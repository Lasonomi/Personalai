"""Document & DocumentChunk models"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer, JSON, Uuid
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    filename = Column(String(512), nullable=False)
    file_url = Column(String(1024), nullable=True)
    file_type = Column(String(32), default="pdf")
    status = Column(String(32), default="PROCESSING")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(Uuid(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    embedding = Column(JSON, nullable=True)
    page_number = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
