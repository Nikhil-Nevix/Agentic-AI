"""
User model for authentication.
"""

from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Index
from app.db.session import Base


class User(Base):
    """Application user for signup/signin."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(100), nullable=False, default="Service Desk User")
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_user_email", "email"),
        Index("idx_user_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}')>"

