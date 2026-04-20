"""
Prompt Templates for Ticket Triaging Agent
Contains all prompts, instructions, and examples for the LangChain agent.
"""

from typing import Dict, Any, Optional
from datetime import datetime


# Primary conversational prompt used before formal triage starts.
CONVERSATIONAL_SYSTEM_PROMPT = """You are a specialized customer support assistant.
Your ONLY job is to help users solve product and service issues by strictly following SOPs.

RULES:
- Never answer questions outside of product/service support scope
- Never make up solutions not found in the SOP
- Always be concise, warm, and professional
- If the issue is unclear, ask ONE clarifying question only
- Never ask for queue or category from the user — handle that internally

CONVERSATION PHASE BEHAVIOR:
- Greeting → Welcome warmly, ask what issue they are facing
- Issue described → Confirm you understood it, proceed to SOP lookup
- Unclear message → Ask one clarifying question
- Out of scope → Politely say you can only help with product/service issues

CURRENT CONVERSATION CONTEXT:
{conversation_context}

USER MESSAGE: {user_message}

Respond naturally and helpfully:"""


# Triage prompt consumed by the ReAct executor in triage_agent.py.
TRIAGE_AGENT_PROMPT = """You are an expert IT support triage agent.

ISSUE DETAILS:
Subject: {subject}
Description: {description}
Additional Context: {context}

Your task:
1. Use available tools to find similar tickets and relevant SOPs
2. Analyze the issue systematically
3. Provide structured resolution guidance

Available tools:
- similar_ticket_search: Find related past tickets
- sop_retrieval: Search knowledge base for procedures

CRITICAL: Your Final Answer MUST be valid JSON matching this exact schema:
{{
    "queue": "string",
    "category": "string",
    "sub_category": "string",
    "resolution_steps": ["step1", "step2", "step3"],
    "confidence": "high|medium|low",
    "sop_reference": "SOP title or null",
    "reasoning": "Brief explanation of your analysis"
}}

Be specific, concise, and actionable. Use SOP evidence when available and reduce confidence when details are incomplete."""

# Backward compatibility alias used elsewhere in legacy flows.
SYSTEM_PROMPT = TRIAGE_AGENT_PROMPT


# Few-Shot Examples
EXAMPLES = [
    {
        "ticket": {
            "subject": "Cannot access email - account locked",
            "description": "User jsmith@jadeglobal.com cannot login to Outlook. Getting 'account locked' error."
        },
        "reasoning": """
1. Used search_similar_tickets → Found 15+ similar account lockout cases
2. All routed to STACK Service Desk Group
3. Used search_sop_procedures → Found SOP 1.2 "Account Locked Out"
4. Clear issue, standard procedure available
""",
        "output": {
            "queue": "AMER - STACK Service Desk Group",
            "category": "Access Issues",
            "sub_category": "Account Lockout",
            "resolution_steps": [
                "Verify user identity (ask security questions or employee ID)",
                "Open Active Directory Users and Computers",
                "Locate user account jsmith@jadeglobal.com",
                "Check 'Unlock account' checkbox under Account tab",
                "Reset password if needed (must change at next login)",
                "Confirm user can access Outlook successfully"
            ],
            "confidence": 0.95,
            "sop_reference": "Section 1.2 - Account Locked Out",
            "reasoning": "Standard account lockout issue. Clear SOP match (1.2). Similar tickets show 100% resolution with this procedure. High confidence."
        }
    }
]


# Output Schema Description
OUTPUT_SCHEMA = {
    "queue": "string - One of 9 available queues (exact match required)",
    "category": "string - High-level category (Access, Hardware, Software, Network, etc.)",
    "sub_category": "string - Specific issue type within category",
    "resolution_steps": "array of strings - Numbered, actionable steps (3-7 steps)",
    "confidence": "float - 0.0 to 1.0 (>= 0.85 high, 0.60-0.84 medium, < 0.60 low)",
    "sop_reference": "string - SOP section number and title, or 'No specific SOP'",
    "reasoning": "string - 1-2 sentence explanation of decision"
}


# Validation Rules
VALIDATION_RULES = {
    "queue": {
        "required": True,
        "type": "string",
        "must_be_one_of": [
            "AMER - STACK Service Desk Group",
            "AMER - Enterprise Applications",
            "AMER - Infra & Network",
            "AMER - GIS",
            "AMER - End User Computing",
            "AMER - DC Infra",
            "AMER - SharePoint",
            "AMER - Enterprise Unified Communications",
            "AMER - Access Management"
        ]
    },
    "category": {
        "required": True,
        "type": "string",
        "min_length": 3
    },
    "sub_category": {
        "required": True,
        "type": "string",
        "min_length": 3
    },
    "resolution_steps": {
        "required": True,
        "type": "array",
        "min_items": 3,
        "max_items": 10,
        "item_type": "string"
    },
    "confidence": {
        "required": True,
        "type": "float",
        "min": 0.0,
        "max": 1.0
    },
    "sop_reference": {
        "required": True,
        "type": "string",
        "min_length": 5
    },
    "reasoning": {
        "required": True,
        "type": "string",
        "min_length": 20,
        "max_length": 500
    }
}


