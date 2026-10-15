"""Memory model"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Float, Uuid, JSON
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class Memory(Base):
    __tablename__ = "memories"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    category = Column(String(32), default="OTHER", index=True)
    importance = Column(Float, default=0.5)
    embedding = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
