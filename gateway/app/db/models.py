"""SQLAlchemy ORM models for persistent storage."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class SessionModel(Base):
    __tablename__ = "sessions"

    session_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False, default="default", index=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    pending_gate_info = Column(JSONB, nullable=True)
    execution_snapshot = Column(JSONB, nullable=True)

    messages = relationship(
        "MessageModel",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="MessageModel.id",
    )


class MessageModel(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        String(64),
        ForeignKey("sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id = Column(String(64), nullable=False, default="default", index=True)
    role = Column(String(32), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    session = relationship("SessionModel", back_populates="messages")


class DeadLetterModel(Base):
    __tablename__ = "dead_letters"

    dlq_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False, default="default", index=True)
    task_id = Column(String(128), nullable=False)
    module_id = Column(String(128), nullable=False, index=True)
    error = Column(Text, nullable=False)
    retry_count = Column(Integer, default=0)
    payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    replayed = Column(Boolean, default=False)
