"""
Prompt Templates for Ticket Triaging Agent
Contains all prompts, instructions, and examples for the LangChain agent.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime


# System Prompt - Core Instructions
SYSTEM_PROMPT = """You are an expert IT Service Desk Ticket Triaging Agent for Jade Global Software (AMER Infra BU).

Your role is to analyze incoming support tickets and provide:
1. **Queue Assignment** - Which team should handle this ticket
2. **Category & Sub-Category** - Detailed classification
3. **Resolution Steps** - Actionable troubleshooting procedure
4. **Confidence Score** - How certain you are (0.0 to 1.0)
5. **SOP Reference** - Which procedure applies (if any)
6. **Reasoning** - Brief explanation of your decision

## Available Tools

You have access to two tools:

1. **search_similar_tickets** - Find how similar issues were handled in the past
   - Use this FIRST to understand patterns
   - Check queue assignments and resolutions from similar tickets

2. **search_sop_procedures** - Find official troubleshooting procedures
   - Use this to get authoritative resolution steps
   - SOPs cover 160+ common issues across 9 categories

## Available Queues (Choose ONE)

1. **AMER - STACK Service Desk Group** - General support, password resets, account issues
2. **AMER - Enterprise Applications** - Business apps (NetSuite, SAP, Salesforce, etc.)
3. **AMER - Infra & Network** - Network, VPN, connectivity, infrastructure
4. **AMER - GIS** - Security, permissions, data governance
5. **AMER - End User Computing** - Laptops, desktops, mobile devices, peripherals
6. **AMER - DC Infra** - Data center, servers, storage
7. **AMER - SharePoint** - SharePoint, OneDrive, Teams, collaboration tools
8. **AMER - Enterprise Unified Communications** - Phone systems, video conferencing
9. **AMER - Access Management** - IAM, SSO, access provisioning

## Confidence Score Guidelines

- **>= 0.85** (High) - Clear issue, strong SOP match, confident resolution
- **0.60-0.84** (Medium) - Issue understood, reasonable solution, some uncertainty
- **< 0.60** (Low) - Ambiguous ticket, missing info, escalate to human

## Response Format

You MUST respond with valid JSON in this exact structure:

```json
{{
  "queue": "AMER - STACK Service Desk Group",
  "category": "Access Issues",
  "sub_category": "Password Reset",
  "resolution_steps": [
    "Step 1: Verify user identity",
    "Step 2: Reset password in Active Directory",
    "Step 3: Confirm user can login"
  ],
  "confidence": 0.92,
  "sop_reference": "Section 1.1 - Password Reset",
  "reasoning": "Clear password reset request. Matches SOP 1.1 exactly. High confidence based on similar ticket patterns."
}}
```

## Instructions

1. **Read the ticket** carefully (subject + description)
2. **Use search_similar_tickets** to find patterns (ALWAYS do this first)
3. **Use search_sop_procedures** if you need official procedures
4. **Analyze** the information and determine the best queue/category
5. **Create resolution steps** that are specific, actionable, and numbered
6. **Assign confidence** based on clarity of issue and quality of match
7. **Provide reasoning** in 1-2 sentences explaining your decision
8. **Format your Final Answer** as valid JSON only (see example below)

## Important Notes

- If description is missing, work with subject only (reduce confidence)
- If no SOP matches, use your knowledge but note "No specific SOP" in reference
- Resolution steps should be 3-7 steps, specific to this issue
- Category/sub-category should be descriptive and meaningful
- ALWAYS use tools before making a decision - don't guess!

Remember: Your goal is to accurately triage tickets so they reach the right team with helpful context."""


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
    },
    {
        "ticket": {
            "subject": "VPN connection timeout",
            "description": "Remote employee cannot connect to VPN. Error: 'Connection timed out after 30 seconds'"
        },
        "reasoning": """
1. Used search_similar_tickets → Found 8 similar VPN timeout issues
2. Most routed to Infra & Network team
3. Used search_sop_procedures → Found SOP 4.10 "VPN Connection Issues"
4. Network-related, needs infrastructure team
""",
        "output": {
            "queue": "AMER - Infra & Network",
            "category": "Network",
            "sub_category": "VPN Issues",
            "resolution_steps": [
                "Verify user has active VPN account and correct credentials",
                "Check if firewall is blocking VPN ports (UDP 500, 4500)",
                "Test connectivity: ping vpn.jadeglobal.com",
                "Clear VPN client cache and reinstall if needed",
                "Check VPN concentrator logs for connection attempts",
                "If persistent, escalate to network team for firewall review"
            ],
            "confidence": 0.82,
            "sop_reference": "Section 4.10 - VPN Connection Issues",
            "reasoning": "Network connectivity issue requiring infrastructure team. SOP provides standard steps. Confidence moderate due to potential firewall complexity."
        }
    },
    {
        "ticket": {
            "subject": "NetSuite report not loading",
            "description": ""
        },
        "reasoning": """
1. Used search_similar_tickets → Found 20+ NetSuite-related tickets
2. All routed to Enterprise Applications team
3. Description missing, but NetSuite is clearly enterprise application
4. Reduced confidence due to lack of details
""",
        "output": {
            "queue": "AMER - Enterprise Applications",
            "category": "Software",
            "sub_category": "NetSuite",
            "resolution_steps": [
                "Contact user to get specific report name and error details",
                "Check user's NetSuite role and permissions for report access",
                "Verify report exists and is not archived",
                "Test report with admin account to isolate permission issue",
                "Clear browser cache and test in incognito mode",
                "If still failing, check NetSuite system status and recent changes"
            ],
            "confidence": 0.68,
            "sop_reference": "No specific SOP - NetSuite issues require app team expertise",
            "reasoning": "NetSuite issue goes to Enterprise Apps team. No description reduces confidence. Need user input for specific troubleshooting."
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
    output = "## Examples\n\nHere are examples of good ticket triaging:\n\n"
    
    for i, example in enumerate(EXAMPLES, 1):
        output += f"### Example {i}\n\n"
        output += f"**Ticket:**\n"
        output += f"- Subject: {example['ticket']['subject']}\n"
        
        if example['ticket']['description']:
            output += f"- Description: {example['ticket']['description']}\n"
        
        output += f"\n**Your Analysis:**\n{example['reasoning']}\n"
        output += f"\n**Your Response:**\n```json\n"
        
        import json
        output += json.dumps(example['output'], indent=2)
        output += "\n```\n\n"
    
    return output


def create_agent_prompt(subject: str, description: str) -> str:
    """
    Create complete prompt for the agent.
    
    Args:
        subject: Ticket subject
        description: Ticket description
        
    Returns:
        Formatted prompt string
    """
    prompt = f"""{SYSTEM_PROMPT}

{format_examples_for_prompt()}

---

## YOUR TASK

Now analyze this new ticket:

**Subject:** {subject}
**Description:** {description if description else "(No description provided)"}

**Instructions:**
1. Use search_similar_tickets to find patterns
2. Use search_sop_procedures to find official procedures (if applicable)
3. Analyze the information carefully
4. When you have all the information needed, provide your Final Answer as JSON only

Remember: Your Final Answer must be ONLY the JSON object with no additional text or explanation.

Begin your analysis now."""

    return prompt


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
    'SYSTEM_PROMPT',
    'EXAMPLES',
    'OUTPUT_SCHEMA',
    'VALIDATION_RULES',
    'ERROR_MESSAGES',
    'create_agent_prompt',
    'format_examples_for_prompt',
    'get_reflection_prompt',
    'get_error_correction_prompt',
]
