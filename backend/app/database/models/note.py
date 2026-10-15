"""Note model"""
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Text, Uuid
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class Note(Base):
    __tablename__ = "notes"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(32), default="OTHER")
    embedding = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
