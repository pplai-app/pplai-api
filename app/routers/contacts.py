from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Union
from uuid import UUID
import json
import logging

from app.database import get_db
from app.models import Contact, Tag, MediaAttachment, User, Event
from app.schemas import ContactCreate, ContactResponse, TagResponse, MediaAttachmentResponse
from app.auth import get_current_user
from app.storage import upload_file_to_s3, delete_file_from_s3, get_file_type
from app.logging_config import metrics
from app.middleware import DatabaseMetricsMiddleware
import time

logger = logging.getLogger(__name__)

router = APIRouter(tags=["contacts"])


@router.get("/", response_model=List[ContactResponse])
async def get_contacts(
    event_id: Optional[UUID] = None,
    tag_id: Optional[UUID] = None,
    date_range: Optional[str] = None,  # 'today', 'week', 'month'
    date_from: Optional[str] = None,  # ISO date string
    date_to: Optional[str] = None,  # ISO date string
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all contacts for current user, optionally filtered by event, tag, or date"""
    start_time = time.time()
    from datetime import datetime, timedelta, time as dt_time
    from sqlalchemy import and_
    
    with DatabaseMetricsMiddleware('SELECT', 'contacts', user_id=str(current_user.id)):
        query = db.query(Contact).filter(Contact.user_id == current_user.id)

    if event_id and str(event_id) != 'all':
        query = query.filter(Contact.event_id == event_id)
    
    if tag_id:
        query = query.join(Contact.tags).filter(Tag.id == tag_id)
    
    # Handle date filters
    if date_range or date_from or date_to:
        now = datetime.now()
        today_start = datetime.combine(now.date(), dt_time.min)
        
        if date_range == 'today':
            query = query.filter(Contact.meeting_date >= today_start)
        elif date_range == 'week':
            week_start = today_start - timedelta(days=now.weekday())
            query = query.filter(Contact.meeting_date >= week_start)
        elif date_range == 'month':
            month_start = datetime(now.year, now.month, 1)
            query = query.filter(Contact.meeting_date >= month_start)
        elif date_from or date_to:
            if date_from:
                from_date = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                query = query.filter(Contact.meeting_date >= from_date)
            if date_to:
                to_date = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
                # Include the entire day
                to_date = to_date.replace(hour=23, minute=59, second=59)
                query = query.filter(Contact.meeting_date <= to_date)

    # Use joinedload to eagerly load relationships and avoid lazy loading issues
    from sqlalchemy.orm import joinedload
    with DatabaseMetricsMiddleware('SELECT', 'contacts', user_id=str(current_user.id)):
        contacts = query.options(
            joinedload(Contact.tags),
            joinedload(Contact.media_attachments),
            joinedload(Contact.event)
        ).order_by(Contact.meeting_date.desc()).all()
    
    duration_ms = (time.time() - start_time) * 1000
    logger.debug(f"Retrieved {len(contacts)} contacts in {duration_ms:.2f}ms")

    result = []
    for contact in contacts:
        try:
            # Build contact dict manually to handle potential schema issues
            contact_dict = {
                'id': contact.id,
                'user_id': contact.user_id,
                'name': contact.name,
                'email': contact.email,
                'role_company': contact.role_company,
                'mobile': contact.mobile,
                'linkedin_url': contact.linkedin_url,
                'contact_photo_url': contact.contact_photo_url,
                'meeting_context': contact.meeting_context,
                'meeting_date': contact.meeting_date,
                'meeting_latitude': float(contact.meeting_latitude) if contact.meeting_latitude else None,
                'meeting_longitude': float(contact.meeting_longitude) if contact.meeting_longitude else None,
                'meeting_location_name': contact.meeting_location_name,
                'event_id': contact.event_id,
                'created_at': contact.created_at,
                'updated_at': contact.updated_at,
            }
            
            # Get tags safely - already eagerly loaded via joinedload
            try:
                tags_list = []
                for tag in contact.tags:
                    try:
                        tags_list.append(TagResponse.model_validate(tag).model_dump())
                    except Exception as tag_error:
                        logger.warning(f"Error processing tag {tag.id if hasattr(tag, 'id') else 'unknown'}", exc_info=True)
                contact_dict['tags'] = tags_list
            except Exception as e:
                logger.warning(f"Error loading tags for contact {contact.id}: {e}", exc_info=True)
                contact_dict['tags'] = []
            
            # Get media safely
            try:
                contact_dict['media'] = [MediaAttachmentResponse.model_validate(media).model_dump() for media in contact.media_attachments]
            except Exception as e:
                logger.warning(f"Error loading media for contact {contact.id}", exc_info=True)
                contact_dict['media'] = []
            
            # Include event information if available
            if contact.event:
                try:
                    from app.schemas import EventResponse
                    contact_dict['event'] = EventResponse.model_validate(contact.event).model_dump()
                except Exception as e:
                    logger.warning(f"Error loading event for contact {contact.id}", exc_info=True)
            
            result.append(ContactResponse(**contact_dict))
        except Exception as e:
            logger.error(f"Error processing contact {contact.id}", exc_info=True)
            # Skip this contact if there's an error
            continue

    return result


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get single contact"""
    contact = db.query(Contact).filter(
        Contact.id == contact_id,
        Contact.user_id == current_user.id
    ).first()

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found"
        )

    contact_dict = ContactResponse.model_validate(contact).dict()
    contact_dict['tags'] = [TagResponse.model_validate(tag) for tag in contact.tags]
    contact_dict['media'] = [MediaAttachmentResponse.model_validate(media) for media in contact.media_attachments]
    
    # Include event information if available
    if contact.event:
        from app.schemas import EventResponse
        contact_dict['event'] = EventResponse.model_validate(contact.event).dict()

    return ContactResponse(**contact_dict)


