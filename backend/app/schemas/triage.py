"""
Pydantic schemas for ticket triaging API.
Request and response models for Module 8.
"""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from enum import Enum


class RoutingActionEnum(str, Enum):
    """Routing actions based on confidence score."""
    AUTO_RESOLVE = "auto_resolve"
    ROUTE_WITH_SUGGESTION = "route_with_suggestion"
    ESCALATE_TO_HUMAN = "escalate_to_human"


class TriageJobStatusEnum(str, Enum):
    """Async triage job lifecycle states."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TriageRequest(BaseModel):
    """Request schema for ticket triaging."""
    
    subject: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Ticket subject/title",
        examples=["User cannot login - password expired"]
    )
    
    description: str = Field(
        default="",
        max_length=5000,
        description="Detailed ticket description (optional)",
        examples=["Employee jsmith@jadeglobal.com unable to access email. Password has expired."]
    )
    
    verbose: bool = Field(
        default=False,
        description="Enable verbose logging for debugging"
    )
    
    max_iterations: int = Field(
        default=10,
        ge=1,
        le=20,
        description="Maximum agent reasoning iterations"
    )
    
    @field_validator('subject')
    @classmethod
    def subject_not_empty(cls, v: str) -> str:
        """Ensure subject is not just whitespace."""
        if not v or not v.strip():
            raise ValueError("Subject cannot be empty")
        return v.strip()
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "subject": "Cannot access VPN",
                    "description": "Remote employee getting timeout error when connecting to company VPN",
                    "verbose": False,
                    "max_iterations": 10
                },
                {
                    "subject": "Password reset needed",
                    "description": "",
                    "verbose": False,
                    "max_iterations": 8
                }
            ]
        }
    }


class TriageResponse(BaseModel):
    """Response schema for ticket triaging."""
    
    queue: str = Field(
        ...,
        description="Assigned support queue",
        examples=["AMER - STACK Service Desk Group"]
    )
    
    category: str = Field(
        ...,
        description="High-level ticket category",
        examples=["Access Issues"]
    )
    
    sub_category: str = Field(
        ...,
        description="Specific sub-category",
        examples=["Password Reset"]
    )
    
    resolution_steps: List[str] = Field(
        ...,
        min_length=1,
        description="Ordered list of resolution steps",
        examples=[
            [
                "Verify user identity (ask security questions)",
                "Reset password in Active Directory",
                "Confirm user can login successfully"
            ]
        ]
    )
    
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0 to 1.0)",
        examples=[0.92]
    )
    
    sop_reference: str = Field(
        ...,
        description="SOP section reference or 'No specific SOP'",
        examples=["Section 1.1 - Password Reset"]
    )
    
    reasoning: str = Field(
        ...,
        min_length=10,
        description="Explanation of the triaging decision",
        examples=["Clear password reset request. Matches SOP 1.1 exactly. High confidence based on similar ticket patterns."]
    )
    
    routing_action: RoutingActionEnum = Field(
        ...,
        description="Recommended routing action based on confidence",
        examples=["auto_resolve"]
    )
    
    validation_errors: List[str] = Field(
        default_factory=list,
        description="Any validation errors encountered"
    )
    
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the triage was performed"
    )
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "queue": "AMER - STACK Service Desk Group",
                    "category": "Access Issues",
                    "sub_category": "Password Reset",
                    "resolution_steps": [
                        "Verify user identity (ask security questions or employee ID)",
                        "Open Active Directory Users and Computers",
                        "Reset password with 'User must change password at next logon'",
                        "Confirm successful password change"
                    ],
                    "confidence": 0.92,
                    "sop_reference": "Section 1.1 - Password Reset",
                    "reasoning": "Clear password reset request. Matches SOP 1.1 exactly. High confidence.",
                    "routing_action": "auto_resolve",
                    "validation_errors": [],
                    "timestamp": "2024-01-15T10:30:00Z"
                }
            ]
        }
    }


class AsyncTriageStartResponse(BaseModel):
    """Response returned when async triage job is accepted."""
    job_id: str = Field(..., description="Unique triage job identifier")
    status: TriageJobStatusEnum = Field(..., description="Current job status")
    poll_url: str = Field(..., description="Endpoint to poll for job completion")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AsyncTriageJobStatusResponse(BaseModel):
    """Polling response for async triage jobs."""
    job_id: str = Field(..., description="Unique triage job identifier")
    status: TriageJobStatusEnum = Field(..., description="Current job status")
    result: Optional[TriageResponse] = Field(default=None, description="Final triage result when completed")
    error: Optional[str] = Field(default=None, description="Failure details when status is failed")
    created_at: datetime = Field(..., description="Job creation time")
    started_at: Optional[datetime] = Field(default=None, description="Job start time")
    completed_at: Optional[datetime] = Field(default=None, description="Job completion time")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TicketListItemResponse(BaseModel):
    """Tickets list item schema for Tickets page."""

    id: str = Field(..., description="Ticket identifier")
    subject: str = Field(..., description="Ticket subject")
    queue: str = Field(..., description="Assigned or raw queue")
    category: str = Field(..., description="Assigned or raw category")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    routing: str = Field(..., description="Routing state: auto-resolved, routed, escalated")
    created_at: datetime = Field(..., description="Ticket creation timestamp")
    description: Optional[str] = Field(default=None, description="Ticket description")
    sub_category: Optional[str] = Field(default=None, description="Ticket sub-category")
    sop_reference: Optional[str] = Field(default=None, description="SOP reference")
    reasoning: Optional[str] = Field(default=None, description="Routing reasoning")
    resolution_steps: List[str] = Field(default_factory=list, description="Suggested resolution steps")


class TicketsListResponse(BaseModel):
    """Paginated tickets response."""

    tickets: List[TicketListItemResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    limit: int = Field(..., ge=1, le=100)


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: str = Field(
        default="healthy",
        description="Service health status"
    )
    
    version: str = Field(
        ...,
        description="API version"
    )
    
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Current server time"
    )
    
    components: dict = Field(
        default_factory=dict,
        description="Status of individual components"
    )


class ErrorResponse(BaseModel):
    """Error response schema."""
    
    error: str = Field(
        ...,
        description="Error type",
        examples=["ValidationError"]
    )
    
    message: str = Field(
        ...,
        description="Human-readable error message",
        examples=["Subject cannot be empty"]
    )
    
    details: Optional[dict] = Field(
        default=None,
        description="Additional error details"
    )
    
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the error occurred"
    )


class QueuesResponse(BaseModel):
    """Available queues response."""
    
    queues: List[str] = Field(
        ...,
        description="List of available support queues"
    )
    
    count: int = Field(
        ...,
        description="Total number of queues"
    )


class StatsResponse(BaseModel):
    """Agent statistics response."""
    
    total_tickets_in_db: int = Field(
        ...,
        description="Total historical tickets in database"
    )
    
    total_sop_chunks: int = Field(
        ...,
        description="Total SOP procedure chunks available"
    )
    
    llm_provider: str = Field(
        ...,
        description="Currently configured LLM provider"
    )
    
    embedding_provider: str = Field(
        ...,
        description="Currently configured embedding provider"
    )
    
    available_tools: List[str] = Field(
        ...,
        description="Available agent tools"
    )


__all__ = [
    'TriageRequest',
    'TriageResponse',
    'AsyncTriageStartResponse',
    'AsyncTriageJobStatusResponse',
    'TicketListItemResponse',
    'TicketsListResponse',
    'HealthResponse',
    'ErrorResponse',
    'QueuesResponse',
    'StatsResponse',
    'RoutingActionEnum',
    'TriageJobStatusEnum'
]
