"""Conversation state machine for Google Chat webhook chatbot."""
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import re

from loguru import logger

from app.config import settings
from app.db.session import SessionLocal
from app.agent.triage_agent import get_triage_agent
from app.agent.prompts import create_conversational_prompt
from app.models import ChatConversation as ChatConversationModel
from app.services.triage_service import triage_ticket_async_start_threaded, triage_ticket_async_status
from app.services.auto_resolve_service import find_best_auto_resolve_playbook, run_auto_resolve_simulation
from app.utils.google_chat_cards import (
    create_auto_resolve_consent_card,
    create_ask_ai_or_escalate_card,
    create_ask_final_resolved_card,
    create_dropdown_card,
    create_error_card,
    create_feature_coming_soon_card,
    create_processing_card,
    create_ai_solution_card,
    create_sop_result_card,
    create_sop_solution_card,
    create_text_input_card,
    create_triage_result_card,
    create_welcome_card,
)


QUEUE_OPTIONS: List[str] = [
    "AI Suggested",
    "Stack Service Desk",
    "Enterprise App",
    "Infra & Network",
    "End User Computing",
    "Other Queues",
]

CATEGORY_OPTIONS: List[str] = [
    "AI Suggested",
    "Access Management",
    "Enterprise Platform",
    "Network Services",
    "Endpoint Support",
    "General Incident",
]

STEP_WELCOME = "welcome"
STEP_ASK_SUBJECT = "ask_subject"
STEP_ASK_DESCRIPTION = "ask_description"
STEP_ASK_QUEUE = "ask_queue"
STEP_ASK_CATEGORY = "ask_category"
STEP_PROCESS_TRIAGE = "process_triage"
STEP_SHOW_RESULTS = "show_results"
STEP_WAIT_TRIAGE = "wait_triage"
STEP_ASK_SATISFACTION = "ask_satisfaction"
STEP_COMPLETE = "complete"
STEP_SHOW_SOP = "show_sop"
STEP_ASK_AI_OR_ESCALATE = "ask_ai_or_escalate"
STEP_SHOW_AI_SOLUTION = "show_ai_solution"
STEP_ASK_FINAL_RESOLVED = "ask_final_resolved"
STEP_CREATE_TICKET = "create_ticket"
STEP_ASK_AUTO_RESOLVE_PERMISSION = "ask_auto_resolve_permission"

TRIGGER_START_VALUES = {"start_triage", "start triage", "start", "start triage"}
GREETING_VALUES = {"hi", "hii", "hiii", "hello", "hey", "heyy", "hola", "yo"}
CASUAL_CHAT_VALUES = {
    "how are you",
    "what can you do",
    "help",
    "hello there",
    "good morning",
    "good afternoon",
    "good evening",
}
ISSUE_KEYWORDS = {
    "issue",
    "problem",
    "error",
    "failed",
    "failure",
    "unable",
    "cannot",
    "can't",
    "not working",
    "doesn't work",
    "broken",
    "access",
    "login",
    "password",
    "vpn",
    "email",
    "outlook",
    "teams",
    "network",
    "slow",
    "crash",
    "install",
    "update",
    "restart",
    "reboot",
    "stuck",
    "timeout",
}
SATISFIED_VALUES = {
    "yes",
    "y",
    "yup",
    "yeah",
    "ok",
    "okay",
    "done",
    "thanks",
    "thank you",
    "thankyou",
    "thank you for the help",
    "resolved",
}

ACTION_GET_AI_SOLUTION = "get_ai_solution"
ACTION_ANOTHER_AI_SOLUTION = "another_ai_solution"
ACTION_MARK_RESOLVED = "mark_resolved"
ACTION_AUTO_RESOLVE = "auto_resolve"
ACTION_ESCALATE_TO_HUMAN = "escalate_to_human"
ACTION_STATUS = "status"
ACTION_ISSUE_RESOLVED_SOP = "issue_resolved_sop"
ACTION_ISSUE_NOT_RESOLVED_SOP = "issue_not_resolved_sop"
ACTION_WANT_AI_SOLUTION = "want_ai_solution"
ACTION_WANT_ESCALATE = "want_escalate"
ACTION_FINAL_RESOLVED = "final_resolved"
ACTION_CREATE_TICKET_NOW = "create_ticket_now"
ACTION_AUTO_RESOLVE_NOW = "auto_resolve_now"
ACTION_GRANT_AUTO_RESOLVE_PERMISSION = "grant_auto_resolve_permission"
ACTION_DECLINE_AUTO_RESOLVE_PERMISSION = "decline_auto_resolve_permission"

UNSATISFIED_VALUES = {
    "no",
    "nope",
    "not resolved",
    "not solved",
    "still not resolved",
    "still not solved",
    "still not working",
    "didnt work",
    "didn't work",
    "doesnt work",
    "doesn't work",
    "not satisfied",
    "still issue",
    "still facing issue",
    "still facing the issue",
    "complication",
    "complications",
}

QUEUE_MAP = {
    "Stack Service Desk": "AMER - STACK Service Desk Group",
    "Enterprise App": "AMER - Enterprise Applications",
    "Infra & Network": "AMER - Infra & Network",
    "End User Computing": "AMER - End User Computing",
}

CATEGORY_MAP = {
    "Access Management": "Access Management",
    "Enterprise Platform": "Enterprise Platform",
    "Network Services": "Network Services",
    "Endpoint Support": "Endpoint Support",
    "General Incident": "General Incident",
}


def _bot_name() -> str:
    return settings.google_chat_bot_name


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

    # Heuristics for Google Chat payload variants where event type is omitted.
    if event.get("action"):
        return "CARD_CLICKED"
    if event.get("message") or (event.get("messagePayload") or {}).get("message"):
        return "MESSAGE"
    if event.get("space") or (event.get("spaceData") or {}).get("space"):
        return "ADDED_TO_SPACE"
    return ""


