"""Reminder model"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Uuid
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    event_id = Column(Uuid(as_uuid=True), ForeignKey("events.id"), nullable=True)
    task_id = Column(Uuid(as_uuid=True), ForeignKey("tasks.id"), nullable=True)
    title = Column(String(255), nullable=False)
    remind_at = Column(DateTime(timezone=True), nullable=False, index=True)
    delivery_platform = Column(String(32), nullable=True)
    delivery_user_id = Column(String(128), nullable=True)
    status = Column(String(32), default="PENDING")  # PENDING | SENDING | SENT | CANCELLED
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    attempt_count = Column(Integer, default=0, nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
