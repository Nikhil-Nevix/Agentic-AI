"""
Ticket triaging API router.
Main endpoints for Module 8.
"""

from fastapi import APIRouter, HTTPException, status, BackgroundTasks, Query
from loguru import logger
from dataclasses import dataclass
from uuid import uuid4

from app.schemas.triage import (
    TriageRequest,
    TriageResponse,
    AsyncTriageStartResponse,
    AsyncTriageJobStatusResponse,
    TicketsListResponse,
    TicketListItemResponse,
    TriageJobStatusEnum,
    HealthResponse,
    ErrorResponse,
    QueuesResponse,
    StatsResponse,
    QueueAnalyticsResponse,
    QueueAnalyticsItemResponse,
    RoutingActionEnum,
    WebChatRequest,
    WebChatResponse,
    WebChatHistoryClearRequest,
    WebChatHistoryClearResponse,
)
from app.agent.triage_agent import triage_ticket, get_triage_agent
from app.agent.prompts import VALIDATION_RULES
from app.config import settings
from app.db.session import SessionLocal
from app.models import Ticket as TicketModel, TriageResult as TriageResultModel
from app.services.triage_service import triage_ticket_sync
from app.services.google_chat_service import process_web_chat_event, clear_web_chat_history
from datetime import datetime
from typing import Optional, Dict
from datetime import timedelta, date
from sqlalchemy import func, and_

router = APIRouter(
    prefix="/api/v1",
    tags=["triage"],
    responses={
        500: {"model": ErrorResponse, "description": "Internal server error"},
        400: {"model": ErrorResponse, "description": "Bad request"}
    }
)


@dataclass
class TriageJob:
    """In-memory async triage job state."""
    id: str
    status: TriageJobStatusEnum
    request: TriageRequest
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[TriageResponse] = None
    error: Optional[str] = None


TRIAGE_JOBS: Dict[str, TriageJob] = {}


def _map_persisted_routing_to_response(value: str) -> RoutingActionEnum:
    mapping = {
        "auto_resolve": RoutingActionEnum.AUTO_RESOLVE,
        "suggest": RoutingActionEnum.ROUTE_WITH_SUGGESTION,
        "escalate": RoutingActionEnum.ESCALATE_TO_HUMAN,
    }
    return mapping.get(value, RoutingActionEnum.ESCALATE_TO_HUMAN)


def _run_triage_job(job_id: str) -> None:
    """Background runner for async triage jobs."""
    job = TRIAGE_JOBS.get(job_id)
    if not job:
        return
    try:
        job.status = TriageJobStatusEnum.RUNNING
        job.started_at = datetime.utcnow()
        persisted = triage_ticket_sync(
            subject=job.request.subject,
            description=job.request.description,
        )
        triage_result = persisted["triage_result"]
        job.result = TriageResponse(
            queue=str(triage_result["queue"]),
            category=str(triage_result["category"]),
            sub_category=str(triage_result["sub_category"]),
            resolution_steps=[str(step) for step in (triage_result.get("resolution_steps") or [])],
            confidence=float(triage_result["confidence"]),
            sop_reference=str(triage_result["sop_reference"]),
            reasoning=str(triage_result["reasoning"]),
            routing_action=_map_persisted_routing_to_response(str(triage_result.get("routing_action", ""))),
            validation_errors=[],
            timestamp=datetime.utcnow(),
        )
        job.status = TriageJobStatusEnum.COMPLETED
        job.completed_at = datetime.utcnow()
        logger.success(f"Async triage job completed: {job_id}")
    except Exception as triage_error:
        job.status = TriageJobStatusEnum.FAILED
        job.error = str(triage_error)
        job.completed_at = datetime.utcnow()
        logger.error(f"Async triage job failed: {job_id} | {triage_error}")


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Check API health and component status"
)
async def health_check():
    """
    Check if the API and all components are operational.
    
    Returns:
        HealthResponse with status of all components
    """
    try:
        # Check agent initialization
        agent = get_triage_agent()
        agent_status = "healthy" if agent else "unhealthy"
        
        # Check vector stores
        from app.vector.faiss_store import FAISSStore
        try:
            ticket_store = FAISSStore("tickets")
            sop_store = FAISSStore("sop")
            vector_status = "healthy"
        except Exception as e:
            logger.warning(f"Vector store check failed: {e}")
            vector_status = "degraded"
        
        components = {
            "agent": agent_status,
            "vector_stores": vector_status,
            "llm_provider": settings.llm_provider,
            "embedding_provider": settings.embedding_provider
        }
        
        overall_status = "healthy" if all(
            v == "healthy" for v in [agent_status, vector_status]
        ) else "degraded"
        
        return HealthResponse(
            status=overall_status,
            version=settings.app_version,
            timestamp=datetime.utcnow(),
            components=components
        )
    
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            version=settings.app_version,
            timestamp=datetime.utcnow(),
            components={"error": str(e)}
        )


