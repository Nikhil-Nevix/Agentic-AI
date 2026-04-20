"""Google Chat webhook router for triage chatbot interactions."""

from typing import Any, Dict

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from loguru import logger

from app.config import settings
from app.services.google_chat_service import process_google_chat_event
from app.utils.google_chat_cards import create_error_card


router = APIRouter()


def _event_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    chat_event = payload.get("chat")
    if isinstance(chat_event, dict):
        return chat_event
    return payload


def _resolve_event_type(payload: Dict[str, Any]) -> str:
    event = _event_payload(payload)
    explicit_type = str(
        event.get("type")
        or event.get("eventType")
        or event.get("event_type")
        or payload.get("type")
        or payload.get("eventType")
        or payload.get("event_type")
        or ""
    ).strip()
    if explicit_type:
        return explicit_type
    if event.get("action"):
        return "CARD_CLICKED"
    if event.get("message") or (event.get("messagePayload") or {}).get("message"):
        return "MESSAGE"
    if event.get("space") or (event.get("spaceData") or {}).get("space"):
        return "ADDED_TO_SPACE"
    return ""


def _is_addon_event(payload: Dict[str, Any]) -> bool:
    return isinstance(payload.get("chat"), dict) and isinstance(payload.get("commonEventObject"), dict)


def _wrap_addon_response(message_payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "hostAppDataAction": {
            "chatDataAction": {
                "createMessageAction": {
                    "message": message_payload,
                }
            }
        }
    }


def _card_payload_to_text(message_payload: Dict[str, Any], *, preserve_options: bool = True) -> str:
    if isinstance(message_payload.get("text"), str) and message_payload.get("text", "").strip():
        return str(message_payload["text"]).strip()

    cards = message_payload.get("cardsV2") or []
    lines: list[str] = []
    for card_entry in cards:
        card = (card_entry or {}).get("card") or {}
        header = card.get("header") or {}
        title = str(header.get("title") or "").strip()
        subtitle = str(header.get("subtitle") or "").strip()
        if title:
            lines.append(title)
        if subtitle:
            lines.append(subtitle)
        for section in card.get("sections") or []:
            for widget in section.get("widgets") or []:
                text_block = (widget.get("textParagraph") or {}).get("text")
                if text_block:
                    cleaned = str(text_block).replace("<br>", "\n").replace("<b>", "").replace("</b>", "")
                    lines.append(cleaned.strip())
                button_list = (widget.get("buttonList") or {}).get("buttons") or []
                button_texts = [str(btn.get("text", "")).strip() for btn in button_list if str(btn.get("text", "")).strip()]
                if button_texts and preserve_options:
                    lines.append("Options:\n" + "\n".join(button_texts))

    compact = [line for line in lines if line]
    if compact:
        return "\n".join(compact)
    return "Service Desk AI is online. Type 'start' to begin triage."


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Google Chat webhook health",
    description="Health check endpoint for Google Chat webhook integration.",
)
async def google_chat_webhook_health() -> JSONResponse:
    """Return health status for Google Chat webhook service."""
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "ok", "service": "google-chat-webhook"},
    )


@router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
    summary="Google Chat webhook",
    description="Receives Google Chat bot events and returns card responses.",
)
async def google_chat_webhook(request: Request) -> JSONResponse:
    """Handle Google Chat webhook requests."""
    if not settings.google_chat_webhook_enabled:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=create_error_card(
                "Google Chat webhook is currently disabled.",
                bot_name=settings.google_chat_bot_name,
            ),
        )
    if settings.google_chat_integration_mode != "two_way":
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=create_error_card(
                "Google Chat is configured in one-way mode. Incoming chatbot events are disabled.",
                bot_name=settings.google_chat_bot_name,
            ),
        )

    try:
        payload: Dict[str, Any] = await request.json()
    except Exception:
        logger.warning("Google Chat webhook received non-JSON payload")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=create_error_card(
                "Invalid request format. JSON payload expected.",
                bot_name=settings.google_chat_bot_name,
            ),
        )

    logger.info(
        f"Google Chat webhook request: type={_resolve_event_type(payload) or None} "
        f"event_time={_event_payload(payload).get('eventTime') or _event_payload(payload).get('event_time')} "
        f"keys={list(payload.keys())}"
    )

    try:
        card_response = process_google_chat_event(payload)
        if _is_addon_event(payload):
            # Google Workspace add-on chat trigger is strict about response shape.
            # Return a plain text Message wrapped in DataActions for maximum compatibility.
            event = _event_payload(payload)
            is_card_click = bool(event.get("action"))
            addon_message = {
                "text": _card_payload_to_text(card_response, preserve_options=not is_card_click)
            }
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=_wrap_addon_response(addon_message),
            )
        return JSONResponse(status_code=status.HTTP_200_OK, content=card_response)
    except Exception as exc:
        logger.error(f"Google Chat webhook failed: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=create_error_card(
                "Unexpected error while processing webhook event.",
                bot_name=settings.google_chat_bot_name,
            ),
        )
