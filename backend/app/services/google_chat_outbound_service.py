"""Outbound Google Chat notifications via incoming webhook (one-way mode)."""

from __future__ import annotations

from typing import Any, Dict

import requests
from loguru import logger

from app.config import settings


def _is_one_way_enabled() -> bool:
    return (
        settings.google_chat_webhook_enabled
        and settings.google_chat_integration_mode == "one_way"
        and bool(settings.google_chat_incoming_webhook_url)
    )


def _build_triage_message(ticket: Dict[str, Any], triage_result: Dict[str, Any]) -> Dict[str, Any]:
    confidence_pct = float(triage_result.get("confidence", 0.0)) * 100
    steps = triage_result.get("resolution_steps") or []
    steps_text = "\n".join([f"{idx + 1}. {step}" for idx, step in enumerate(steps[:5])]) or "N/A"
    return {
        "text": (
            f"*New ticket triaged*\n"
            f"Ticket: INC-{int(ticket['id']):06d}\n"
            f"Subject: {ticket.get('subject', 'N/A')}\n"
            f"Queue: {triage_result.get('queue', 'N/A')}\n"
            f"Category: {triage_result.get('category', 'N/A')}\n"
            f"Sub-Category: {triage_result.get('sub_category', 'N/A')}\n"
            f"Confidence: {confidence_pct:.2f}%\n"
            f"SOP: {triage_result.get('sop_reference', 'N/A')}\n"
            f"Top Resolution Steps:\n{steps_text}"
        )
    }


def send_triage_notification(ticket: Dict[str, Any], triage_result: Dict[str, Any]) -> None:
    """Send one-way notification to Google Chat space if configured."""
    if not _is_one_way_enabled():
        return

    webhook_url = str(settings.google_chat_incoming_webhook_url).strip()
    payload = _build_triage_message(ticket=ticket, triage_result=triage_result)

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json; charset=UTF-8"},
            timeout=15,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Google Chat notification request failed: {exc}") from exc
    if response.status_code >= 300:
        raise RuntimeError(
            f"Google Chat notification failed. Status={response.status_code}, body={response.text}"
        )
    logger.info("Google Chat one-way triage notification sent successfully")