@router.post(
    "/triage",
    response_model=TriageResponse,
    status_code=status.HTTP_200_OK,
    summary="Triage a Ticket",
    description="Analyze a support ticket and provide triaging recommendations",
    responses={
        200: {
            "description": "Ticket successfully triaged",
            "content": {
                "application/json": {
                    "example": {
                        "queue": "AMER - STACK Service Desk Group",
                        "category": "Access Issues",
                        "sub_category": "Password Reset",
                        "resolution_steps": [
                            "Verify user identity",
                            "Reset password in Active Directory",
                            "Confirm successful login"
                        ],
                        "confidence": 0.92,
                        "sop_reference": "Section 1.1 - Password Reset",
                        "reasoning": "Clear password reset request",
                        "routing_action": "auto_resolve",
                        "validation_errors": [],
                        "timestamp": "2024-01-15T10:30:00Z"
                    }
                }
            }
        }
    }
)
async def triage_ticket_endpoint(request: TriageRequest):
    """
    Triage a support ticket using the AI agent.
    
    The agent will:
    1. Search for similar historical tickets
    2. Find relevant SOP procedures
    3. Analyze the ticket and provide routing recommendations
    4. Return actionable resolution steps
    
    Args:
        request: TriageRequest with subject, description, and options
        
    Returns:
        TriageResponse with queue, category, steps, confidence, etc.
        
    Raises:
        HTTPException: If triaging fails
    """
    try:
        logger.info(f"Triaging ticket: '{request.subject[:60]}...'")
        
        # Perform triaging
        result = triage_ticket(
            subject=request.subject,
            description=request.description,
            verbose=request.verbose
        )
        
        # Convert to response model
        response = TriageResponse(
            queue=result.queue,
            category=result.category,
            sub_category=result.sub_category,
            resolution_steps=result.resolution_steps,
            confidence=result.confidence,
            sop_reference=result.sop_reference,
            reasoning=result.reasoning,
            routing_action=result.routing_action,
            validation_errors=result.validation_errors,
            timestamp=datetime.utcnow()
        )
        
        logger.success(
            f"Ticket triaged: {result.queue} | "
            f"Confidence: {result.confidence:.2%} | "
            f"Action: {result.routing_action.value}"
        )
        
        return response
    
    except Exception as e:
        logger.error(f"Triage failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "TriageError",
                "message": f"Failed to triage ticket: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            }
        )


