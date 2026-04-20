"""Conversation state model for Google Chat webhook interactions."""

from datetime import datetime
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import relationship

from app.db.session import Base


class ChatConversation(Base):
    """Stores per-user Google Chat conversation state for triage flow."""

    __tablename__ = "chat_conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    google_chat_space_id = Column(String(255), nullable=False, index=True)
    google_chat_user_id = Column(String(255), nullable=False, index=True)
    google_chat_thread_id = Column(String(255), nullable=True, index=True)
    current_step = Column(String(50), nullable=False, default="welcome")
    collected_data = Column(JSON, nullable=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, nullable=False, default=True)

    ticket = relationship("Ticket", foreign_keys=[ticket_id])

    __table_args__ = (
        Index("idx_chat_conversation_space_user", "google_chat_space_id", "google_chat_user_id"),
        Index("idx_chat_conversation_active", "is_active"),
    )

    def __repr__(self) -> str:
        return (
            f"<ChatConversation(id={self.id}, space='{self.google_chat_space_id}', "
            f"user='{self.google_chat_user_id}', step='{self.current_step}')>"
        )

