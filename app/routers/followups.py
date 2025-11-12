from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from datetime import datetime

from app.database import get_db
from app.models import FollowUp, Contact, User
from app.schemas import FollowUpCreate, FollowUpResponse, FollowUpUpdate
from app.auth import get_current_user

router = APIRouter(tags=["followups"])


@router.get("/contact/{contact_id}", response_model=List[FollowUpResponse])
async def get_followups(
    contact_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all follow-ups for a contact"""
    # Verify contact belongs to user
    contact = db.query(Contact).filter(
        Contact.id == contact_id,
        Contact.user_id == current_user.id
    ).first()

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found"
        )

    followups = db.query(FollowUp).filter(
        FollowUp.contact_id == contact_id,
        FollowUp.user_id == current_user.id
    ).order_by(FollowUp.created_at.desc()).all()

    return [FollowUpResponse.model_validate(fu) for fu in followups]


@router.post("/", response_model=FollowUpResponse, status_code=status.HTTP_201_CREATED)
async def create_followup(
    followup: FollowUpCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new follow-up"""
    # Verify contact belongs to user
    contact = db.query(Contact).filter(
        Contact.id == followup.contact_id,
        Contact.user_id == current_user.id
    ).first()

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found"
        )

    new_followup = FollowUp(
        contact_id=followup.contact_id,
        user_id=current_user.id,
        message=followup.message,
        follow_up_date=followup.follow_up_date
    )
    db.add(new_followup)
    db.commit()
    db.refresh(new_followup)

    return FollowUpResponse.model_validate(new_followup)


@router.put("/{followup_id}", response_model=FollowUpResponse)
async def update_followup(
    followup_id: UUID,
    followup_update: FollowUpUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update follow-up status"""
    followup = db.query(FollowUp).filter(
        FollowUp.id == followup_id,
        FollowUp.user_id == current_user.id
    ).first()

    if not followup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Follow-up not found"
        )

    if followup_update.status:
        followup.status = followup_update.status
    if followup_update.sent_at:
        followup.sent_at = followup_update.sent_at
    elif followup_update.status == 'sent' and not followup.sent_at:
        followup.sent_at = datetime.utcnow()

    db.commit()
    db.refresh(followup)

    return FollowUpResponse.model_validate(followup)


@router.delete("/{followup_id}")
async def delete_followup(
    followup_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a follow-up"""
    followup = db.query(FollowUp).filter(
        FollowUp.id == followup_id,
        FollowUp.user_id == current_user.id
    ).first()

    if not followup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Follow-up not found"
        )

    db.delete(followup)
    db.commit()

    return {"message": "Follow-up deleted successfully"}

