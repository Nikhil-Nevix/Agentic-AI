"""Freshservice webhook router for automatic ticket triage integration."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from loguru import logger

from app.config import settings
from app.services.freshservice_service import process_freshservice_ticket_created


router = APIRouter()


def _verify_webhook_secret(incoming_secret: Optional[str]) -> None:
    expected = settings.freshservice_webhook_secret
    if not expected:
        return
    if incoming_secret != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "WebhookUnauthorized",
                "message": "Invalid Freshservice webhook secret",
            },
        )


@router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
    summary="Freshservice webhook",
    description="Receives Freshservice ticket-created events and auto-runs triage",
)
async def freshservice_webhook(
    request: Request,
    x_freshservice_secret: Optional[str] = Header(default=None),
) -> JSONResponse:
    """Handle Freshservice webhook events."""
    if not settings.freshservice_enabled:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": "FreshserviceDisabled",
                "message": "Freshservice integration is disabled",
            },
        )

    _verify_webhook_secret(x_freshservice_secret)

    try:
        payload: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "InvalidPayload",
                "message": "Invalid JSON payload",
            },
        )

    logger.info(f"Freshservice webhook received: event={payload.get('trigger_name')}")
    event_name = str(payload.get("trigger_name") or payload.get("event") or "").lower()
    if "ticket" not in event_name and payload.get("ticket") is None:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "status": "ignored",
                "message": "Event does not contain ticket payload",
            },
        )

    try:
        result = process_freshservice_ticket_created(payload)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "result": result,
            },
        )
    except HTTPException:
        raise
    except ValueError as validation_error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "ValidationError",
                "message": str(validation_error),
            },
        )
    except Exception as exc:
        logger.error(f"Freshservice webhook processing failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "FreshserviceProcessingError",
                "message": f"Failed to process Freshservice ticket: {str(exc)}",
            },
        )
