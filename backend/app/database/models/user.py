"""User & PlatformAccount models"""
from sqlalchemy import Boolean, Column, String, DateTime, ForeignKey, Text, Uuid, UniqueConstraint
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255))
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=True)
    timezone = Column(String(64), default="Asia/Jakarta")
    language = Column(String(16), default="id")
    daily_summary_enabled = Column(Boolean, default=True, nullable=False)
    university = Column(String(255), nullable=True)
    major = Column(String(255), nullable=True)
    semester = Column(String(32), nullable=True)
    preferences = Column(Text, nullable=True)  # JSON string or use JSONB
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class PlatformAccount(Base):
    __tablename__ = "platform_accounts"
    __table_args__ = (
        UniqueConstraint("platform", "platform_user_id", name="uq_platform_account_identity"),
    )
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    platform = Column(String(32), nullable=False)  # telegram | discord
    platform_user_id = Column(String(128), nullable=False)
    username = Column(String(255), nullable=True)
    linked_at = Column(DateTime(timezone=True), server_default=func.now())


class PlatformLinkCode(Base):
    __tablename__ = "platform_link_codes"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    source_platform = Column(String(32), nullable=False)
    code_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
