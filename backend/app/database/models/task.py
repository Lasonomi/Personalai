"""Task model"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer, Uuid
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(32), default="OTHER")
    priority = Column(String(16), default="MEDIUM")  # LOW MEDIUM HIGH URGENT
    deadline = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(32), default="TODO")  # TODO IN_PROGRESS COMPLETED OVERDUE CANCELLED
    estimated_duration = Column(Integer, nullable=True)  # minutes
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