@router.post("/", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    name: str = Form(...),
    email: Optional[str] = Form(None),
    role_company: Optional[str] = Form(None),
    mobile: Optional[str] = Form(None),
    linkedin_url: Optional[str] = Form(None),
    meeting_context: Optional[str] = Form(None),
    meeting_date: Optional[str] = Form(None),  # ISO datetime string
    event_id: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),  # JSON string
    meeting_latitude: Optional[str] = Form(None),
    meeting_longitude: Optional[str] = Form(None),
    meeting_location_name: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    media: List[UploadFile] = File([]),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new contact"""
    start_time = time.time()
    
    # Handle photo upload
    contact_photo_url = None
    if photo:
        photo_content = await photo.read()
        contact_photo_url = upload_file_to_s3(
            photo_content,
            photo.filename,
            photo.content_type,
            'contacts'
        )

    # Parse event_id
    event_uuid = None
    if event_id and event_id != 'null':
        try:
            event_uuid = UUID(event_id)
            # Verify event belongs to user
            event = db.query(Event).filter(
                Event.id == event_uuid,
                Event.user_id == current_user.id
            ).first()
            if not event:
                event_uuid = None
        except:
            event_uuid = None

    # Parse location coordinates
    latitude = None
    longitude = None
    if meeting_latitude and meeting_longitude:
        try:
            latitude = float(meeting_latitude)
            longitude = float(meeting_longitude)
        except (ValueError, TypeError):
            pass

    # Create contact
    # Parse meeting_date if provided
    from datetime import datetime
    meeting_datetime = None
    if meeting_date:
        try:
            meeting_datetime = datetime.fromisoformat(meeting_date.replace('Z', '+00:00'))
        except Exception as e:
            logger.warning("Error parsing meeting_date, using current datetime", exc_info=True)
            # Use current datetime as fallback
            meeting_datetime = datetime.now()
    else:
        # Default to current time if not provided
        meeting_datetime = datetime.now()
    
    # Add pplai.app metadata to meeting_context if not already present
    # This ensures all contacts created from pplai.app have the connection date
    enhanced_context = meeting_context or ""
    if "Date Connected on pplai.app" not in (meeting_context or "") and "Connected via pplai.app" not in (meeting_context or ""):
        date_connected = meeting_datetime.strftime('%Y-%m-%d')
        date_connected_readable = meeting_datetime.strftime('%B %d, %Y')
        pplai_metadata = f"Date Connected on pplai.app: {date_connected_readable} ({date_connected})"
        if enhanced_context:
            enhanced_context = f"{enhanced_context}\n\n{pplai_metadata}"
        else:
            enhanced_context = pplai_metadata
    
    with DatabaseMetricsMiddleware('INSERT', 'contacts', user_id=str(current_user.id)):
        new_contact = Contact(
            user_id=current_user.id,
            event_id=event_uuid,
            name=name,
            email=email,
            role_company=role_company,
            mobile=mobile,
            linkedin_url=linkedin_url,
            contact_photo_url=contact_photo_url,
            meeting_context=enhanced_context,
            meeting_date=meeting_datetime,
            meeting_latitude=latitude,
            meeting_longitude=longitude,
            meeting_location_name=meeting_location_name
        )
        db.add(new_contact)
        db.commit()
        db.refresh(new_contact)
    
    metrics.log_business_event('contact_created', user_id=str(current_user.id), contact_id=str(new_contact.id), has_photo=bool(contact_photo_url), has_media=len(media) > 0, has_event=bool(event_uuid))
    duration_ms = (time.time() - start_time) * 1000
    logger.info(f"Contact created: {new_contact.name} (ID: {new_contact.id}) by user {current_user.id} in {duration_ms:.2f}ms")

    # Handle tags
    if tags:
        try:
            tag_list = json.loads(tags) if isinstance(tags, str) else tags
            for tag_name in tag_list:
                # Check if tag exists for this user, create if not
                # First check system tags, then user's custom tags
                try:
                    tag = db.query(Tag).filter(
                        Tag.name == tag_name,
                        (Tag.is_system_tag == True) | (Tag.user_id == current_user.id)
                    ).first()
                except Exception:
                    # Fallback: if user_id column doesn't exist, check by name only
                    tag = db.query(Tag).filter(Tag.name == tag_name).first()
                
                if not tag:
                    # Create tag with user_id if column exists, otherwise without
                    try:
                        tag = Tag(name=tag_name, is_system_tag=False, user_id=current_user.id)
                    except Exception:
                        tag = Tag(name=tag_name, is_system_tag=False)
                    db.add(tag)
                    db.commit()
                    db.refresh(tag)

                # Link tag to contact
                if tag not in new_contact.tags:
                    new_contact.tags.append(tag)
        except Exception as e:
            logger.warning("Error processing tags", exc_info=True)

    # Handle media attachments
    for file in media:
        file_content = await file.read()
        media_url = upload_file_to_s3(
            file_content,
            file.filename,
            file.content_type,
            'media'
        )

        media_attachment = MediaAttachment(
            contact_id=new_contact.id,
            file_url=media_url,
            file_type=get_file_type(file.content_type),
            file_name=file.filename,
            file_size=len(file_content)
        )
        db.add(media_attachment)

    db.commit()
    db.refresh(new_contact)

    contact_dict = ContactResponse.model_validate(new_contact).dict()
    contact_dict['tags'] = [TagResponse.model_validate(tag) for tag in new_contact.tags]
    contact_dict['media'] = [MediaAttachmentResponse.model_validate(media) for media in new_contact.media_attachments]
    
    # Include event information if available
    if new_contact.event:
        from app.schemas import EventResponse
        contact_dict['event'] = EventResponse.model_validate(new_contact.event).dict()

    return ContactResponse(**contact_dict)


@router.put("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: UUID,
    name: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    role_company: Optional[str] = Form(None),
    mobile: Optional[str] = Form(None),
    linkedin_url: Optional[str] = Form(None),
    meeting_context: Optional[str] = Form(None),
    meeting_date: Optional[str] = Form(None),  # ISO datetime string
    event_id: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    media: List[UploadFile] = File([]),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a contact"""
    contact = db.query(Contact).filter(
        Contact.id == contact_id,
        Contact.user_id == current_user.id
    ).first()

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found"
        )

    # Handle photo upload
    if photo:
        # Delete old photo
        if contact.contact_photo_url:
            try:
                delete_file_from_s3(contact.contact_photo_url)
            except Exception as e:
                logger.warning("Error deleting old photo", exc_info=True)

        # Upload new photo
        photo_content = await photo.read()
        contact.contact_photo_url = upload_file_to_s3(
            photo_content,
            photo.filename,
            photo.content_type,
            'contacts'
        )

    # Update fields
    if name:
        contact.name = name
    if email is not None:
        contact.email = email
    if role_company is not None:
        contact.role_company = role_company
    if mobile is not None:
        contact.mobile = mobile
    if linkedin_url is not None:
        contact.linkedin_url = linkedin_url
    if meeting_context is not None:
        contact.meeting_context = meeting_context
    if meeting_date:
        try:
            from datetime import datetime
            contact.meeting_date = datetime.fromisoformat(meeting_date.replace('Z', '+00:00'))
        except Exception as e:
            logger.warning("Error parsing meeting_date", exc_info=True)
    if event_id and event_id != 'null':
        try:
            contact.event_id = UUID(event_id)
        except:
            pass

    # Update tags
    if tags:
        # Remove existing tags
        contact.tags.clear()

        try:
            tag_list = json.loads(tags) if isinstance(tags, str) else tags
            for tag_name in tag_list:
                # Check if tag exists for this user (system tags or user's custom tags)
                try:
                    tag = db.query(Tag).filter(
                        Tag.name == tag_name,
                        (Tag.is_system_tag == True) | (Tag.user_id == current_user.id)
                    ).first()
                except Exception:
                    # Fallback: if user_id column doesn't exist, check by name only
                    tag = db.query(Tag).filter(Tag.name == tag_name).first()
                
                if not tag:
                    # Create tag with user_id if column exists, otherwise without
                    try:
                        tag = Tag(name=tag_name, is_system_tag=False, user_id=current_user.id)
                    except Exception:
                        tag = Tag(name=tag_name, is_system_tag=False)
                    db.add(tag)
                    db.commit()
                    db.refresh(tag)

                contact.tags.append(tag)
        except Exception as e:
            logger.warning("Error processing tags", exc_info=True)

    # Handle new media attachments
    for file in media:
        file_content = await file.read()
        media_url = upload_file_to_s3(
            file_content,
            file.filename,
            file.content_type,
            'media'
        )

        media_attachment = MediaAttachment(
            contact_id=contact.id,
            file_url=media_url,
            file_type=get_file_type(file.content_type),
            file_name=file.filename,
            file_size=len(file_content)
        )
        db.add(media_attachment)

    db.commit()
    db.refresh(contact)

    contact_dict = ContactResponse.model_validate(contact).dict()
    contact_dict['tags'] = [TagResponse.model_validate(tag) for tag in contact.tags]
    contact_dict['media'] = [MediaAttachmentResponse.model_validate(media) for media in contact.media_attachments]
    
    # Include event information if available
    if contact.event:
        from app.schemas import EventResponse
        contact_dict['event'] = EventResponse.model_validate(contact.event).dict()

    return ContactResponse(**contact_dict)


