"""Conversation & Message models"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON, Uuid
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    platform = Column(String(32), nullable=False)  # telegram | discord
    platform_chat_id = Column(String(128), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Message(Base):
    __tablename__ = "messages"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String(16), nullable=False)  # USER | ASSISTANT | SYSTEM | TOOL
    content = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
