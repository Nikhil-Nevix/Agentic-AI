"""
SQLAlchemy models for Service Desk Triaging Agent.
Defines database schema for tickets, triage results, audit logs, and SOP chunks.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, 
    ForeignKey, JSON, Index, Enum
)
from sqlalchemy.orm import relationship
from app.db.session import Base


class Ticket(Base):
    """
    Support ticket records from Stack_Tickets.xlsx.
    Stores raw ticket data before AI processing.
    """
    __tablename__ = "tickets"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    subject = Column(String(500), nullable=False, index=True)
    description = Column(Text, nullable=True)  # 200 nulls in dataset
    raw_group = Column(String(100), nullable=True)
    raw_category = Column(String(100), nullable=True)
    raw_subcategory = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    triage_results = relationship("TriageResult", back_populates="ticket", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="ticket", cascade="all, delete-orphan")
    
    # Indexes for search performance
    __table_args__ = (
        Index("idx_ticket_subject", "subject"),
        Index("idx_ticket_created", "created_at"),
        Index("idx_ticket_group", "raw_group"),
    )
    
    def __repr__(self) -> str:
        return f"<Ticket(id={self.id}, subject='{self.subject[:50]}...')>"


class TriageResult(Base):
    """
    AI agent triage output.
    Stores queue assignment, resolution steps, and confidence scores.
    """
    __tablename__ = "triage_results"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    
    # AI predictions
    queue = Column(String(100), nullable=False, index=True)
    category = Column(String(100), nullable=True)
    sub_category = Column(String(100), nullable=True)
    
    # Resolution guidance
    resolution_steps = Column(JSON, nullable=False)  # List[str]
    sop_reference = Column(String(200), nullable=True)  # e.g. "Section 1.2 - Account Locked"
    reasoning = Column(Text, nullable=True)  # Agent's explanation
    
    # Confidence & routing
    confidence = Column(Float, nullable=False)  # 0.0 - 1.0
    routing_action = Column(
        Enum("auto_resolve", "suggest", "escalate", name="routing_action_enum"),
        nullable=False,
        index=True
    )
    
    # Metadata
    model_used = Column(String(50), nullable=True)  # gpt-4o, llama-3.1-70b, etc.
    processing_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    ticket = relationship("Ticket", back_populates="triage_results")
    
    __table_args__ = (
        Index("idx_triage_ticket", "ticket_id"),
        Index("idx_triage_confidence", "confidence"),
        Index("idx_triage_created", "created_at"),
    )
    
    def __repr__(self) -> str:
        return f"<TriageResult(id={self.id}, queue='{self.queue}', confidence={self.confidence})>"


class AuditLog(Base):
    """
    Audit trail for all ticket operations.
    Tracks who did what and when for compliance.
    """
    __tablename__ = "audit_log"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    
    action = Column(String(100), nullable=False)  # created, triaged, escalated, resolved
    performed_by = Column(String(100), nullable=False)  # system, user_id, agent_name
    details = Column(JSON, nullable=True)  # Additional context
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Relationships
    ticket = relationship("Ticket", back_populates="audit_logs")
    
    __table_args__ = (
        Index("idx_audit_ticket", "ticket_id"),
        Index("idx_audit_action", "action"),
        Index("idx_audit_created", "created_at"),
    )
    
    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action='{self.action}', by='{self.performed_by}')>"


class SOPChunk(Base):
    """
    Parsed SOP procedure chunks from Common.pdf.
    Each chunk represents one searchable SOP procedure.
    """
    __tablename__ = "sop_chunks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    section_num = Column(String(20), nullable=False, index=True)  # 1.1, 1.2, 2.1, etc.
    title = Column(String(300), nullable=False)
    content = Column(Text, nullable=False)
    
    # FAISS metadata
    embedding_id = Column(Integer, nullable=True)  # Index in FAISS vector store
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("idx_sop_section", "section_num"),
        Index("idx_sop_embedding", "embedding_id"),
    )
    
    def __repr__(self) -> str:
        return f"<SOPChunk(id={self.id}, section='{self.section_num}', title='{self.title[:50]}...')>"
