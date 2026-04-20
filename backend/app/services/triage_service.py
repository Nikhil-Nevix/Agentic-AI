"""Service helpers to run triage and persist ticket lifecycle records."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import BackgroundTasks
from loguru import logger

from app.agent.triage_agent import triage_ticket
from app.db.session import SessionLocal
from app.config import settings
from app.models import AuditLog as AuditLogModel
from app.models import Ticket as TicketModel
from app.models import TriageResult as TriageResultModel
from app.schemas.triage import TriageJobStatusEnum
from app.services.google_chat_outbound_service import send_triage_notification


ASYNC_TRIAGE_JOBS: Dict[str, Dict[str, Any]] = {}
ASYNC_TRIAGE_EXECUTOR = ThreadPoolExecutor(max_workers=4)


def _map_routing_action(routing_action: str) -> str:
    mapping = {
        "auto_resolve": "auto_resolve",
        "route_with_suggestion": "suggest",
        "escalate_to_human": "escalate",
    }
    return mapping.get(routing_action, "escalate")


def _persist_ticket_and_result(
    subject: str,
    description: str,
    queue_override: Optional[str] = None,
    category_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Run triage and save ticket, triage_result, and audit_log records."""
    db = SessionLocal()
    try:
        triage = triage_ticket(subject=subject, description=description, verbose=False)
        queue_value = queue_override if queue_override and queue_override != "AI Suggested" else triage.queue
        category_value = (
            category_override if category_override and category_override != "AI Suggested" else triage.category
        )

        ticket = TicketModel(
            subject=subject,
            description=description,
            raw_group=queue_value,
            raw_category=category_value,
            raw_subcategory=triage.sub_category,
            created_at=datetime.utcnow(),
        )
        db.add(ticket)
        db.flush()

        triage_result = TriageResultModel(
            ticket_id=ticket.id,
            queue=queue_value,
            category=category_value,
            sub_category=triage.sub_category,
            resolution_steps=triage.resolution_steps,
            sop_reference=triage.sop_reference,
            reasoning=triage.reasoning,
            confidence=triage.confidence,
            routing_action=_map_routing_action(triage.routing_action.value),
            model_used="chatbot",
            processing_time_ms=None,
            created_at=datetime.utcnow(),
        )
        db.add(triage_result)

        audit = AuditLogModel(
            ticket_id=ticket.id,
            action="chatbot_triage_created",
            performed_by="google_chat_bot",
            details={
                "source": "google_chat",
                "queue": queue_value,
                "category": category_value,
                "sub_category": triage.sub_category,
                "confidence": triage.confidence,
            },
            created_at=datetime.utcnow(),
        )
        db.add(audit)
        db.commit()
        db.refresh(ticket)
        db.refresh(triage_result)

        if settings.google_chat_notify_on_triage:
            send_triage_notification(
                ticket={
                    "id": ticket.id,
                    "subject": ticket.subject,
                },
                triage_result={
                    "queue": triage_result.queue,
                    "category": triage_result.category,
                    "sub_category": triage_result.sub_category,
                    "resolution_steps": triage_result.resolution_steps,
                    "sop_reference": triage_result.sop_reference,
                    "confidence": triage_result.confidence,
                },
            )

        return {
            "ticket": {
                "id": ticket.id,
                "subject": ticket.subject,
                "description": ticket.description,
                "raw_group": ticket.raw_group,
                "raw_category": ticket.raw_category,
                "raw_subcategory": ticket.raw_subcategory,
            },
            "triage_result": {
                "id": triage_result.id,
                "queue": triage_result.queue,
                "category": triage_result.category,
                "sub_category": triage_result.sub_category,
                "resolution_steps": triage_result.resolution_steps,
                "sop_reference": triage_result.sop_reference,
                "reasoning": triage_result.reasoning,
                "confidence": triage_result.confidence,
                "routing_action": triage_result.routing_action,
            },
        }
    except Exception as exc:
        db.rollback()
        logger.error(f"Triage persistence failed: {exc}")
        raise
    finally:
        db.close()


def triage_ticket_sync(
    subject: str,
    description: str,
    queue_override: Optional[str] = None,
    category_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Synchronous triage and persistence wrapper."""
    return _persist_ticket_and_result(
        subject=subject,
        description=description,
        queue_override=queue_override,
        category_override=category_override,
    )


def _run_async_job(
    job_id: str,
    subject: str,
    description: str,
    queue_override: Optional[str],
    category_override: Optional[str],
) -> None:
    job = ASYNC_TRIAGE_JOBS.get(job_id)
    if not job:
        return
    try:
        job["status"] = TriageJobStatusEnum.RUNNING.value
        job["started_at"] = datetime.utcnow().isoformat()
        result = triage_ticket_sync(
            subject=subject,
            description=description,
            queue_override=queue_override,
            category_override=category_override,
        )
        job["status"] = TriageJobStatusEnum.COMPLETED.value
        job["result"] = result
        job["completed_at"] = datetime.utcnow().isoformat()
    except Exception as exc:
        job["status"] = TriageJobStatusEnum.FAILED.value
        job["error"] = str(exc)
        job["completed_at"] = datetime.utcnow().isoformat()
        logger.error(f"Async chatbot triage job failed {job_id}: {exc}")


def triage_ticket_async_start(
    subject: str,
    description: str,
    background_tasks: BackgroundTasks,
    queue_override: Optional[str] = None,
    category_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Start an async triage job used by chatbot flows when needed."""
    job_id = str(uuid4())
    ASYNC_TRIAGE_JOBS[job_id] = {
        "job_id": job_id,
        "status": TriageJobStatusEnum.QUEUED.value,
        "created_at": datetime.utcnow().isoformat(),
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
    }
    background_tasks.add_task(
        _run_async_job,
        job_id,
        subject,
        description,
        queue_override,
        category_override,
    )
    return ASYNC_TRIAGE_JOBS[job_id]


def triage_ticket_async_start_threaded(
    subject: str,
    description: str,
    queue_override: Optional[str] = None,
    category_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Start an async triage job without FastAPI BackgroundTasks."""
    job_id = str(uuid4())
    ASYNC_TRIAGE_JOBS[job_id] = {
        "job_id": job_id,
        "status": TriageJobStatusEnum.QUEUED.value,
        "created_at": datetime.utcnow().isoformat(),
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
    }
    ASYNC_TRIAGE_EXECUTOR.submit(
        _run_async_job,
        job_id,
        subject,
        description,
        queue_override,
        category_override,
    )
    return ASYNC_TRIAGE_JOBS[job_id]


def triage_ticket_async_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Return async triage job status if available."""
    return ASYNC_TRIAGE_JOBS.get(job_id)
