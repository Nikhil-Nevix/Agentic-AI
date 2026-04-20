"""Google Chat card builders for chatbot responses."""

from typing import Any, Dict, List
from uuid import uuid4


def _build_card(title: str, subtitle: str, widgets: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "cardsV2": [
            {
                "cardId": str(uuid4()),
                "card": {
                    "header": {
                        "title": title,
                        "subtitle": subtitle,
                    },
                    "sections": [{"widgets": widgets}],
                },
            }
        ]
    }


def create_welcome_card(bot_name: str = "Triage Assistant") -> Dict[str, Any]:
    """Welcome message with Start Triage button."""
    widgets: List[Dict[str, Any]] = [
        {
            "textParagraph": {
                "text": "Hi! Hello, how may I help you?",
            }
        },
        {
            "buttonList": {
                "buttons": [
                    {
                        "text": "Start Triage",
                        "onClick": {
                            "action": {
                                "actionMethodName": "start_triage",
                            }
                        },
                    }
                ]
            }
        },
    ]
    return _build_card(bot_name, "Let us create your ticket", widgets)


def create_text_input_card(question: str, bot_name: str = "Triage Assistant") -> Dict[str, Any]:
    """Text prompt card for conversational question."""
    widgets: List[Dict[str, Any]] = [
        {
            "textParagraph": {
                "text": question,
            }
        }
    ]
    return _build_card(bot_name, "Please reply in chat with your answer", widgets)


def create_dropdown_card(title: str, options: List[str], bot_name: str = "Triage Assistant") -> Dict[str, Any]:
    """Dropdown-like options rendered as buttons for chat webhook flow."""
    buttons = [
        {
            "text": option,
            "onClick": {
                "action": {
                    "actionMethodName": "select_option",
                    "parameters": [{"key": "selected", "value": option}],
                }
            },
        }
        for option in options
    ]
    widgets: List[Dict[str, Any]] = [
        {
            "textParagraph": {
                "text": title,
            }
        },
        {
            "buttonList": {
                "buttons": buttons,
            }
        },
    ]
    return _build_card(bot_name, "Choose one option", widgets)


def create_triage_result_card(
    ticket: Dict[str, Any],
    triage_result: Dict[str, Any],
    bot_name: str = "Triage Assistant",
) -> Dict[str, Any]:
    """Formatted triage results card."""
    steps = triage_result.get("resolution_steps") or []
    steps_text = "<br>".join([f"{idx + 1}. {step}" for idx, step in enumerate(steps)])
    widgets: List[Dict[str, Any]] = [
        {
            "textParagraph": {
                "text": (
                    f"<b>Ticket:</b> INC-{int(ticket['id']):06d}<br>"
                    f"<b>Subject:</b> {ticket['subject']}<br>"
                    f"<b>Queue:</b> {triage_result['queue']}<br>"
                    f"<b>Category:</b> {triage_result['category']}<br>"
                    f"<b>Sub-Category:</b> {triage_result['sub_category']}<br>"
                    f"<b>Confidence:</b> {float(triage_result['confidence']) * 100:.2f}%<br>"
                    f"<b>SOP:</b> {triage_result['sop_reference']}<br>"
                )
            }
        },
        {
            "textParagraph": {
                "text": f"<b>Reasoning:</b><br>{triage_result['reasoning']}",
            }
        },
        {
            "textParagraph": {
                "text": f"<b>Resolution Steps:</b><br>{steps_text}" if steps_text else "<b>Resolution Steps:</b><br>N/A",
            }
        },
    ]
    return _build_card(f"{bot_name} - Triage Complete", "Ticket created and routed successfully", widgets)


def _sop_action_buttons() -> Dict[str, Any]:
    return {
        "buttonList": {
            "buttons": [
                {
                    "text": "Get AI Solution",
                    "onClick": {
                        "action": {
                            "actionMethodName": "get_ai_solution",
                        }
                    },
                },
                {
                    "text": "Auto Resolve",
                    "onClick": {
                        "action": {
                            "actionMethodName": "auto_resolve",
                        }
                    },
                },
                {
                    "text": "Escalate to Human",
                    "onClick": {
                        "action": {
                            "actionMethodName": "escalate_to_human",
                        }
                    },
                },
            ]
        }
    }


