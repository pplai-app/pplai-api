from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
import logging

from app.database import get_db
from app.models import User
from app.schemas import UserResponse, UserUpdate, AuthResponse, AdminUserCreate
from app.auth import get_current_admin, create_access_token

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin"])


@router.get("/users", response_model=List[UserResponse])
async def list_all_users(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """List all users (admin only)"""
    try:
        users = db.query(User).order_by(User.created_at.desc()).offset(skip).limit(limit).all()
        # Admin endpoints always include is_admin
        result = []
        for user in users:
            try:
                result.append(UserResponse.from_user(user, include_admin=True))
            except Exception as user_error:
                logger.error(f"Error serializing user {user.id}: {user_error}", exc_info=True)
                # Continue with other users even if one fails
                continue
        return result
    except Exception as e:
        logger.error(f"Error listing users: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list users: {str(e)}"
        )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get a specific user by ID (admin only)"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        # Admin endpoints always include is_admin
        return UserResponse.from_user(user, include_admin=True)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user"
        )


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: AdminUserCreate,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Create a new user (admin only)"""
    try:
        from app.routers.auth import hash_password
        
        # Validate password strength
        if len(user_data.password) < 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 6 characters long"
            )
        
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == user_data.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email already exists"
            )
        
        # Hash password
        password_hash = hash_password(user_data.password)
        
        user = User(
            email=user_data.email,
            name=user_data.name,
            password_hash=password_hash,
            role_company=user_data.role_company,
            mobile=user_data.mobile,
            whatsapp=user_data.whatsapp,
            linkedin_url=user_data.linkedin_url,
            about_me=user_data.about_me,
            is_admin=user_data.is_admin or False,
            oauth_provider='email'
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        logger.info(f"Admin {current_admin.email} created user {user.email}")
        # Admin endpoints always include is_admin
        return UserResponse.from_user(user, include_admin=True)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating user: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user"
        )


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    user_data: UserUpdate,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Update a user (admin only)"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Prevent admin from removing their own admin status
        if user_id == current_admin.id and user_data.is_admin is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove your own admin status"
            )
        
        # Update fields
        if user_data.name is not None:
            user.name = user_data.name
        if user_data.email is not None and user_data.email != user.email:
            # Check if new email is already taken
            existing = db.query(User).filter(User.email == user_data.email, User.id != user_id).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already in use"
                )
            user.email = user_data.email
        if user_data.role_company is not None:
            user.role_company = user_data.role_company
        if user_data.mobile is not None:
            user.mobile = user_data.mobile
        if user_data.whatsapp is not None:
            user.whatsapp = user_data.whatsapp
        if user_data.linkedin_url is not None:
            user.linkedin_url = user_data.linkedin_url
        if user_data.about_me is not None:
            user.about_me = user_data.about_me
        if user_data.is_admin is not None:
            user.is_admin = user_data.is_admin
        
        db.commit()
        db.refresh(user)
        
        logger.info(f"Admin {current_admin.email} updated user {user.email}")
        # Admin endpoints always include is_admin
        return UserResponse.from_user(user, include_admin=True)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating user: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user"
        )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Delete a user (admin only)"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Prevent admin from deleting themselves
        if user_id == current_admin.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete your own account"
            )
        
        user_email = user.email
        db.delete(user)
        db.commit()
        
        logger.info(f"Admin {current_admin.email} deleted user {user_email}")
        return None
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting user: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user"
        )


@router.post("/login-as/{user_id}", response_model=AuthResponse)
async def login_as_user(
    user_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Login as any user (admin impersonation)"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Create token for the target user
        token = create_access_token(str(user.id))
        
        logger.info(f"Admin {current_admin.email} logged in as user {user.email}")
        
        return AuthResponse(
            token=token,
            user=UserResponse.from_user(user, include_admin=user.is_admin)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in login_as_user: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to login as user"
        )

