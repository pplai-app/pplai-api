from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import bcrypt
import logging
import time
from app.database import get_db
from app.models import User
from app.schemas import OAuthRequest, EmailAuthRequest, AuthResponse, UserResponse
from app.auth import create_access_token
from app.logging_config import metrics
from app.middleware import DatabaseMetricsMiddleware

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])

def hash_password(password: str) -> str:
    """Hash a password using bcrypt directly"""
    # Generate salt and hash password
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception:
        return False


@router.post("/oauth", response_model=AuthResponse)
async def oauth_login(
    request: OAuthRequest,
    db: Session = Depends(get_db)
):
    """Handle OAuth login (Google/LinkedIn)"""
    logger.info(f"OAuth login attempt for email: {request.email}")
    start_time = time.time()
    
    if not request.email or not request.name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email and name are required"
        )

    # Check if user exists
    try:
        logger.debug(f"Querying database for user: {request.email}")
        user = db.query(User).filter(User.email == request.email).first()
        logger.debug(f"User query completed: {'found' if user else 'not found'}")
    except Exception as db_error:
        logger.error(f"Database error in oauth_login: {db_error}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection error. Please try again."
        )

    if not user:
        # Create new user
        try:
            user = User(
                email=request.email,
                name=request.name,
                profile_photo_url=request.photo,
                oauth_provider=request.provider,
                oauth_id=request.oauth_id
            )
            db.add(user)
            db.commit()
            # No need to refresh, user object is already updated
            user_id = str(user.id)
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating user: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create account"
            )
        
        metrics.log_business_event('user_created', user_id=user_id, method='oauth')
        logger.info(f"New user created via OAuth: {user.email}")
    else:
        # Update OAuth info if changed
        if user.oauth_provider != request.provider or user.oauth_id != request.oauth_id:
            try:
                user.oauth_provider = request.provider
                user.oauth_id = request.oauth_id
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating OAuth info: {e}", exc_info=True)
                # Continue anyway, not critical
        
        metrics.log_business_event('user_login', user_id=str(user.id), method='oauth')
        logger.info(f"User logged in via OAuth: {user.email}")

    token = create_access_token(str(user.id))
    
    duration_ms = (time.time() - start_time) * 1000
    logger.debug(f"OAuth login completed in {duration_ms:.2f}ms")

    return AuthResponse(
        token=token,
        user=UserResponse.from_user(user, include_admin=user.is_admin)
    )


@router.post("/email", response_model=AuthResponse)
async def email_login(
    request: EmailAuthRequest,
    db: Session = Depends(get_db)
):
    """Handle email-based login/signup with password"""
    start_time = time.time()
    is_signup = False
    
    # Validate email
    if not request.email:
        logger.warning("Email login attempt with missing email")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is required"
        )
    
    # Validate password
    if not request.password:
        logger.warning(f"Email login attempt with missing password for: {request.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password is required"
        )
    
    logger.info(f"Email login attempt for email: {request.email}")

    # Check if user exists
    try:
        logger.debug(f"Querying database for user: {request.email}")
        user = db.query(User).filter(User.email == request.email).first()
        logger.debug(f"User query completed: {'found' if user else 'not found'}")
    except Exception as db_error:
        logger.error(f"Database error in email_login: {db_error}", exc_info=True)
        logger.error(f"Error type: {type(db_error).__name__}", exc_info=True)
        try:
            db.rollback()
        except:
            pass
        # Provide more specific error message
        error_msg = str(db_error)
        if "connection" in error_msg.lower() or "timeout" in error_msg.lower():
            detail = "Database connection error. Please check if PostgreSQL is running and try again."
        elif "does not exist" in error_msg.lower():
            detail = "Database not found. Please check your DATABASE_URL configuration."
        else:
            detail = f"Database error: {error_msg[:100]}"
        
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail
        )

    if not user:
        # Sign up: Create new user with email and password
        is_signup = True
        if not request.name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Name is required for signup"
            )
        
        # Validate password strength (minimum 6 characters)
        if len(request.password) < 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 6 characters long"
            )
        
        name = request.name
        try:
            # Hash password before database operation to avoid holding transaction
            password_hash = hash_password(request.password)
            user = User(
                email=request.email,
                name=name,
                password_hash=password_hash,
                oauth_provider='email'
            )
            db.add(user)
            db.commit()
            # No need to refresh, user object is already updated
            user_id = str(user.id)
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating user: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create account"
            )
        
        metrics.log_business_event('user_created', user_id=user_id, method='email')
        logger.info(f"New user created via email: {user.email}")
    else:
        # Login: Verify password
        if not user.password_hash:
            metrics.log_error('auth_error', 'Password not set for account', user_id=str(user.id))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This account was created with OAuth. Please use OAuth to login."
            )
        
        if not verify_password(request.password, user.password_hash):
            metrics.log_error('auth_error', 'Invalid password', user_id=str(user.id))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        metrics.log_business_event('user_login', user_id=str(user.id), method='email')
        logger.info(f"User logged in via email: {user.email}")

    token = create_access_token(str(user.id))
    
    duration_ms = (time.time() - start_time) * 1000
    logger.debug(f"Email {'signup' if is_signup else 'login'} completed in {duration_ms:.2f}ms")

    return AuthResponse(
        token=token,
        user=UserResponse.from_user(user, include_admin=user.is_admin)
    )

