from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import date, datetime
from uuid import UUID


# User Schemas
class UserBase(BaseModel):
    email: EmailStr
    name: str


class UserCreate(UserBase):
    role_company: Optional[str] = None
    mobile: Optional[str] = None
    whatsapp: Optional[str] = None
    linkedin_url: Optional[str] = None
    about_me: Optional[str] = None
    profile_photo_url: Optional[str] = None
    oauth_provider: Optional[str] = None
    oauth_id: Optional[str] = None


class UserResponse(UserBase):
    id: UUID
    role_company: Optional[str]
    mobile: Optional[str]
    whatsapp: Optional[str]
    linkedin_url: Optional[str]
    about_me: Optional[str]
    profile_photo_url: Optional[str]
    is_admin: Optional[bool] = None  # Only included if user is admin viewing their own profile or admin endpoints
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_user(cls, user, include_admin: bool = False):
        """Create UserResponse from User model, conditionally including is_admin"""
        data = {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role_company": user.role_company,
            "mobile": user.mobile,
            "whatsapp": user.whatsapp,
            "linkedin_url": user.linkedin_url,
            "about_me": user.about_me,
            "profile_photo_url": user.profile_photo_url,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }
        if include_admin:
            data["is_admin"] = user.is_admin
        return cls(**data)


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    role_company: Optional[str] = None
    mobile: Optional[str] = None
    whatsapp: Optional[str] = None
    linkedin_url: Optional[str] = None
    about_me: Optional[str] = None
    is_admin: Optional[bool] = None


# Auth Schemas
class OAuthRequest(BaseModel):
    provider: str  # 'google', 'linkedin'
    email: EmailStr
    name: str
    photo: Optional[str] = None
    oauth_id: Optional[str] = None


class EmailAuthRequest(BaseModel):
    email: EmailStr
    password: str  # Required for login/signup
    name: Optional[str] = None  # Optional, only used for signup


class AdminUserCreate(BaseModel):
    """Schema for admin creating users with full profile"""
    email: EmailStr
    password: str
    name: str
    role_company: Optional[str] = None
    mobile: Optional[str] = None
    whatsapp: Optional[str] = None
    linkedin_url: Optional[str] = None
    about_me: Optional[str] = None
    is_admin: Optional[bool] = False


class AuthResponse(BaseModel):
    token: str
    user: UserResponse


# Event Schemas
class EventBase(BaseModel):
    name: str
    location: str
    start_date: date
    end_date: date
    description: Optional[str] = None


class EventCreate(EventBase):
    pass


class EventResponse(EventBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Tag Schemas
class TagCreate(BaseModel):
    name: str

class TagResponse(BaseModel):
    id: UUID
    name: str
    is_system_tag: bool
    is_hidden: bool
    created_at: datetime

    class Config:
        from_attributes = True

class TagUpdate(BaseModel):
    name: Optional[str] = None
    is_hidden: Optional[bool] = None


# Media Attachment Schemas
class MediaAttachmentResponse(BaseModel):
    id: UUID
    file_url: str
    file_type: str
    file_name: Optional[str]
    file_size: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


# Contact Schemas
class ContactBase(BaseModel):
    name: str
    email: Optional[EmailStr] = None
    role_company: Optional[str] = None
    mobile: Optional[str] = None
    linkedin_url: Optional[str] = None
    meeting_context: Optional[str] = None
    meeting_latitude: Optional[float] = None
    meeting_longitude: Optional[float] = None
    meeting_location_name: Optional[str] = None


class ContactCreate(ContactBase):
    event_id: Optional[UUID] = None
    tags: Optional[List[str]] = []


class ContactResponse(ContactBase):
    id: UUID
    user_id: UUID
    event_id: Optional[UUID]
    contact_photo_url: Optional[str]
    meeting_date: datetime
    created_at: datetime
    updated_at: datetime
    tags: List[TagResponse] = []
    media: List[MediaAttachmentResponse] = []
    meeting_latitude: Optional[float] = None
    meeting_longitude: Optional[float] = None
    meeting_location_name: Optional[str] = None

    class Config:
        from_attributes = True


# Follow-up Schemas
class FollowUpBase(BaseModel):
    message: str
    follow_up_date: Optional[date] = None


class FollowUpCreate(FollowUpBase):
    contact_id: UUID


class FollowUpResponse(FollowUpBase):
    id: UUID
    contact_id: UUID
    user_id: UUID
    status: str
    sent_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FollowUpUpdate(BaseModel):
    status: Optional[str] = None
    sent_at: Optional[datetime] = None

