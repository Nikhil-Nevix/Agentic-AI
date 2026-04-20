import httpx
from loguru import logger

from app.config import settings


def create_freshservice_ticket(subject, description, sop_reference="", priority=2):
    url = f"https://{settings.freshservice_domain}/api/v2/tickets"
    headers = {"Content-Type": "application/json"}
    auth = (settings.freshservice_api_key, "X")
    body = {
        "subject": subject,
        "description": f"{description}<br><br><b>SOP Reference:</b> {sop_reference}<br><b>Source:</b> Google Chat Bot",
        "email": settings.freshservice_requester_email,
        "priority": priority,
        "status": 2,
        "type": "Incident",
        "source": 2,
    }
    try:
        response = httpx.post(url, json=body, auth=auth, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        ticket_id = data.get("ticket", {}).get("id", "N/A")
        logger.success(f"Freshservice ticket created: #{ticket_id}")
        return {"ticket_id": ticket_id, "status": "created"}
    except httpx.HTTPStatusError as e:
        logger.error(f"Freshservice API error: {e.response.status_code} {e.response.text}")
        return {"ticket_id": "N/A", "status": "failed", "error": str(e)}
    except Exception as e:
        logger.error(f"Freshservice ticket creation failed: {e}")
        return {"ticket_id": "N/A", "status": "failed", "error": str(e)}


def process_freshservice_ticket_created(payload):
    """Backward-compatible webhook processor used by freshservice_webhook router."""
    ticket = payload.get("ticket") or {}
    subject = str(ticket.get("subject") or "Freshservice ticket")
    description = str(ticket.get("description_text") or ticket.get("description") or "")
    sop_reference = str((payload.get("triage_result") or {}).get("sop_reference") or "")

    created = create_freshservice_ticket(
        subject=subject,
        description=description,
        sop_reference=sop_reference,
    )

    return {
        "freshservice_ticket_id": ticket.get("id", "N/A"),
        "status": created.get("status", "failed"),
        "ticket_id": created.get("ticket_id", "N/A"),
        "error": created.get("error"),
    }