def _extract_payload_context(payload: Dict[str, Any]) -> Dict[str, str]:
    event = _event_payload(payload)
    message = event.get("message") or ((event.get("messagePayload") or {}).get("message") or {})
    space = event.get("space") or ((event.get("spaceData") or {}).get("space") or {})
    space_id = (space or {}).get("name", "") or (message.get("space") or {}).get("name", "")
    user = event.get("user") or message.get("sender") or {}
    user_id = user.get("name", "")
    thread_id = (message.get("thread") or {}).get("name", "")
    if not space_id or not user_id:
        raise ValueError("Missing required space/user identifiers in webhook payload")
    return {"space_id": space_id, "user_id": user_id, "thread_id": thread_id}


def _extract_action_value(payload: Dict[str, Any]) -> str:
    event = _event_payload(payload)
    action = event.get("action") or {}
    method = str(action.get("actionMethodName", "")).strip()
    params = action.get("parameters") or []
    selected = ""
    for item in params:
        if item.get("key") == "selected":
            selected = str(item.get("value", "")).strip()
            break
    return selected or method


def _extract_message_text(payload: Dict[str, Any]) -> str:
    event = _event_payload(payload)
    message = event.get("message") or ((event.get("messagePayload") or {}).get("message") or {})
    text = str(message.get("argumentText") or message.get("text") or "").strip()
    if not text:
        action = event.get("action") or {}
        text = str(action.get("actionMethodName", "")).strip()
    return text


def _normalize_user_input(payload: Dict[str, Any]) -> str:
    action_value = _extract_action_value(payload)
    if action_value:
        return action_value
    return _extract_message_text(payload)


