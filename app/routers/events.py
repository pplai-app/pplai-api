from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
import httpx
import logging

from app.database import get_db
from app.models import Event, User
from app.schemas import EventCreate, EventResponse
from app.auth import get_current_user

router = APIRouter(tags=["events"])
logger = logging.getLogger(__name__)


@router.get("/", response_model=List[EventResponse])
async def get_events(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all events for current user"""
    events = db.query(Event).filter(Event.user_id == current_user.id).order_by(Event.start_date.desc()).all()
    return [EventResponse.model_validate(event) for event in events]


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get single event"""
    event = db.query(Event).filter(
        Event.id == event_id,
        Event.user_id == current_user.id
    ).first()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    return EventResponse.model_validate(event)


@router.post("/", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    event: EventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new event"""
    new_event = Event(
        user_id=current_user.id,
        **event.dict()
    )
    db.add(new_event)
    db.commit()
    db.refresh(new_event)

    return EventResponse.model_validate(new_event)


@router.put("/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: UUID,
    event: EventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an event"""
    db_event = db.query(Event).filter(
        Event.id == event_id,
        Event.user_id == current_user.id
    ).first()

    if not db_event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    for key, value in event.dict().items():
        setattr(db_event, key, value)

    db.commit()
    db.refresh(db_event)

    return EventResponse.model_validate(db_event)


@router.delete("/{event_id}")
async def delete_event(
    event_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an event"""
    event = db.query(Event).filter(
        Event.id == event_id,
        Event.user_id == current_user.id
    ).first()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    db.delete(event)
    db.commit()

    return {"message": "Event deleted successfully"}


@router.get("/search/locations")
async def search_locations(
    q: str = Query(..., min_length=2, description="Location search query"),
    limit: int = Query(8, ge=1, le=20, description="Maximum number of results"),
    current_user: User = Depends(get_current_user)
):
    """Search for locations using Nominatim API (proxied to avoid CORS issues)"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "format": "json",
                    "q": q,
                    "limit": limit,
                    "addressdetails": 1
                },
                headers={
                    "User-Agent": "PPLAI-Networking-App/1.0 (https://pplai.app)"
                }
            )
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        logger.warning(f"Location search timeout for query: {q}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Location search timed out"
        )
    except httpx.HTTPStatusError as e:
        logger.warning(f"Location search HTTP error for query: {q}: {e.response.status_code}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Location service unavailable"
        )
    except Exception as e:
        logger.error(f"Location search error for query: {q}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Location search failed"
        )