@router.post(
    "/chatbot/message",
    response_model=WebChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Process web chatbot message",
    description="Process floating web chatbot user message/action using the same state machine as Google Chat",
)
async def web_chatbot_message_endpoint(request: WebChatRequest):
    """Route frontend chatbot interactions through the existing conversation engine."""
    try:
        response = process_web_chat_event(
            user_id=request.user_id,
            session_id=request.session_id,
            message=request.message,
            action=request.action,
        )
        return WebChatResponse(**response)
    except Exception as e:
        logger.error(f"Web chatbot request failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "WebChatError",
                "message": "Unable to process chatbot request right now.",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


@router.post(
    "/chatbot/history/clear",
    response_model=WebChatHistoryClearResponse,
    status_code=status.HTTP_200_OK,
    summary="Clear web chatbot history",
    description="Delete persisted web chatbot history for a user/session",
)
async def clear_web_chatbot_history_endpoint(request: WebChatHistoryClearRequest):
    """Clear web chatbot conversation history records from database."""
    try:
        deleted_count = clear_web_chat_history(
            user_id=request.user_id,
            session_id=request.session_id,
        )
        return WebChatHistoryClearResponse(status="success", deleted_count=deleted_count)
    except Exception as e:
        logger.error(f"Web chatbot history clear failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "WebChatHistoryClearError",
                "message": "Unable to clear chatbot history right now.",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


@router.post(
    "/tickets/triage",
    response_model=AsyncTriageStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start Async Triage Job",
    description="Queue a ticket triage job and return a polling token"
)
async def triage_ticket_async_endpoint(request: TriageRequest, background_tasks: BackgroundTasks):
    """Queue an asynchronous triage job and return a job id for polling."""
    job_id = str(uuid4())
    TRIAGE_JOBS[job_id] = TriageJob(
        id=job_id,
        status=TriageJobStatusEnum.QUEUED,
        request=request,
        created_at=datetime.utcnow()
    )
    background_tasks.add_task(_run_triage_job, job_id)
    logger.info(f"Queued async triage job: {job_id}")
    return AsyncTriageStartResponse(
        job_id=job_id,
        status=TriageJobStatusEnum.QUEUED,
        poll_url=f"/api/v1/tickets/triage/{job_id}",
        timestamp=datetime.utcnow()
    )


@router.get(
    "/tickets/triage/{job_id}",
    response_model=AsyncTriageJobStatusResponse,
    summary="Get Async Triage Job Status",
    description="Poll an async triage job until completion"
)
async def triage_ticket_async_status_endpoint(job_id: str):
    """Return current status for a previously queued triage job."""
    job = TRIAGE_JOBS.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "JobNotFound",
                "message": f"No triage job found for id: {job_id}",
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    return AsyncTriageJobStatusResponse(
        job_id=job.id,
        status=job.status,
        result=job.result,
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        timestamp=datetime.utcnow()
    )


@router.get(
    "/tickets",
    response_model=TicketsListResponse,
    summary="List Tickets",
    description="Fetch paginated tickets with optional filters for queue/category/search"
)
async def list_tickets(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    queue: str = Query(default=""),
    category: str = Query(default=""),
    search: str = Query(default="")
):
    """Return paginated tickets for frontend tickets page."""
    db = SessionLocal()
    try:
        query = db.query(TicketModel)

        if queue:
            query = query.filter(TicketModel.raw_group == queue)
        if category:
            query = query.filter(TicketModel.raw_category == category)
        if search:
            like_search = f"%{search}%"
            query = query.filter(
                (TicketModel.subject.ilike(like_search)) |
                (TicketModel.description.ilike(like_search))
            )

        total = query.count()
        rows = (
            query
            .order_by(TicketModel.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )

        tickets: list[TicketListItemResponse] = []
        for ticket in rows:
            latest_triage = (
                db.query(TriageResultModel)
                .filter(TriageResultModel.ticket_id == ticket.id)
                .order_by(TriageResultModel.created_at.desc())
                .first()
            )

            routing = "routed"
            confidence = 0.7
            reasoning = ""
            sop_reference = ""
            resolution_steps: list[str] = []
            category_value = ticket.raw_category or "General Incident"
            sub_category_value = ticket.raw_subcategory or ""

            if latest_triage:
                confidence = latest_triage.confidence
                reasoning = latest_triage.reasoning or ""
                sop_reference = latest_triage.sop_reference or ""
                resolution_steps = latest_triage.resolution_steps or []
                category_value = latest_triage.category or category_value
                sub_category_value = latest_triage.sub_category or sub_category_value

                if latest_triage.routing_action == "auto_resolve":
                    routing = "auto-resolved"
                elif latest_triage.routing_action == "escalate":
                    routing = "escalated"
                else:
                    routing = "routed"

            tickets.append(
                TicketListItemResponse(
                    id=f"INC-{ticket.id:06d}",
                    subject=ticket.subject,
                    queue=ticket.raw_group or "STACK Service Desk",
                    category=category_value,
                    confidence=confidence,
                    routing=routing,
                    created_at=ticket.created_at,
                    description=ticket.description or "",
                    sub_category=sub_category_value,
                    sop_reference=sop_reference,
                    reasoning=reasoning,
                    resolution_steps=resolution_steps
                )
            )

        return TicketsListResponse(
            tickets=tickets,
            total=total,
            page=page,
            limit=limit
        )
    except Exception as e:
        logger.error(f"Failed to list tickets: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "TicketsListError",
                "message": f"Failed to retrieve tickets: {str(e)}"
            }
        )
    finally:
        db.close()


@router.get(
    "/queues",
    response_model=QueuesResponse,
    summary="Get Available Queues",
    description="List all available support queues"
)
async def get_queues():
    """
    Get list of all available support queues.
    
    Returns:
        QueuesResponse with list of queue names
    """
    queues = VALIDATION_RULES["queue"]["must_be_one_of"]
    
    return QueuesResponse(
        queues=queues,
        count=len(queues)
    )


@router.get(
    "/queues/analytics",
    response_model=QueueAnalyticsResponse,
    summary="Get Queue Analytics",
    description="Queue KPIs and trend data for a selected date range"
)
async def get_queue_analytics(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
):
    """Return queue cards and trends for selected date range."""
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "InvalidDateFormat",
                "message": "start_date and end_date must be in YYYY-MM-DD format",
            },
        )

    if end < start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "InvalidDateRange",
                "message": "end_date must be greater than or equal to start_date",
            },
        )

    db = SessionLocal()
    try:
        start_dt = datetime.combine(start, datetime.min.time())
        end_dt = datetime.combine(end, datetime.max.time())

        labels: list[str] = []
        cursor: date = start
        while cursor <= end:
            labels.append(cursor.strftime("%d %b"))
            cursor += timedelta(days=1)

        ticket_rows = (
            db.query(TicketModel)
            .filter(and_(TicketModel.created_at >= start_dt, TicketModel.created_at <= end_dt))
            .all()
        )
        ticket_ids = [ticket.id for ticket in ticket_rows]
        total_open = len(ticket_rows)

        triage_rows = []
        if ticket_ids:
            triage_rows = (
                db.query(TriageResultModel)
                .filter(TriageResultModel.ticket_id.in_(ticket_ids))
                .all()
            )

        triage_by_ticket = {}
        for triage in triage_rows:
            triage_by_ticket[triage.ticket_id] = triage

        queue_buckets: dict[str, dict] = {}

        for ticket in ticket_rows:
            triage = triage_by_ticket.get(ticket.id)
            queue_name = (triage.queue if triage and triage.queue else ticket.raw_group) or "Other Queues"
            category_name = (triage.category if triage and triage.category else ticket.raw_category) or "General Incident"
            confidence = float(triage.confidence) if triage and triage.confidence is not None else 0.0
            day_key = ticket.created_at.date()

            if queue_name not in queue_buckets:
                queue_buckets[queue_name] = {
                    "ticket_count": 0,
                    "confidence_total": 0.0,
                    "confidence_count": 0,
                    "categories": {},
                    "day_counts": {},
                }

            bucket = queue_buckets[queue_name]
            bucket["ticket_count"] += 1
            bucket["confidence_total"] += confidence
            bucket["confidence_count"] += 1
            bucket["categories"][category_name] = bucket["categories"].get(category_name, 0) + 1
            bucket["day_counts"][day_key] = bucket["day_counts"].get(day_key, 0) + 1

        queues: list[QueueAnalyticsItemResponse] = []
        for queue_name, bucket in queue_buckets.items():
            avg_confidence = (
                bucket["confidence_total"] / bucket["confidence_count"]
                if bucket["confidence_count"] > 0
                else 0.0
            )
            top_category = "General Incident"
            if bucket["categories"]:
                top_category = max(bucket["categories"], key=bucket["categories"].get)

            trend_values: list[int] = []
            trend_cursor = start
            while trend_cursor <= end:
                trend_values.append(int(bucket["day_counts"].get(trend_cursor, 0)))
                trend_cursor += timedelta(days=1)

            queues.append(
                QueueAnalyticsItemResponse(
                    name=queue_name,
                    ticket_count=int(bucket["ticket_count"]),
                    avg_confidence=max(0.0, min(float(avg_confidence), 1.0)),
                    top_category=top_category,
                    trend=trend_values,
                )
            )

        queues.sort(key=lambda item: item.ticket_count, reverse=True)

        sla_breached = sum(1 for triage in triage_rows if triage.routing_action == "escalate")

        avg_resolution_hours = (
            (sum((triage.processing_time_ms or 0) for triage in triage_rows) / 3600000.0) / len(triage_rows)
            if triage_rows
            else 0.0
        )

        return QueueAnalyticsResponse(
            start_date=start_date,
            end_date=end_date,
            labels=labels,
            total_open=int(total_open),
            sla_breached=int(sla_breached),
            avg_resolution_hours=round(float(avg_resolution_hours), 2),
            queues=queues,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch queue analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "QueueAnalyticsError",
                "message": f"Failed to retrieve queue analytics: {str(e)}"
            }
        )
    finally:
        db.close()