def _get_or_create_conversation(
    space_id: str, user_id: str, thread_id: str
) -> ChatConversationModel:
    db = SessionLocal()
    try:
        conversation = (
            db.query(ChatConversationModel)
            .filter(
                ChatConversationModel.google_chat_space_id == space_id,
                ChatConversationModel.google_chat_user_id == user_id,
                ChatConversationModel.is_active.is_(True),
            )
            .order_by(ChatConversationModel.updated_at.desc())
            .first()
        )
        if conversation:
            return conversation

        conversation = ChatConversationModel(
            google_chat_space_id=space_id,
            google_chat_user_id=user_id,
            google_chat_thread_id=thread_id or None,
            current_step=STEP_WELCOME,
            collected_data={},
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        return conversation
    finally:
        db.close()


def _update_conversation(
    conversation_id: int,
    *,
    step: Optional[str] = None,
    collected_data: Optional[Dict[str, Any]] = None,
    ticket_id: Optional[int] = None,
    is_active: Optional[bool] = None,
) -> ChatConversationModel:
    db = SessionLocal()
    try:
        conversation = db.query(ChatConversationModel).filter(ChatConversationModel.id == conversation_id).first()
        if not conversation:
            raise ValueError(f"Conversation not found: {conversation_id}")
        if step is not None:
            conversation.current_step = step
        if collected_data is not None:
            conversation.collected_data = collected_data
        if ticket_id is not None:
            conversation.ticket_id = ticket_id
        if is_active is not None:
            conversation.is_active = is_active
        conversation.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(conversation)
        logger.info(
            f"Conversation state changed: id={conversation.id} "
            f"step={conversation.current_step} active={conversation.is_active}"
        )
        return conversation
    finally:
        db.close()


def _validate_payload(payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    event_type = _resolve_event_type(payload)
    if event_type not in {"MESSAGE", "CARD_CLICKED", "ADDED_TO_SPACE"}:
        return False, f"Unsupported event type: {event_type or 'unknown'}"
    return True, None


def _is_added_to_space_event(payload: Dict[str, Any]) -> bool:
    return _resolve_event_type(payload) == "ADDED_TO_SPACE"


def _should_start_flow(user_input: str) -> bool:
    normalized = user_input.strip().lower()
    return normalized in TRIGGER_START_VALUES


def _normalize_text(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _map_numeric_choice(step: str, user_input: str) -> Optional[str]:
    normalized = _normalize_text(user_input)
    if not normalized:
        return None

    step_choice_map: Dict[str, Dict[str, str]] = {
        STEP_SHOW_SOP: {
            "1": ACTION_ISSUE_RESOLVED_SOP,
            "2": ACTION_ISSUE_NOT_RESOLVED_SOP,
            "3": ACTION_AUTO_RESOLVE_NOW,
        },
        STEP_ASK_AUTO_RESOLVE_PERMISSION: {
            "1": ACTION_GRANT_AUTO_RESOLVE_PERMISSION,
            "2": ACTION_DECLINE_AUTO_RESOLVE_PERMISSION,
        },
        STEP_ASK_AI_OR_ESCALATE: {
            "1": ACTION_WANT_AI_SOLUTION,
            "2": ACTION_WANT_ESCALATE,
        },
        STEP_SHOW_AI_SOLUTION: {
            "1": ACTION_ANOTHER_AI_SOLUTION,
            "2": ACTION_FINAL_RESOLVED,
            "3": ACTION_CREATE_TICKET_NOW,
        },
        STEP_ASK_FINAL_RESOLVED: {
            "1": ACTION_FINAL_RESOLVED,
            "2": ACTION_CREATE_TICKET_NOW,
        },
        STEP_SHOW_RESULTS: {
            "1": ACTION_ANOTHER_AI_SOLUTION,
            "2": ACTION_FINAL_RESOLVED,
            "3": ACTION_CREATE_TICKET_NOW,
        },
    }

    return step_choice_map.get(step, {}).get(normalized)


def _is_greeting(user_input: str) -> bool:
    normalized = _normalize_text(user_input)
    return normalized in GREETING_VALUES


def _is_satisfied_response(user_input: str) -> bool:
    normalized = _normalize_text(user_input)
    return normalized in SATISFIED_VALUES


def _is_casual_chat(user_input: str) -> bool:
    normalized = _normalize_text(user_input)
    if normalized in CASUAL_CHAT_VALUES:
        return True

    # Treat broad assistance-only prompts as casual until the user shares concrete issue details.
    casual_markers = (
        "help",
        "can you help",
        "need your help",
        "i need help",
        "please help",
    )
    return any(marker in normalized for marker in casual_markers)


def _looks_like_issue_description(user_input: str) -> bool:
    normalized = _normalize_text(user_input)
    if not normalized:
        return False
    if _is_greeting(normalized) or _should_start_flow(normalized):
        return False
    if _is_casual_chat(normalized):
        # Short help-like prompts without issue signals should not trigger triage.
        if not any(keyword in normalized for keyword in ISSUE_KEYWORDS):
            return False

    if any(keyword in normalized for keyword in ISSUE_KEYWORDS):
        return True

    # Free-form issue descriptions usually contain enough detail.
    return len(normalized) >= 28


def _wants_ai_solution(user_input: str) -> bool:
    normalized = _normalize_text(user_input)
    if not normalized:
        return False
    phrases = {
        "get ai solution",
        "ai solution",
        "give ai solution",
        "show ai solution",
        "need ai solution",
        "instead give me the ai solution",
        "no i don't need the sop solution",
    }
    return any(phrase in normalized for phrase in phrases)


def _wants_another_ai_solution(user_input: str) -> bool:
    normalized = _normalize_text(user_input)
    if not normalized:
        return False
    phrases = {
        "another ai solution",
        "one more ai solution",
        "different ai solution",
        "alternative ai solution",
        "try another solution",
        "another solution",
        "not this one give another",
    }
    return any(phrase in normalized for phrase in phrases)


def _wants_status_check(user_input: str) -> bool:
    normalized = _normalize_text(user_input)
    return normalized in {"status", "check status", "show status"}


def _is_unsatisfied_response(user_input: str) -> bool:
    normalized = _normalize_text(user_input)
    return normalized in UNSATISFIED_VALUES


def _wants_auto_resolve(user_input: str) -> bool:
    normalized = _normalize_text(user_input)
    if not normalized:
        return False
    phrases = {
        "auto resolve",
        "auto-resolve",
        "automatically resolve",
        "resolve automatically",
        "run auto resolve",
    }
    return any(phrase in normalized for phrase in phrases)


def _derive_subject(user_input: str) -> str:
    cleaned = " ".join(user_input.split())
    if not cleaned:
        return "User-reported issue"
    return cleaned[:120]


def _conversation_context_for_prompt(conversation: ChatConversationModel) -> str:
    """Build a concise context snapshot for conversational LLM responses."""
    data = dict(conversation.collected_data or {})
    context_parts = [f"current_step={conversation.current_step}"]

    subject = str(data.get("subject") or "").strip()
    description = str(data.get("description") or "").strip()
    if subject:
        context_parts.append(f"subject={subject}")
    if description:
        desc_preview = description[:300]
        context_parts.append(f"description={desc_preview}")

    triage_job_id = str(data.get("triage_job_id") or "").strip()
    if triage_job_id:
        context_parts.append(f"triage_job_id={triage_job_id}")

    return " | ".join(context_parts)


def _generate_conversational_reply(conversation: ChatConversationModel, user_message: str, fallback: str) -> str:
    """Generate natural assistant text before formal triage starts."""
    try:
        prompt = create_conversational_prompt(
            conversation_context=_conversation_context_for_prompt(conversation),
            user_message=user_message,
        )
        llm = get_triage_agent().llm
        response = llm.invoke(prompt)
        content = str(getattr(response, "content", "") or "").strip()
        if not content:
            return fallback
        return content
    except Exception as exc:
        logger.warning(f"Conversational reply fallback used: {exc}")
        return fallback


def _start_issue_triage(conversation: ChatConversationModel, issue_text: str) -> Dict[str, Any]:
    data = {
        "subject": _derive_subject(issue_text),
        "description": issue_text,
        "queue": "AI Suggested",
        "category": "AI Suggested",
    }
    job = triage_ticket_async_start_threaded(
        subject=data["subject"],
        description=data["description"],
        queue_override=None,
        category_override=None,
    )
    data["triage_job_id"] = job["job_id"]
    _update_conversation(conversation.id, step=STEP_WAIT_TRIAGE, collected_data=data)
    logger.info(
        f"Queued conversational triage for conversation_id={conversation.id} job_id={job['job_id']}"
    )
    return create_processing_card(
        "Thanks for the details. I am preparing an SOP-based solution now.",
        bot_name=_bot_name(),
    )


def _format_text_for_card(text: str) -> str:
    return text.replace("\n", "<br>")


def _normalize_solution_text(text: str) -> str:
    """Normalize solution text for reliable duplicate detection."""
    plain = (text or "").replace("<br>", "\n")
    plain = re.sub(r"\s+", " ", plain).strip().lower()
    return plain


def _build_forced_alternative_solution(
    triage_result: Dict[str, Any],
    attempt_index: int,
) -> str:
    """Create a deterministic fallback alternative when LLM repeats output."""
    raw_steps = [str(step).strip() for step in (triage_result.get("resolution_steps") or []) if str(step).strip()]

    if raw_steps:
        # Rotate selected steps to ensure each alternative starts differently.
        rotation = (attempt_index - 1) % len(raw_steps)
        rotated = raw_steps[rotation:] + raw_steps[:rotation]
        selected_steps = rotated[:3]
    else:
        selected_steps = [
            "Reconfirm exact error text and timestamp from the user session.",
            "Clear local app/session cache, then restart the impacted client.",
            "Re-test with a fresh sign-in and verify service dependency health.",
        ]

    lines = [
        f"Alternative troubleshooting path #{attempt_index}",
        f"1. {selected_steps[0]}",
        f"2. {selected_steps[1] if len(selected_steps) > 1 else 'Validate authentication, connectivity, and endpoint reachability.'}",
        f"3. {selected_steps[2] if len(selected_steps) > 2 else 'Retry action and confirm expected result with the user.'}",
        "Validation: confirm issue does not recur in next user action.",
        "Escalate: if unchanged after these checks, route to human support.",
    ]
    return _format_text_for_card("\n".join(lines))


def _generate_ai_solution(
    subject: str,
    description: str,
    triage_result: Dict[str, Any],
    attempt_index: int = 1,
    previous_solutions: Optional[List[str]] = None,
) -> str:
    variation_tracks = [
        "prioritize quick user-side checks first",
        "prioritize cache/session and credential refresh path",
        "prioritize network/environment validation path",
        "prioritize application settings and rollback-safe path",
    ]
    selected_track = variation_tracks[(attempt_index - 1) % len(variation_tracks)]

    prior_context = ""
    if previous_solutions:
        condensed = "\n".join([f"- {item}" for item in previous_solutions[-2:]])
        prior_context = (
            "Avoid repeating these prior AI suggestions exactly. "
            "Use a mostly different root-cause hypothesis and a different first remediation step. "
            f"Prior suggestions:\n{condensed}\n"
        )

    prompt = (
        "You are an IT support assistant. Generate a short and precise AI-generated solution for the issue below. "
        "Keep it practical, safe, and easy to execute quickly. "
        f"This is alternative suggestion attempt #{attempt_index}. "
        f"Use this variation track: {selected_track}.\n"
        "Output format constraints:\n"
        "- Max 90 words total\n"
        "- Max 3 remediation steps\n"
        "- Each step <= 14 words\n"
        "- Prefer bullets and plain language\n"
        "- Include one short validation check\n"
        "- Include one short escalation trigger\n\n"
        f"{prior_context}"
        f"Issue subject: {subject}\n"
        f"Issue details: {description}\n"
        f"SOP reference: {triage_result.get('sop_reference')}\n"
        f"SOP steps: {triage_result.get('resolution_steps')}\n"
    )
    try:
        llm = get_triage_agent().llm
        response = llm.invoke(prompt)
        content = str(getattr(response, "content", "") or "").strip()
        if not content:
            raise ValueError("Empty AI response")
        compact_lines = [line.strip() for line in content.splitlines() if line.strip()]
        compact = "\n".join(compact_lines[:7])
        if len(compact) > 700:
            compact = compact[:700].rsplit(" ", 1)[0] + "..."
        return _format_text_for_card(compact)
    except Exception as exc:
        logger.warning(f"AI solution generation fallback used: {exc}")
        fallback = (
            "Root cause likely aligns with the ticket pattern detected by triage.<br>"
            "Recommended approach:<br>"
            "1. Execute the SOP steps in order.<br>"
            "2. Reproduce and verify the issue clears for the user.<br>"
            "3. If symptoms persist after SOP checks, collect logs and escalate to human support."
        )
        return fallback


def _handle_get_ai_solution(conversation: ChatConversationModel, regenerate: bool = False) -> Dict[str, Any]:
    data = dict(conversation.collected_data or {})
    ticket = data.get("ticket") or {}
    triage_result = data.get("triage_result") or {}
    if not ticket or not triage_result:
        return create_text_input_card(
            "Please share your issue first so I can generate SOP and AI solutions.",
            bot_name=_bot_name(),
        )

    ai_solution = str(data.get("ai_solution") or "").strip()
    ai_attempts = int(data.get("ai_solution_attempts") or 0)
    prior_solutions = [str(item) for item in (data.get("ai_solutions_history") or []) if str(item).strip()]

    if regenerate or not ai_solution:
        next_attempt = ai_attempts + 1 if ai_attempts > 0 else 1

        existing_normalized = {
            _normalize_solution_text(item)
            for item in prior_solutions
            if _normalize_solution_text(item)
        }

        generated_solution = ""
        chosen_attempt = next_attempt
        max_regen_attempts = 3

        for retry_idx in range(max_regen_attempts):
            attempt_num = next_attempt + retry_idx
            candidate = _generate_ai_solution(
                subject=str(data.get("subject") or ticket.get("subject") or "User issue"),
                description=str(data.get("description") or ""),
                triage_result=triage_result,
                attempt_index=attempt_num,
                previous_solutions=prior_solutions,
            )

            normalized_candidate = _normalize_solution_text(candidate)
            if normalized_candidate and normalized_candidate not in existing_normalized:
                generated_solution = candidate
                chosen_attempt = attempt_num
                break

            logger.info(
                "AI solution duplicate detected; retrying with stronger variation "
                f"(attempt={attempt_num}, retry={retry_idx + 1}/{max_regen_attempts})"
            )

        if not generated_solution:
            chosen_attempt = next_attempt + max_regen_attempts
            generated_solution = _build_forced_alternative_solution(
                triage_result=triage_result,
                attempt_index=chosen_attempt,
            )
            logger.warning(
                "AI solution remained repetitive after retries; "
                "served deterministic alternative response"
            )

        ai_solution = generated_solution
        data["ai_solution"] = ai_solution
        prior_solutions.append(ai_solution)
        data["ai_solutions_history"] = prior_solutions[-5:]
        data["ai_solution_attempts"] = chosen_attempt
    _update_conversation(conversation.id, collected_data=data, step=STEP_SHOW_AI_SOLUTION)

    return create_ai_solution_card(
        ticket=ticket,
        triage_result=triage_result,
        ai_solution=ai_solution,
        bot_name=_bot_name(),
    )


def _handle_resolution_success(conversation: ChatConversationModel) -> Dict[str, Any]:
    _update_conversation(
        conversation.id,
        step=STEP_COMPLETE,
        collected_data=dict(conversation.collected_data or {}),
        is_active=False,
    )
    return create_text_input_card(
        "Great to hear your issue is resolved. Thank you. Reach out anytime you need help again.",
        bot_name=_bot_name(),
    )


def _handle_unsatisfied_after_ai(conversation: ChatConversationModel) -> Dict[str, Any]:
    data = dict(conversation.collected_data or {})
    ticket = data.get("ticket") or {}
    triage_result = data.get("triage_result") or {}
    if ticket and triage_result:
        return create_ai_solution_card(
            ticket=ticket,
            triage_result=triage_result,
            ai_solution=(
                "I understand this is still not resolved. Please use the 'Escalate to Human' button so a support agent can take over with priority."
            ),
            bot_name=_bot_name(),
        )
    return create_text_input_card(
        "I understand this is still not resolved. Please use 'Escalate to Human' so a support agent can take over.",
        bot_name=_bot_name(),
    )


def _handle_welcome_step(conversation: ChatConversationModel, user_input: str) -> Dict[str, Any]:
    if _is_greeting(user_input):
        return create_text_input_card(
            _generate_conversational_reply(
                conversation,
                user_input,
                "Hi! I can help with IT issues. Tell me what issue you are facing.",
            ),
            bot_name=_bot_name(),
        )
    if _is_casual_chat(user_input):
        return create_text_input_card(
            _generate_conversational_reply(
                conversation,
                user_input,
                "I am doing well and ready to help. Please share the issue you want resolved.",
            ),
            bot_name=_bot_name(),
        )
    if _should_start_flow(user_input):
        return create_text_input_card("Please describe your issue in one message.", bot_name=_bot_name())
    if not user_input.strip():
        return create_welcome_card(bot_name=_bot_name())
    if not _looks_like_issue_description(user_input):
        return create_text_input_card(
            _generate_conversational_reply(
                conversation,
                user_input,
                "I can definitely help. Please share your IT issue with a little detail, for example: 'VPN is not connecting and shows authentication failed'.",
            ),
            bot_name=_bot_name(),
        )
    return _start_issue_triage(conversation, user_input)


def _handle_ask_subject_step(conversation: ChatConversationModel, user_input: str) -> Dict[str, Any]:
    if not user_input:
        return create_text_input_card("Please provide the ticket subject.", bot_name=_bot_name())
    data = dict(conversation.collected_data or {})
    data["subject"] = user_input
    _update_conversation(conversation.id, step=STEP_ASK_DESCRIPTION, collected_data=data)
    return create_text_input_card("Please provide a detailed description of the issue.", bot_name=_bot_name())


def _handle_ask_description_step(conversation: ChatConversationModel, user_input: str) -> Dict[str, Any]:
    if not user_input:
        return create_text_input_card("Please provide the issue description to continue.", bot_name=_bot_name())
    data = dict(conversation.collected_data or {})
    data["description"] = user_input
    _update_conversation(conversation.id, step=STEP_ASK_QUEUE, collected_data=data)
    return create_dropdown_card("Select queue preference:", QUEUE_OPTIONS, bot_name=_bot_name())


def _handle_ask_queue_step(conversation: ChatConversationModel, user_input: str) -> Dict[str, Any]:
    if user_input not in QUEUE_OPTIONS:
        return create_dropdown_card("Please choose a valid queue option:", QUEUE_OPTIONS, bot_name=_bot_name())
    data = dict(conversation.collected_data or {})
    data["queue"] = user_input
    _update_conversation(conversation.id, step=STEP_ASK_CATEGORY, collected_data=data)
    return create_dropdown_card("Select category preference:", CATEGORY_OPTIONS, bot_name=_bot_name())


def _handle_ask_category_step(conversation: ChatConversationModel, user_input: str) -> Dict[str, Any]:
    if user_input not in CATEGORY_OPTIONS:
        return create_dropdown_card("Please choose a valid category option:", CATEGORY_OPTIONS, bot_name=_bot_name())

    data = dict(conversation.collected_data or {})
    data["category"] = user_input
    _update_conversation(conversation.id, step=STEP_PROCESS_TRIAGE, collected_data=data)

    subject = str(data.get("subject", "")).strip()
    description = str(data.get("description", "")).strip()
    queue_override = QUEUE_MAP.get(str(data.get("queue")))
    category_override = CATEGORY_MAP.get(str(data.get("category")))

    job = triage_ticket_async_start_threaded(
        subject=subject,
        description=description,
        queue_override=queue_override,
        category_override=category_override,
    )
    data["triage_job_id"] = job["job_id"]
    _update_conversation(conversation.id, step=STEP_WAIT_TRIAGE, collected_data=data)
    logger.info(
        f"Queued async triage for conversation_id={conversation.id} job_id={job['job_id']}"
    )
    return create_text_input_card(
        "Thanks. I am processing your triage now. Please type 'status' in a few seconds to get the result.",
        bot_name=_bot_name(),
    )


def _handle_wait_triage_step(conversation: ChatConversationModel, user_input: str) -> Dict[str, Any]:
    data = dict(conversation.collected_data or {})
    job_id = str(data.get("triage_job_id") or "").strip()
    if not job_id:
        _update_conversation(conversation.id, step=STEP_ASK_CATEGORY, collected_data=data)
        return create_dropdown_card("Select category preference:", CATEGORY_OPTIONS, bot_name=_bot_name())

    job = triage_ticket_async_status(job_id)
    if not job:
        _update_conversation(conversation.id, step=STEP_ASK_CATEGORY, collected_data=data)
        return create_dropdown_card(
            "I could not find the triage job. Please select category again:",
            CATEGORY_OPTIONS,
            bot_name=_bot_name(),
        )

    status = str(job.get("status") or "").lower()
    if status in {"queued", "running"}:
        return create_processing_card(
            "Still processing. Please click 'Check Status' again in a few seconds.",
            bot_name=_bot_name(),
        )

    if status == "failed":
        _update_conversation(conversation.id, step=STEP_ASK_CATEGORY, collected_data=data)
        return create_error_card(
            "Triage failed. Please select category again to retry.",
            bot_name=_bot_name(),
        )

    result = job.get("result") or {}
    ticket = result.get("ticket")
    triage_result = result.get("triage_result")
    if not ticket or not triage_result:
        _update_conversation(conversation.id, step=STEP_ASK_CATEGORY, collected_data=data)
        return create_error_card(
            "Triage result was incomplete. Please select category again.",
            bot_name=_bot_name(),
        )

    data["ticket"] = ticket
    data["triage_result"] = triage_result
    data["auto_resolve_playbook"] = find_best_auto_resolve_playbook(
        subject=str(data.get("subject") or ticket.get("subject") or ""),
        description=str(data.get("description") or ""),
        sop_reference=str(triage_result.get("sop_reference") or ""),
        category=str(triage_result.get("category") or ""),
    )
    data["ai_solution"] = _generate_ai_solution(
        subject=str(data.get("subject") or ticket.get("subject") or "User issue"),
        description=str(data.get("description") or ""),
        triage_result=triage_result,
        attempt_index=1,
        previous_solutions=[],
    )
    data["ai_solution_attempts"] = 1
    data["ai_solutions_history"] = [data["ai_solution"]]
    _update_conversation(
        conversation.id,
        step=STEP_SHOW_SOP,
        collected_data=data,
        ticket_id=int(ticket["id"]),
        is_active=True,
    )
    return create_sop_result_card(ticket=ticket, triage_result=triage_result, bot_name=_bot_name())


def _manual_steps_message(steps: List[str]) -> str:
    if not steps:
        return "No manual steps were available."
    return "\n".join([f"{index + 1}. {step}" for index, step in enumerate(steps[:8])])


def _handle_auto_resolve_failure(conversation: ChatConversationModel, reason: str) -> Dict[str, Any]:
    data = dict(conversation.collected_data or {})
    triage_result = data.get("triage_result") or {}
    playbook = data.get("auto_resolve_playbook") or {}

    manual_steps = playbook.get("steps") or triage_result.get("resolution_steps") or []
    steps_text = _manual_steps_message([str(step) for step in manual_steps])

    _update_conversation(conversation.id, step=STEP_SHOW_SOP, collected_data=data)
    return create_text_input_card(
        (
            f"Auto Resolve failed: {reason}\n\n"
            "Please follow the steps below manually and raise a support ticket if needed:\n"
            f"{steps_text}"
        ),
        bot_name=_bot_name(),
    )


def _run_auto_resolve(conversation: ChatConversationModel) -> Dict[str, Any]:
    data = dict(conversation.collected_data or {})
    playbook = data.get("auto_resolve_playbook") or {}
    if not playbook:
        return _handle_auto_resolve_failure(
            conversation,
            "No matching playbook found in Common_Outlook.pdf for this issue.",
        )

    result = run_auto_resolve_simulation(playbook)
    if result.get("status") != "success":
        return _handle_auto_resolve_failure(
            conversation,
            str(result.get("error") or "Auto Resolve execution did not complete."),
        )

    executed_steps = result.get("executed_steps") or []
    steps_text = "\n".join(
        [f"{item.get('step_no')}. {item.get('description')} (completed)" for item in executed_steps]
    )

    _update_conversation(
        conversation.id,
        step=STEP_COMPLETE,
        collected_data=data,
        is_active=False,
    )
    return create_text_input_card(
        (
            "Auto Resolve completed successfully for this session.\n\n"
            "Executed steps:\n"
            f"{steps_text}\n\n"
            "If any issue remains, please raise a support ticket and we will assist you."
        ),
        bot_name=_bot_name(),
    )


def _handle_auto_resolve_request(conversation: ChatConversationModel) -> Dict[str, Any]:
    data = dict(conversation.collected_data or {})
    playbook = data.get("auto_resolve_playbook") or {}

    if not playbook:
        return _handle_auto_resolve_failure(
            conversation,
            "No matching playbook found in Common_Outlook.pdf for this issue.",
        )

    if bool(data.get("auto_resolve_consent_granted")):
        return _run_auto_resolve(conversation)

    _update_conversation(conversation.id, step=STEP_ASK_AUTO_RESOLVE_PERMISSION, collected_data=data)
    return create_auto_resolve_consent_card(
        playbook_title=str(playbook.get("title") or "Matched Outlook issue"),
        permissions=[str(item) for item in (playbook.get("permissions") or [])],
        bot_name=_bot_name(),
    )


def _handle_auto_resolve_permission_step(conversation: ChatConversationModel, user_input: str) -> Dict[str, Any]:
    data = dict(conversation.collected_data or {})
    playbook = data.get("auto_resolve_playbook") or {}

    if user_input == ACTION_GRANT_AUTO_RESOLVE_PERMISSION:
        data["auto_resolve_consent_granted"] = True
        data["auto_resolve_consent_at"] = datetime.utcnow().isoformat()
        _update_conversation(conversation.id, collected_data=data)
        return _run_auto_resolve(conversation)

    if user_input == ACTION_DECLINE_AUTO_RESOLVE_PERMISSION:
        _update_conversation(conversation.id, step=STEP_SHOW_SOP, collected_data=data)
        return create_text_input_card(
            "Understood. Auto Resolve is cancelled. You can continue manually with SOP steps or create a support ticket.",
            bot_name=_bot_name(),
        )

    return create_auto_resolve_consent_card(
        playbook_title=str(playbook.get("title") or "Matched Outlook issue"),
        permissions=[str(item) for item in (playbook.get("permissions") or [])],
        bot_name=_bot_name(),
    )


def _handle_show_sop_step(conversation: ChatConversationModel, user_input: str) -> Dict[str, Any]:
    if user_input == ACTION_ISSUE_RESOLVED_SOP or _is_satisfied_response(user_input):
        return _handle_resolution_success(conversation)
    if user_input == ACTION_AUTO_RESOLVE_NOW or _wants_auto_resolve(user_input):
        return _handle_auto_resolve_request(conversation)
    if user_input == ACTION_ISSUE_NOT_RESOLVED_SOP or _is_unsatisfied_response(user_input):
        _update_conversation(conversation.id, step=STEP_ASK_AI_OR_ESCALATE)
        return create_ask_ai_or_escalate_card(bot_name=_bot_name())
    data = dict(conversation.collected_data or {})
    return create_sop_result_card(
        ticket=data.get("ticket", {}),
        triage_result=data.get("triage_result", {}),
        bot_name=_bot_name(),
    )


def _handle_ask_ai_or_escalate_step(conversation: ChatConversationModel, user_input: str) -> Dict[str, Any]:
    if user_input == ACTION_WANT_AI_SOLUTION or _wants_ai_solution(user_input):
        return _handle_get_ai_solution(conversation, regenerate=False)
    if user_input in {ACTION_WANT_ESCALATE, ACTION_ESCALATE_TO_HUMAN}:
        return _trigger_freshservice_ticket(conversation)
    return create_ask_ai_or_escalate_card(bot_name=_bot_name())


def _handle_show_ai_solution_step(conversation: ChatConversationModel, user_input: str) -> Dict[str, Any]:
    if user_input == ACTION_FINAL_RESOLVED or _is_satisfied_response(user_input):
        return _handle_resolution_success(conversation)
    if user_input == ACTION_CREATE_TICKET_NOW:
        return _trigger_freshservice_ticket(conversation)
    if _wants_another_ai_solution(user_input):
        return _handle_get_ai_solution(conversation, regenerate=True)
    _update_conversation(conversation.id, step=STEP_ASK_FINAL_RESOLVED)
    return create_ask_final_resolved_card(bot_name=_bot_name())


def _trigger_freshservice_ticket(conversation: ChatConversationModel) -> Dict[str, Any]:
    from app.services.freshservice_service import create_freshservice_ticket

    data = dict(conversation.collected_data or {})
    subject = str(data.get("subject") or "User reported issue")
    description = str(data.get("description") or "")
    sop_ref = str((data.get("triage_result") or {}).get("sop_reference") or "")
    result = create_freshservice_ticket(subject=subject, description=description, sop_reference=sop_ref)
    ticket_id = result.get("ticket_id", "N/A")
    _update_conversation(conversation.id, step=STEP_COMPLETE, is_active=False)
    return create_text_input_card(
        f"A support ticket has been created: #{ticket_id}. A human agent will contact you shortly. Thank you for your patience.",
        bot_name=_bot_name(),
    )


def _handle_ask_satisfaction_step(conversation: ChatConversationModel, user_input: str) -> Dict[str, Any]:
    if _is_satisfied_response(user_input):
        _update_conversation(
            conversation.id,
            step=STEP_COMPLETE,
            collected_data=dict(conversation.collected_data or {}),
            is_active=False,
        )
        return create_text_input_card(
            "Glad I could help. Thank you.",
            bot_name=_bot_name(),
        )
    return create_text_input_card(
        "Thanks for the feedback. Type 'start' to create another ticket or share what still needs help.",
        bot_name=_bot_name(),
    )


def _web_card_payload_to_text(message_payload: Dict[str, Any]) -> str:
    if isinstance(message_payload.get("text"), str) and message_payload.get("text", "").strip():
        return str(message_payload["text"]).strip()

    cards = message_payload.get("cardsV2") or []
    lines: List[str] = []
    for card_entry in cards:
        card = (card_entry or {}).get("card") or {}
        header = card.get("header") or {}
        subtitle = str(header.get("subtitle") or "").strip()
        if subtitle:
            lines.append(subtitle)
        for section in card.get("sections") or []:
            for widget in section.get("widgets") or []:
                text_block = (widget.get("textParagraph") or {}).get("text")
                if text_block:
                    cleaned = (
                        str(text_block)
                        .replace("<br>", "\n")
                        .replace("<b>", "")
                        .replace("</b>", "")
                        .strip()
                    )
                    if cleaned:
                        lines.append(cleaned)
    message = "\n\n".join([line for line in lines if line])
    return message or "Please describe your issue in one message."


def _web_card_payload_to_options(message_payload: Dict[str, Any]) -> List[Dict[str, str]]:
    cards = message_payload.get("cardsV2") or []
    options: List[Dict[str, str]] = []
    for card_entry in cards:
        card = (card_entry or {}).get("card") or {}
        for section in card.get("sections") or []:
            for widget in section.get("widgets") or []:
                button_list = (widget.get("buttonList") or {}).get("buttons") or []
                for btn in button_list:
                    label = str(btn.get("text") or "").strip()
                    action = ((btn.get("onClick") or {}).get("action") or {})
                    action_name = str(action.get("actionMethodName") or "").strip()
                    if label and action_name:
                        options.append({"label": label, "action": action_name})
    return options


def process_web_chat_event(
    *,
    user_id: str,
    session_id: str = "portal",
    message: Optional[str] = None,
    action: Optional[str] = None,
) -> Dict[str, Any]:
    """Process frontend widget message with Google Chat state machine compatibility."""
    normalized_user = re.sub(r"[^a-zA-Z0-9_.@-]", "_", (user_id or "anonymous").strip())
    normalized_session = re.sub(r"[^a-zA-Z0-9_.-]", "_", (session_id or "portal").strip())

    space_name = f"spaces/web-{normalized_session}"
    user_name = f"users/{normalized_user}"
    thread_name = f"threads/web-{normalized_session}"

    if action and action.strip():
        payload: Dict[str, Any] = {
            "type": "CARD_CLICKED",
            "space": {"name": space_name},
            "user": {"name": user_name},
            "message": {
                "space": {"name": space_name},
                "sender": {"name": user_name},
                "thread": {"name": thread_name},
            },
            "action": {"actionMethodName": action.strip()},
        }
    else:
        payload = {
            "type": "MESSAGE",
            "space": {"name": space_name},
            "user": {"name": user_name},
            "message": {
                "argumentText": (message or "").strip(),
                "space": {"name": space_name},
                "sender": {"name": user_name},
                "thread": {"name": thread_name},
            },
        }

    card_response = process_google_chat_event(payload)
    return {
        "message": _web_card_payload_to_text(card_response),
        "options": _web_card_payload_to_options(card_response),
    }


def clear_web_chat_history(*, user_id: str, session_id: str = "portal") -> int:
    """Delete persisted web chatbot history rows for a user/session."""
    normalized_user = re.sub(r"[^a-zA-Z0-9_.@-]", "_", (user_id or "anonymous").strip())
    normalized_session = re.sub(r"[^a-zA-Z0-9_.-]", "_", (session_id or "portal").strip())

    space_name = f"spaces/web-{normalized_session}"
    user_name = f"users/{normalized_user}"

    db = SessionLocal()
    try:
        deleted_count = (
            db.query(ChatConversationModel)
            .filter(
                ChatConversationModel.google_chat_space_id == space_name,
                ChatConversationModel.google_chat_user_id == user_name,
            )
            .delete(synchronize_session=False)
        )
        db.commit()
        logger.info(
            "Cleared web chatbot history: "
            f"user={user_name} session={normalized_session} deleted={deleted_count}"
        )
        return int(deleted_count or 0)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def process_google_chat_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate payload, route by step, and return Google Chat card response."""
    if not settings.google_chat_webhook_enabled:
        return create_error_card("Google Chat webhook integration is disabled.", bot_name=_bot_name())

    is_valid, error = _validate_payload(payload)
    if not is_valid:
        return create_error_card(error or "Invalid Google Chat request.", bot_name=_bot_name())

    try:
        if _is_added_to_space_event(payload):
            return create_welcome_card(bot_name=_bot_name())

        context = _extract_payload_context(payload)
        user_input = _normalize_user_input(payload)
        conversation = _get_or_create_conversation(
            space_id=context["space_id"],
            user_id=context["user_id"],
            thread_id=context["thread_id"],
        )

        action_value = _extract_action_value(payload).strip().lower()
        if not action_value:
            mapped_choice = _map_numeric_choice(conversation.current_step, user_input)
            if mapped_choice:
                action_value = mapped_choice
                user_input = mapped_choice

        if action_value == ACTION_ISSUE_RESOLVED_SOP:
            return _handle_show_sop_step(conversation, action_value)
        if action_value == ACTION_ISSUE_NOT_RESOLVED_SOP:
            return _handle_show_sop_step(conversation, action_value)
        if action_value == ACTION_WANT_AI_SOLUTION:
            return _handle_ask_ai_or_escalate_step(conversation, action_value)
        if action_value == ACTION_WANT_ESCALATE:
            return _trigger_freshservice_ticket(conversation)
        if action_value == ACTION_FINAL_RESOLVED:
            return _handle_resolution_success(conversation)
        if action_value == ACTION_CREATE_TICKET_NOW:
            return _trigger_freshservice_ticket(conversation)
        if action_value in {ACTION_AUTO_RESOLVE_NOW, ACTION_AUTO_RESOLVE}:
            return _handle_auto_resolve_request(conversation)
        if action_value in {ACTION_GRANT_AUTO_RESOLVE_PERMISSION, ACTION_DECLINE_AUTO_RESOLVE_PERMISSION}:
            return _handle_auto_resolve_permission_step(conversation, action_value)
        if action_value == ACTION_GET_AI_SOLUTION:
            return _handle_get_ai_solution(conversation, regenerate=False)
        if action_value == ACTION_ANOTHER_AI_SOLUTION:
            return _handle_get_ai_solution(conversation, regenerate=True)
        if action_value == ACTION_MARK_RESOLVED:
            return _handle_resolution_success(conversation)
        if action_value == ACTION_ESCALATE_TO_HUMAN:
            return create_feature_coming_soon_card(bot_name=_bot_name())
        if action_value == ACTION_STATUS:
            return _handle_wait_triage_step(conversation, ACTION_STATUS)

        logger.info(
            f"Processing Google Chat event: conversation_id={conversation.id} "
            f"step={conversation.current_step} input='{user_input}'"
        )

        if _wants_ai_solution(user_input):
            return _handle_get_ai_solution(conversation, regenerate=False)

        if _wants_another_ai_solution(user_input):
            return _handle_get_ai_solution(conversation, regenerate=True)

        if _wants_status_check(user_input) and conversation.current_step == STEP_WAIT_TRIAGE:
            return _handle_wait_triage_step(conversation, ACTION_STATUS)

        if _is_greeting(user_input):
            _update_conversation(
                conversation.id,
                step=STEP_WELCOME,
                collected_data={},
                ticket_id=None,
                is_active=True,
            )
            return create_welcome_card(bot_name=_bot_name())

        if _should_start_flow(user_input):
            _update_conversation(
                conversation.id,
                step=STEP_WELCOME,
                collected_data={},
                ticket_id=None,
                is_active=True,
            )
            return create_text_input_card("Please describe your issue in one message.", bot_name=_bot_name())

        if conversation.current_step == STEP_WELCOME:
            return _handle_welcome_step(conversation, user_input)
        if conversation.current_step == STEP_SHOW_SOP:
            return _handle_show_sop_step(conversation, action_value or user_input)
        if conversation.current_step == STEP_ASK_AUTO_RESOLVE_PERMISSION:
            return _handle_auto_resolve_permission_step(conversation, action_value or user_input)
        if conversation.current_step == STEP_ASK_AI_OR_ESCALATE:
            return _handle_ask_ai_or_escalate_step(conversation, action_value or user_input)
        if conversation.current_step in {STEP_SHOW_AI_SOLUTION, STEP_SHOW_RESULTS}:
            return _handle_show_ai_solution_step(conversation, action_value or user_input)
        if conversation.current_step == STEP_SHOW_RESULTS:
            if _is_satisfied_response(user_input):
                return _handle_resolution_success(conversation)
            if _wants_ai_solution(user_input):
                return _handle_get_ai_solution(conversation, regenerate=False)
            if _wants_another_ai_solution(user_input):
                return _handle_get_ai_solution(conversation, regenerate=True)
            if _is_unsatisfied_response(user_input):
                return _handle_unsatisfied_after_ai(conversation)
            if user_input and not _is_satisfied_response(user_input):
                if not _looks_like_issue_description(user_input):
                    return create_text_input_card(
                        "Share your next issue in one message (what is failing and any error shown), and I will triage it.",
                        bot_name=_bot_name(),
                    )
                return _start_issue_triage(conversation, user_input)
            return create_text_input_card(
                "If you have another issue, please type it now and I will triage it.",
                bot_name=_bot_name(),
            )
        if conversation.current_step == STEP_ASK_SUBJECT:
            return _handle_ask_subject_step(conversation, user_input)
        if conversation.current_step == STEP_ASK_DESCRIPTION:
            return _handle_ask_description_step(conversation, user_input)
        if conversation.current_step == STEP_ASK_QUEUE:
            return _handle_ask_queue_step(conversation, user_input)
        if conversation.current_step == STEP_ASK_CATEGORY:
            return _handle_ask_category_step(conversation, user_input)
        if conversation.current_step == STEP_WAIT_TRIAGE:
            return _handle_wait_triage_step(conversation, user_input)
        if conversation.current_step == STEP_ASK_FINAL_RESOLVED:
            return _handle_show_ai_solution_step(conversation, action_value or user_input)
        if conversation.current_step == STEP_CREATE_TICKET:
            return _trigger_freshservice_ticket(conversation)
        if conversation.current_step == STEP_ASK_SATISFACTION:
            return _handle_ask_satisfaction_step(conversation, user_input)
        if conversation.current_step in {STEP_PROCESS_TRIAGE, STEP_COMPLETE}:
            return create_text_input_card("Please describe your issue to continue.", bot_name=_bot_name())

        return create_error_card("Unknown conversation state. Please type 'start' to begin again.", bot_name=_bot_name())
    except ValueError as validation_error:
        logger.warning(f"Google Chat payload validation error: {validation_error}")
        return create_error_card(str(validation_error), bot_name=_bot_name())
    except Exception as exc:
        logger.error(f"Google Chat service failure: {exc}", exc_info=True)
        return create_error_card("Unable to process your request right now. Please try again.", bot_name=_bot_name())
