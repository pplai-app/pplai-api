from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from typing import Optional
import qrcode
from io import BytesIO
import base64
import os

from app.database import get_db
from app.models import User
from app.schemas import UserResponse
from app.auth import get_current_user
from app.storage import upload_file_to_s3, delete_file_from_s3
from app.cache import get_cached, set_cached, delete_cached, cache_key

router = APIRouter(tags=["profile"])

# Cache TTLs (in seconds)
PROFILE_CACHE_TTL = 3600  # 1 hour for public profiles
USER_PROFILE_CACHE_TTL = 1800  # 30 minutes for own profile
QR_CACHE_TTL = 7200  # 2 hours for QR codes (they don't change often)


@router.get("/", response_model=UserResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's profile"""
    # Cache key includes user ID
    cache_key_str = cache_key("profile:user", str(current_user.id))
    
    # Try to get from cache
    cached_profile = get_cached(cache_key_str)
    if cached_profile is not None:
        return UserResponse(**cached_profile)
    
    # Cache miss - get from database
    profile_data = UserResponse.from_user(current_user, include_admin=current_user.is_admin)
    profile_dict = profile_data.model_dump()
    
    # Cache the result
    set_cached(cache_key_str, profile_dict, USER_PROFILE_CACHE_TTL)
    
    return profile_data


@router.get("/{user_id}", response_model=UserResponse)
async def get_public_profile(
    user_id: str,
    db: Session = Depends(get_db)
):
    """Get public profile by ID (for QR code sharing)"""
    # Cache key for public profile
    cache_key_str = cache_key("profile:public", user_id)
    
    # Try to get from cache
    cached_profile = get_cached(cache_key_str)
    if cached_profile is not None:
        return UserResponse(**cached_profile)
    
    # Cache miss - get from database
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    
    # Never include is_admin in public profiles
    profile_data = UserResponse.from_user(user, include_admin=False)
    profile_dict = profile_data.model_dump()
    
    # Cache the result (longer TTL for public profiles since they're accessed more frequently)
    set_cached(cache_key_str, profile_dict, PROFILE_CACHE_TTL)
    
    return profile_data


@router.put("/", response_model=UserResponse)
async def update_profile(
    name: Optional[str] = Form(None),
    role_company: Optional[str] = Form(None),
    mobile: Optional[str] = Form(None),
    whatsapp: Optional[str] = Form(None),
    linkedin_url: Optional[str] = Form(None),
    about_me: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user profile"""
    try:
        # Handle photo upload
        if photo and photo.filename:
            # Delete old photo if exists
            if current_user.profile_photo_url:
                try:
                    delete_file_from_s3(current_user.profile_photo_url)
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Error deleting old photo: {e}", exc_info=True)

            # Upload new photo
            photo_content = await photo.read()
            current_user.profile_photo_url = upload_file_to_s3(
                photo_content,
                photo.filename,
                photo.content_type,
                'profiles'
            )

        # Update other fields (handle empty strings as None)
        if name is not None:
            current_user.name = name.strip() if name and name.strip() else current_user.name
        if role_company is not None:
            current_user.role_company = role_company.strip() if role_company and role_company.strip() else None
        if mobile is not None:
            current_user.mobile = mobile.strip() if mobile and mobile.strip() else None
        if whatsapp is not None:
            current_user.whatsapp = whatsapp.strip() if whatsapp and whatsapp.strip() else None
        if linkedin_url is not None:
            current_user.linkedin_url = linkedin_url.strip() if linkedin_url and linkedin_url.strip() else None
        if about_me is not None:
            current_user.about_me = about_me.strip() if about_me and about_me.strip() else None

        db.commit()
        db.refresh(current_user)

        # Invalidate cache for this user's profile
        user_cache_key = cache_key("profile:user", str(current_user.id))
        public_cache_key = cache_key("profile:public", str(current_user.id))
        delete_cached(user_cache_key)
        delete_cached(public_cache_key)
        
        # Also invalidate QR cache for this user
        qr_url_key = cache_key("qr:url", str(current_user.id))
        qr_vcard_key = cache_key("qr:vcard", str(current_user.id))
        delete_cached(qr_url_key)
        delete_cached(qr_vcard_key)

        # Only include is_admin if the user is actually an admin
        return UserResponse.from_user(current_user, include_admin=current_user.is_admin)
    except Exception as e:
        db.rollback()
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating profile: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile"
        )


@router.get("/qr/{user_id}")
async def get_profile_qr(
    user_id: str, 
    mode: str = Query("url", description="QR mode: 'url' or 'vcard'"),
    db: Session = Depends(get_db)
):
    """Generate QR code for profile sharing
    
    Args:
        user_id: User ID
        mode: "url" for profile URL, "vcard" for vCard format
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Try to convert user_id to UUID if it's a string
        from uuid import UUID
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format"
            )
        
        user = db.query(User).filter(User.id == user_uuid).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Check cache for QR code
        qr_cache_key = cache_key("qr", mode, user_id)
        cached_qr = get_cached(qr_cache_key)
        if cached_qr is not None:
            return cached_qr
        
        if mode == "vcard":
            # Generate vCard QR code
            vcard = generate_vcard_from_user(user)
            qr_data = vcard
        else:
            # Generate URL QR code
            frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:8080')
            profile_url = f"{frontend_url}/profile/{user_id}"
            qr_data = profile_url

        # Generate QR code
        try:
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(qr_data)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)

            # Convert to base64 data URL
            img_base64 = base64.b64encode(buffer.read()).decode()
        except Exception as qr_error:
            logger.error(f"Error generating QR code: {qr_error}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate QR code"
            )
        
        if mode == "vcard":
            result = {
                "qr_code": f"data:image/png;base64,{img_base64}",
                "vcard": vcard,
                "mode": "vcard"
            }
        else:
            result = {
                "qr_code": f"data:image/png;base64,{img_base64}",
                "profile_url": qr_data,
                "mode": "url"
            }
        
        # Cache the QR code result
        set_cached(qr_cache_key, result, QR_CACHE_TTL)
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_profile_qr: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