@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="Get Agent Statistics",
    description="Get statistics about the triaging agent and available data"
)
async def get_stats():
    """
    Get statistics about the agent and its data sources.
    
    Returns:
        StatsResponse with counts and configuration info
    """
    try:
        from app.vector.faiss_store import FAISSStore
        
        # Get vector store stats
        ticket_store = FAISSStore("tickets")
        ticket_store.load()  # Load the index
        
        sop_store = FAISSStore("sop")
        sop_store.load()  # Load the index
        
        ticket_count = ticket_store.index.ntotal if ticket_store.index else 0
        sop_count = sop_store.index.ntotal if sop_store.index else 0
        
        # Get agent info
        agent = get_triage_agent()
        tool_names = [tool.name for tool in agent.tools]
        
        return StatsResponse(
            total_tickets_in_db=ticket_count,
            total_sop_chunks=sop_count,
            llm_provider=settings.llm_provider,
            embedding_provider=settings.embedding_provider,
            available_tools=tool_names
        )
    
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "StatsError",
                "message": f"Failed to retrieve statistics: {str(e)}"
            }
        )


@router.get(
    "/",
    summary="API Root",
    description="API information and available endpoints"
)
async def root():
    """
    Get API root information.
    
    Returns:
        API metadata and available endpoints
    """
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "endpoints": {
            "health": "/api/v1/health",
            "triage": "/api/v1/triage",
            "queues": "/api/v1/queues",
            "stats": "/api/v1/stats",
            "docs": "/docs",
            "redoc": "/redoc"
        },
        "description": "AI-powered ticket triaging agent for IT Service Desk"
    }


__all__ = ['router']
