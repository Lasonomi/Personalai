import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Uuid, UniqueConstraint
from sqlalchemy.sql import func

from app.database.connection import Base


class DailySummaryDelivery(Base):
    __tablename__ = "daily_summary_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "local_date",
            "platform",
            "platform_user_id",
            name="uq_daily_summary_recipient_day",
        ),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    local_date = Column(Date, nullable=False)
    platform = Column(String(32), nullable=False)
    platform_user_id = Column(String(128), nullable=False)
    status = Column(String(16), default="SENDING", nullable=False)
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    attempt_count = Column(Integer, default=0, nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