@router.get("/find")
async def find_contact(
    email: Optional[str] = None,
    mobile: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Find existing contact by email or mobile number"""
    if not email and not mobile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email or mobile number is required"
        )
    
    query = db.query(Contact).filter(Contact.user_id == current_user.id)
    
    conditions = []
    if email:
        conditions.append(Contact.email == email)
    if mobile:
        # Clean mobile number for comparison
        clean_mobile = mobile.replace(' ', '').replace('-', '').replace('(', '').replace(')', '').replace('+', '')
        # Use simpler comparison - check if cleaned mobile matches
        conditions.append(
            db.func.replace(
                db.func.replace(
                    db.func.replace(
                        db.func.replace(
                            db.func.replace(Contact.mobile, ' ', ''),
                            '-', ''
                        ),
                        '(', ''
                    ),
                    ')', ''
                ),
                '+', ''
            ) == clean_mobile
        )
    
    if len(conditions) == 1:
        contact = query.filter(conditions[0]).first()
    else:
        from sqlalchemy import or_
        contact = query.filter(or_(*conditions)).first()
    
    if contact:
        contact_dict = ContactResponse.model_validate(contact).dict()
        contact_dict['tags'] = [TagResponse.model_validate(tag) for tag in contact.tags]
        contact_dict['media'] = [MediaAttachmentResponse.model_validate(media) for media in contact.media_attachments]
        if contact.event:
            from app.schemas import EventResponse
            contact_dict['event'] = EventResponse.model_validate(contact.event).dict()
        return ContactResponse(**contact_dict)
    
    # Return null JSON response if not found
    return JSONResponse(content=None, status_code=200)


@router.post("/{contact_id}/message")
async def add_message_to_contact(
    contact_id: UUID,
    message: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add a message to contact's meeting context"""
    contact = db.query(Contact).filter(
        Contact.id == contact_id,
        Contact.user_id == current_user.id
    ).first()
    
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found"
        )
    
    # Append message to existing context with timestamp
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    separator = "\n\n" if contact.meeting_context else ""
    new_message = f"{separator}[{timestamp}] {message}"
    
    if contact.meeting_context:
        contact.meeting_context += new_message
    else:
        contact.meeting_context = new_message
    
    db.commit()
    db.refresh(contact)
    
    contact_dict = ContactResponse.model_validate(contact).dict()
    contact_dict['tags'] = [TagResponse.model_validate(tag) for tag in contact.tags]
    contact_dict['media'] = [MediaAttachmentResponse.model_validate(media) for media in contact.media_attachments]
    if contact.event:
        from app.schemas import EventResponse
        contact_dict['event'] = EventResponse.model_validate(contact.event).dict()
    
    return ContactResponse(**contact_dict)


