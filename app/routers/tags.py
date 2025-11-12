from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
import logging

from app.database import get_db
from app.models import Tag, User, Contact
from app.schemas import TagResponse, TagUpdate, TagCreate
from app.auth import get_current_user

router = APIRouter(tags=["tags"])
logger = logging.getLogger(__name__)


@router.get("/", response_model=List[TagResponse])
async def get_tags(
    include_hidden: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all tags (system tags + user's custom tags), optionally including hidden ones"""
    try:
        from sqlalchemy import or_
        from sqlalchemy.exc import ProgrammingError
        
        # Try to query with user_id filter first (most common case)
        # If it fails, fall back to simpler query
        try:
            query = db.query(Tag).filter(
                or_(
                    Tag.is_system_tag == True,
                    Tag.user_id == current_user.id
                )
            )
        except (ProgrammingError, AttributeError) as e:
            # user_id column doesn't exist or query failed, use simpler query
            logger.warning("Query with user_id failed, using fallback query", exc_info=True)
            query = db.query(Tag)
        
        if not include_hidden:
            query = query.filter(Tag.is_hidden == False)
        
        tags = query.order_by(Tag.is_system_tag.desc(), Tag.name.asc()).all()
        return [TagResponse.model_validate(tag) for tag in tags]
    except Exception as e:
        logger.error(f"Error in get_tags: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch tags"
        )


@router.get("/system", response_model=List[TagResponse])
async def get_system_tags(
    db: Session = Depends(get_db)
):
    """Get only system tags (public endpoint)"""
    tags = db.query(Tag).filter(
        Tag.is_system_tag == True,
        Tag.is_hidden == False
    ).order_by(Tag.name.asc()).all()
    return [TagResponse.model_validate(tag) for tag in tags]


@router.post("/", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(
    tag_create: TagCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new custom tag"""
    from sqlalchemy.exc import ProgrammingError, IntegrityError
    
    # Check if tag name already exists for this user or as system tag
    try:
        from sqlalchemy import or_
        existing = db.query(Tag).filter(
            Tag.name == tag_create.name,
            (Tag.is_system_tag == True) | (Tag.user_id == current_user.id)
        ).first()
    except (ProgrammingError, AttributeError):
        # Fallback: check without user_id filter
        existing = db.query(Tag).filter(Tag.name == tag_create.name).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A tag with this name already exists"
        )
    
    # Create new tag
    try:
        if hasattr(Tag, 'user_id'):
            new_tag = Tag(
                name=tag_create.name,
                is_system_tag=False,
                user_id=current_user.id
            )
        else:
            new_tag = Tag(
                name=tag_create.name,
                is_system_tag=False
            )
        db.add(new_tag)
        db.commit()
        db.refresh(new_tag)
        return TagResponse.model_validate(new_tag)
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A tag with this name already exists"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating tag: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create tag"
        )


@router.get("/manage", response_model=List[TagResponse])
async def get_tags_for_management(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all tags including hidden ones for management UI (only user's tags + system tags)"""
    try:
        from sqlalchemy import or_
        from sqlalchemy.exc import ProgrammingError
        
        # Try to query with user_id filter first (most common case)
        # If it fails, fall back to simpler query
        try:
            tags = db.query(Tag).filter(
                or_(
                    Tag.is_system_tag == True,
                    Tag.user_id == current_user.id
                )
            ).order_by(Tag.is_system_tag.desc(), Tag.name.asc()).all()
        except (ProgrammingError, AttributeError) as e:
            # user_id column doesn't exist or query failed, use simpler query
            logger.warning("Query with user_id failed, using fallback query", exc_info=True)
            tags = db.query(Tag).order_by(Tag.is_system_tag.desc(), Tag.name.asc()).all()
        
        return [TagResponse.model_validate(tag) for tag in tags]
    except Exception as e:
        logger.error(f"Error in get_tags_for_management: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch tags"
        )


@router.put("/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: UUID,
    tag_update: TagUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update tag (name or hide/show)"""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    
    # Cannot rename system tags
    if tag_update.name and tag.is_system_tag:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot rename system tags"
        )
    
    # Check if user owns this tag (or it's a system tag)
    # Only check if user_id column exists (hasattr check)
    if not tag.is_system_tag and hasattr(tag, 'user_id') and tag.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own tags"
        )
    
    # Check if new name already exists for this user
    if tag_update.name and tag_update.name != tag.name:
        from sqlalchemy.exc import ProgrammingError
        try:
            if hasattr(tag, 'user_id'):
                existing = db.query(Tag).filter(
                    Tag.name == tag_update.name,
                    (Tag.is_system_tag == True) | (Tag.user_id == current_user.id)
                ).first()
            else:
                existing = db.query(Tag).filter(Tag.name == tag_update.name).first()
        except (ProgrammingError, AttributeError):
            # Fallback: check without user_id filter
            existing = db.query(Tag).filter(Tag.name == tag_update.name).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A tag with this name already exists"
            )
        tag.name = tag_update.name
    
    if tag_update.is_hidden is not None:
        tag.is_hidden = tag_update.is_hidden
    
    db.commit()
    db.refresh(tag)
    return TagResponse.model_validate(tag)


@router.delete("/{tag_id}")
async def delete_tag(
    tag_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a custom tag (cannot delete system tags)"""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    
    if tag.is_system_tag:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete system tags"
        )
    
    # Check if user owns this tag (only if user_id column exists)
    if hasattr(tag, 'user_id') and tag.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own tags"
        )
    
    # Check if tag is used by any contacts of this user
    contact_count = db.query(Contact).join(Contact.tags).filter(
        Tag.id == tag_id,
        Contact.user_id == current_user.id
    ).count()
    if contact_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete tag that is used by {contact_count} contact(s). Hide it instead."
        )
    
    db.delete(tag)
    db.commit()
    return {"message": "Tag deleted successfully"}

