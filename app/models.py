from sqlalchemy import Column, String, Text, Date, DateTime, Boolean, ForeignKey, Integer, Table, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base

# Association table for many-to-many relationship between contacts and tags
contact_tags = Table(
    'contact_tags',
    Base.metadata,
    Column('contact_id', UUID(as_uuid=True), ForeignKey('contacts.id', ondelete='CASCADE'), primary_key=True),
    Column('tag_id', UUID(as_uuid=True), ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True)
)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    password_hash = Column(String(255))  # Hashed password for email-based login
    role_company = Column(String(255))
    mobile = Column(String(50), index=True)
    whatsapp = Column(String(50), index=True)
    linkedin_url = Column(Text)
    about_me = Column(Text)
    profile_photo_url = Column(Text)
    oauth_provider = Column(String(50))  # 'google', 'linkedin', 'email'
    oauth_id = Column(String(255))
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    events = relationship("Event", back_populates="user", cascade="all, delete-orphan")
    contacts = relationship("Contact", back_populates="user", cascade="all, delete-orphan")
    follow_ups = relationship("FollowUp", back_populates="user", cascade="all, delete-orphan")


class Event(Base):
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    location = Column(String(255), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="events")
    contacts = relationship("Contact", back_populates="event", cascade="all, delete-orphan")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True)
    is_system_tag = Column(Boolean, default=False)
    is_hidden = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Unique constraint: name must be unique per user (or globally for system tags)
    __table_args__ = (
        {'extend_existing': True}
    )


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    event_id = Column(UUID(as_uuid=True), ForeignKey('events.id', ondelete='SET NULL'), index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255))
    role_company = Column(String(255))
    mobile = Column(String(50))
    linkedin_url = Column(Text)
    contact_photo_url = Column(Text)
    meeting_context = Column(Text)
    meeting_latitude = Column(Numeric(10, 7))
    meeting_longitude = Column(Numeric(10, 7))
    meeting_location_name = Column(String(255))  # Human-readable location name
    meeting_date = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="contacts")
    event = relationship("Event", back_populates="contacts")
    tags = relationship("Tag", secondary=contact_tags, backref="contacts")
    media_attachments = relationship("MediaAttachment", back_populates="contact", cascade="all, delete-orphan")
    follow_ups = relationship("FollowUp", back_populates="contact", cascade="all, delete-orphan")


class MediaAttachment(Base):
    __tablename__ = "media_attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id = Column(UUID(as_uuid=True), ForeignKey('contacts.id', ondelete='CASCADE'), nullable=False, index=True)
    file_url = Column(Text, nullable=False)
    file_type = Column(String(50), nullable=False)  # 'image', 'audio', 'document'
    file_name = Column(String(255))
    file_size = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    contact = relationship("Contact", back_populates="media_attachments")


class FollowUp(Base):
    __tablename__ = "follow_ups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id = Column(UUID(as_uuid=True), ForeignKey('contacts.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    message = Column(Text, nullable=False)
    follow_up_date = Column(Date)
    status = Column(String(50), default='pending')  # 'pending', 'sent', 'completed'
    sent_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    contact = relationship("Contact", back_populates="follow_ups")
    user = relationship("User", back_populates="follow_ups")