@router.post("/{contact_id}/media")
async def add_media_to_contact(
    contact_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add media attachment to contact"""
    contact = db.query(Contact).filter(
        Contact.id == contact_id,
        Contact.user_id == current_user.id
    ).first()
    
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found"
        )
    
    file_content = await file.read()
    media_url = upload_file_to_s3(
        file_content,
        file.filename,
        file.content_type,
        'media'
    )
    
    media_attachment = MediaAttachment(
        contact_id=contact.id,
        file_url=media_url,
        file_type=get_file_type(file.content_type),
        file_name=file.filename,
        file_size=len(file_content)
    )
    db.add(media_attachment)
    db.commit()
    db.refresh(media_attachment)
    
    return MediaAttachmentResponse.model_validate(media_attachment)


@router.delete("/{contact_id}")
async def delete_contact(
    contact_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a contact"""
    contact = db.query(Contact).filter(
        Contact.id == contact_id,
        Contact.user_id == current_user.id
    ).first()

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found"
        )

    # Delete media files from S3
    for media in contact.media_attachments:
        try:
            delete_file_from_s3(media.file_url)
        except Exception as e:
            logger.warning("Error deleting media", exc_info=True)

    if contact.contact_photo_url:
        try:
            delete_file_from_s3(contact.contact_photo_url)
        except Exception as e:
            logger.warning("Error deleting photo", exc_info=True)

    db.delete(contact)
    db.commit()

    return {"message": "Contact deleted successfully"}