def generate_vcard_from_user(user):
    """Generate vCard format from user data"""
    from datetime import datetime
    
    vcard = "BEGIN:VCARD\n"
    vcard += "VERSION:3.0\n"
    vcard += f"FN:{escape_vcard_value(user.name or '')}\n"
    vcard += f"N:{escape_vcard_value(user.name or '')};;;;\n"
    
    if user.email:
        vcard += f"EMAIL:{escape_vcard_value(user.email)}\n"
    
    if user.mobile:
        vcard += f"TEL;TYPE=CELL:{escape_vcard_value(user.mobile)}\n"
    
    if user.whatsapp:
        vcard += f"TEL;TYPE=CELL,WA:{escape_vcard_value(user.whatsapp)}\n"
    
    if user.linkedin_url:
        vcard += f"URL:{escape_vcard_value(user.linkedin_url)}\n"
    
    if user.role_company:
        vcard += f"TITLE:{escape_vcard_value(user.role_company)}\n"
    
    if user.about_me:
        vcard += f"NOTE:{escape_vcard_value(user.about_me)}\n"
    
    if user.profile_photo_url:
        vcard += f"PHOTO;VALUE=URI:{escape_vcard_value(user.profile_photo_url)}\n"
    
    # Add pplai.app profile URL
    frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:8080')
    pplai_profile_url = f"{frontend_url}/profile/{user.id}"
    vcard += f"URL;TYPE=PPLAI:{escape_vcard_value(pplai_profile_url)}\n"
    
    # Add pplai.app custom fields
    now = datetime.now()
    date_connected = now.strftime('%Y-%m-%d')
    vcard += f"X-PPLAI-DATE-CONNECTED:{escape_vcard_value(date_connected)}\n"
    
    # Add custom field for "Date Connected on pplai.app" (more readable format)
    date_connected_readable = now.strftime('%B %d, %Y')
    vcard += f"X-PPLAI-DATE-CONNECTED-READABLE:{escape_vcard_value(date_connected_readable)}\n"
    
    # Add notes
    notes = f"Connected via pplai.app on {now.strftime('%Y-%m-%d')}"
    vcard += f"X-PPLAI-NOTES:{escape_vcard_value(notes)}\n"
    
    vcard += "END:VCARD"
    return vcard


def escape_vcard_value(value):
    """Escape special characters in vCard values"""
    if not value:
        return ''
    # Replace special characters
    value = str(value).replace('\\', '\\\\')
    value = value.replace(',', '\\,')
    value = value.replace(';', '\\;')
    value = value.replace('\n', '\\n')
    value = value.replace('\r', '')
    return value