def format_examples_for_prompt() -> str:
    """
    Format few-shot examples for inclusion in prompt.
    
    Returns:
        Formatted examples string
    """
    output = "## Example\n\nUse this as a style reference:\n\n"
    
    for i, example in enumerate(EXAMPLES, 1):
        output += f"### Example {i}\n\n"
        output += f"**Ticket:**\n"
        output += f"- Subject: {example['ticket']['subject']}\n"
        
        if example['ticket']['description']:
            output += f"- Description: {example['ticket']['description']}\n"
        
        output += f"\n**Analysis:**\n{example['reasoning']}\n"
        output += f"\n**Your Response:**\n```json\n"
        
        import json
        output += json.dumps(example['output'], indent=2)
        output += "\n```\n\n"
    
    return output


def create_conversational_prompt(conversation_context: str, user_message: str) -> str:
    """Build the conversational assistant prompt for Google Chat responses."""
    safe_context = (conversation_context or "No prior context").strip()
    safe_message = (user_message or "").strip()
    return CONVERSATIONAL_SYSTEM_PROMPT.format(
        conversation_context=safe_context,
        user_message=safe_message,
    )


def create_agent_prompt(subject: str, description: str, context: Optional[str] = None) -> str:
    """
    Create complete prompt for the agent.
    
    Args:
        subject: Ticket subject
        description: Ticket description
        
    Returns:
        Formatted prompt string
    """
    safe_subject = subject.strip() if subject else "(No subject provided)"
    safe_description = description if description else "(No description provided)"
    safe_context = context.strip() if context else "No additional context"

    return TRIAGE_AGENT_PROMPT.format(
        subject=safe_subject,
        description=safe_description,
        context=safe_context,
    )


def get_reflection_prompt(agent_response: Dict[str, Any], ticket: Dict[str, str]) -> str:
    """
    Create reflection prompt for agent self-verification.
    
    Args:
        agent_response: Agent's initial response
        ticket: Original ticket data
        
    Returns:
        Reflection prompt
    """
    import json
    
    return f"""Review your previous response and verify it meets all requirements:

**Original Ticket:**
- Subject: {ticket.get('subject')}
- Description: {ticket.get('description', '(none)')}

**Your Response:**
```json
{json.dumps(agent_response, indent=2)}
```

**Checklist:**
1. ✓ Is the queue one of the 9 valid options?
2. ✓ Are resolution steps specific and actionable (not generic)?
3. ✓ Is confidence score appropriate for the evidence?
4. ✓ Did you use both tools (similar tickets + SOPs)?
5. ✓ Is reasoning clear and well-justified?

If everything looks good, respond with: "VERIFIED"
If you need to make changes, provide the corrected JSON."""


# Error Messages
ERROR_MESSAGES = {
    "invalid_queue": "Queue must be one of the 9 valid AMER queues. Check the list in the system prompt.",
    "missing_steps": "Resolution steps must contain 3-10 actionable items.",
    "invalid_confidence": "Confidence must be a number between 0.0 and 1.0",
    "missing_field": "Required field '{field}' is missing from response",
    "invalid_json": "Response must be valid JSON. Do not include any text outside the JSON object.",
    "empty_reasoning": "Reasoning must explain your decision in 1-2 sentences (minimum 20 characters)",
}


def get_error_correction_prompt(error_type: str, field: Optional[str] = None) -> str:
    """
    Get prompt for correcting specific errors.
    
    Args:
        error_type: Type of error from ERROR_MESSAGES
        field: Field name if applicable
        
    Returns:
        Error correction prompt
    """
    message = ERROR_MESSAGES.get(error_type, "Unknown error")
    
    if field:
        message = message.format(field=field)
    
    return f"""Your previous response had an error:

**Error:** {message}

Please provide a corrected JSON response that addresses this issue.
Remember to follow the exact schema specified in the system prompt."""


# Metadata
PROMPT_VERSION = "1.0.0"
LAST_UPDATED = datetime.now().strftime("%Y-%m-%d")

__all__ = [
    'CONVERSATIONAL_SYSTEM_PROMPT',
    'TRIAGE_AGENT_PROMPT',
    'SYSTEM_PROMPT',
    'EXAMPLES',
    'OUTPUT_SCHEMA',
    'VALIDATION_RULES',
    'ERROR_MESSAGES',
    'create_conversational_prompt',
    'create_agent_prompt',
    'format_examples_for_prompt',
    'get_reflection_prompt',
    'get_error_correction_prompt',
]