def _ai_followup_buttons() -> Dict[str, Any]:
    return {
        "buttonList": {
            "buttons": [
                {
                    "text": "Another AI Solution",
                    "onClick": {
                        "action": {
                            "actionMethodName": "another_ai_solution",
                        }
                    },
                },
                {
                    "text": "Issue Resolved",
                    "onClick": {
                        "action": {
                            "actionMethodName": "mark_resolved",
                        }
                    },
                },
                {
                    "text": "Escalate to Human",
                    "onClick": {
                        "action": {
                            "actionMethodName": "escalate_to_human",
                        }
                    },
                },
            ]
        }
    }


def create_processing_card(message: str, bot_name: str = "Triage Assistant") -> Dict[str, Any]:
    widgets: List[Dict[str, Any]] = [
        {
            "textParagraph": {
                "text": message,
            }
        },
        {
            "buttonList": {
                "buttons": [
                    {
                        "text": "Check Status",
                        "onClick": {
                            "action": {
                                "actionMethodName": "status",
                            }
                        },
                    }
                ]
            }
        },
    ]
    return _build_card(bot_name, "Analyzing your issue", widgets)


def create_sop_solution_card(
    ticket: Dict[str, Any],
    triage_result: Dict[str, Any],
    bot_name: str = "Triage Assistant",
) -> Dict[str, Any]:
    steps = triage_result.get("resolution_steps") or []
    steps_text = "<br>".join([f"{idx + 1}. {step}" for idx, step in enumerate(steps)])
    widgets: List[Dict[str, Any]] = [
        {
            "textParagraph": {
                "text": (
                    f"<b>Ticket:</b> INC-{int(ticket['id']):06d}<br>"
                    f"<b>Subject:</b> {ticket['subject']}<br>"
                    f"<b>Queue:</b> {triage_result['queue']}<br>"
                    f"<b>Category:</b> {triage_result['category']}<br>"
                    f"<b>SOP Reference:</b> {triage_result['sop_reference']}"
                )
            }
        },
        {
            "textParagraph": {
                "text": f"<b>SOP Solution:</b><br>{steps_text}" if steps_text else "<b>SOP Solution:</b><br>N/A",
            }
        },
        _sop_action_buttons(),
    ]
    return _build_card(f"{bot_name} - SOP Solution", "SOP guidance is ready", widgets)


def create_sop_result_card(
    ticket: Dict[str, Any],
    triage_result: Dict[str, Any],
    bot_name: str = "Support Assistant",
) -> Dict[str, Any]:
    steps = triage_result.get("resolution_steps") or []
    steps_text = "<br>".join([f"{i + 1}. {s}" for i, s in enumerate(steps)])
    widgets: List[Dict[str, Any]] = [
        {
            "textParagraph": {
                "text": (
                    f"<b>Issue:</b> {ticket.get('subject', '')}<br>"
                    f"<b>SOP Reference:</b> {triage_result.get('sop_reference', '')}"
                )
            }
        },
        {
            "textParagraph": {
                "text": f"<b>SOP Solution:</b><br>{steps_text or 'N/A'}",
            }
        },
        {
            "textParagraph": {
                "text": "Did these steps solve your issue? Reply with 1, 2, or 3 if typing.",
            }
        },
        {
            "buttonList": {
                "buttons": [
                    {
                        "text": "1. Resolved",
                        "onClick": {
                            "action": {
                                "actionMethodName": "issue_resolved_sop",
                            }
                        },
                    },
                    {
                        "text": "2. Not Resolved",
                        "onClick": {
                            "action": {
                                "actionMethodName": "issue_not_resolved_sop",
                            }
                        },
                    },
                    {
                        "text": "3. Auto Resolve",
                        "onClick": {
                            "action": {
                                "actionMethodName": "auto_resolve_now",
                            }
                        },
                    },
                ]
            }
        },
    ]
    return _build_card(f"{bot_name} - SOP Solution", "Based on your issue", widgets)


def create_auto_resolve_consent_card(
    *,
    playbook_title: str,
    permissions: List[str],
    bot_name: str = "Support Assistant",
) -> Dict[str, Any]:
    permission_lines = "<br>".join([f"- {item}" for item in permissions]) if permissions else "- Session permissions"
    widgets: List[Dict[str, Any]] = [
        {
            "textParagraph": {
                "text": (
                    f"<b>Auto Resolve Plan:</b> {playbook_title}<br>"
                    "To continue, please grant the required permissions for this session."
                ),
            }
        },
        {
            "textParagraph": {
                "text": f"<b>Required Permissions:</b><br>{permission_lines}",
            }
        },
        {
            "buttonList": {
                "buttons": [
                    {
                        "text": "1. Grant Permissions",
                        "onClick": {
                            "action": {
                                "actionMethodName": "grant_auto_resolve_permission",
                            }
                        },
                    },
                    {
                        "text": "2. Cancel",
                        "onClick": {
                            "action": {
                                "actionMethodName": "decline_auto_resolve_permission",
                            }
                        },
                    },
                ]
            }
        },
    ]
    return _build_card(bot_name, "Auto Resolve Permission Request", widgets)


