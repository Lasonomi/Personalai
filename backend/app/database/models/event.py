"""Event model"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Uuid
from sqlalchemy.sql import func
import uuid
import enum
from app.database.connection import Base


class EventCategory(str, enum.Enum):
    ACADEMIC = "ACADEMIC"
    PERSONAL = "PERSONAL"
    WORK = "WORK"
    SOCIAL = "SOCIAL"
    EVENT = "EVENT"
    HEALTH = "HEALTH"
    STUDY = "STUDY"
    MEETING = "MEETING"
    TRAVEL = "TRAVEL"
    OTHER = "OTHER"


class Event(Base):
    __tablename__ = "events"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(32), default="OTHER")
    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=True)
    location = Column(String(255), nullable=True)
    recurrence = Column(String(64), nullable=True)  # e.g. WEEKLY:MONDAY
    status = Column(String(32), default="ACTIVE")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