def create_ask_ai_or_escalate_card(bot_name: str = "Support Assistant") -> Dict[str, Any]:
    widgets: List[Dict[str, Any]] = [
        {
            "textParagraph": {
                "text": "The SOP steps did not resolve your issue. How would you like to proceed? Reply with 1 or 2 if typing.",
            }
        },
        {
            "buttonList": {
                "buttons": [
                    {
                        "text": "1. Get AI Solution",
                        "onClick": {
                            "action": {
                                "actionMethodName": "want_ai_solution",
                            }
                        },
                    },
                    {
                        "text": "2. Escalate to Human",
                        "onClick": {
                            "action": {
                                "actionMethodName": "want_escalate",
                            }
                        },
                    },
                ]
            }
        },
    ]
    return _build_card(bot_name, "Let us try another approach", widgets)


def create_ask_final_resolved_card(bot_name: str = "Support Assistant") -> Dict[str, Any]:
    widgets: List[Dict[str, Any]] = [
        {
            "textParagraph": {
                "text": "Did the AI solution resolve your issue? Reply with 1 or 2 if typing.",
            }
        },
        {
            "buttonList": {
                "buttons": [
                    {
                        "text": "1. Resolved",
                        "onClick": {
                            "action": {
                                "actionMethodName": "final_resolved",
                            }
                        },
                    },
                    {
                        "text": "2. Create Support Ticket",
                        "onClick": {
                            "action": {
                                "actionMethodName": "create_ticket_now",
                            }
                        },
                    },
                ]
            }
        },
    ]
    return _build_card(bot_name, "Let us know how to proceed", widgets)


def create_ai_solution_card(
    ticket: Dict[str, Any],
    triage_result: Dict[str, Any],
    ai_solution: str,
    bot_name: str = "Triage Assistant",
) -> Dict[str, Any]:
    widgets: List[Dict[str, Any]] = [
        {
            "textParagraph": {
                "text": (
                    f"<b>Ticket:</b> INC-{int(ticket['id']):06d}<br>"
                    f"<b>Subject:</b> {ticket['subject']}<br>"
                    f"<b>SOP Reference:</b> {triage_result['sop_reference']}"
                )
            }
        },
        {
            "textParagraph": {
                "text": f"<b>AI Solution:</b><br>{ai_solution}",
            }
        },
        {
            "textParagraph": {
                "text": (
                    "Is your issue resolved now? If not, I can generate another AI solution "
                    "or create a support ticket. Reply with 1, 2, or 3 if typing."
                ),
            }
        },
        {
            "buttonList": {
                "buttons": [
                    {
                        "text": "1. Another AI Solution",
                        "onClick": {
                            "action": {
                                "actionMethodName": "another_ai_solution",
                            }
                        },
                    },
                    {
                        "text": "2. Resolved",
                        "onClick": {
                            "action": {
                                "actionMethodName": "final_resolved",
                            }
                        },
                    },
                    {
                        "text": "3. Create Support Ticket",
                        "onClick": {
                            "action": {
                                "actionMethodName": "create_ticket_now",
                            }
                        },
                    },
                ]
            }
        },
    ]
    return _build_card(f"{bot_name} - AI Solution", "AI recommendations generated", widgets)


def create_feature_coming_soon_card(bot_name: str = "Triage Assistant") -> Dict[str, Any]:
    widgets: List[Dict[str, Any]] = [
        {
            "textParagraph": {
                "text": "Feature coming soon.",
            }
        }
    ]
    return _build_card(bot_name, "Update", widgets)


def create_error_card(message: str, bot_name: str = "Triage Assistant") -> Dict[str, Any]:
    """Error card for graceful user-facing failures."""
    widgets: List[Dict[str, Any]] = [
        {
            "textParagraph": {
                "text": f"Sorry, something went wrong.<br><b>Details:</b> {message}",
            }
        }
    ]
    return _build_card(bot_name, "Unable to process request", widgets)
