# Module 6: Agent Tools & Prompts

LangChain tools and prompt templates for the ticket triaging agent.

## Overview

This module provides the foundation for the AI agent:
- **Tools** - LangChain tools for retrieving similar tickets and SOPs
- **Prompts** - System prompt, few-shot examples, and output schema
- **Retrievers** - Smart search over FAISS indexes with formatting

## Files Created

```
app/agent/
├── __init__.py
├── tools.py       # LangChain tools and retrievers
└── prompts.py     # All prompt templates
```

## Tools

### 1. **search_similar_tickets**
Searches the ticket FAISS index for similar past tickets.

**Input:** Ticket description or issue  
**Output:** Formatted list of 5 similar tickets with queue, category, description

**Example:**
```python
from app.agent.tools import get_agent_tools

tools = get_agent_tools()
ticket_tool = tools[0]

result = ticket_tool.run("User cannot access email")
# Returns:
# Found 5 similar tickets:
# --- Ticket 1 (Similarity: 72.74%) ---
# Subject: Outlook wont send or receive emails
# Queue: AMER - STACK Service Desk Group
# Category: Software
# ...
```

### 2. **search_sop_procedures**
Searches the SOP FAISS index for relevant troubleshooting procedures.

**Input:** Issue or problem description  
**Output:** Formatted list of 3 relevant SOPs with full procedure steps

**Example:**
```python
sop_tool = tools[1]

result = sop_tool.run("Password reset")
# Returns:
# Found 3 relevant SOP procedures:
# --- SOP 1: [1.1] Password Reset ---
# Relevance: 65.12%
# Procedure:
# 1. Verify user identity...
# 2. Open Active Directory...
# ...
```

## Retrievers

### TicketRetriever
- Embeds query text
- Searches FAISS ticket index
- Filters by score threshold (>= 0.3)
- Formats results with metadata

### SOPRetriever
- Embeds query text
- Searches FAISS SOP index
- Retrieves full content from MySQL database
- Filters by score threshold (>= 0.25)
- Includes relevance percentage

## Prompts

### System Prompt (3,482 chars)
Comprehensive instructions for the agent including:
- Role definition (IT Service Desk Triaging Agent)
- Tool descriptions and usage patterns
- 9 available queues with descriptions
- Confidence score guidelines
- JSON output schema
- Step-by-step instructions

### Few-Shot Examples (3)
Three detailed examples showing:
1. **Account Lockout** - Standard procedure, high confidence (0.95)
2. **VPN Timeout** - Network issue, medium confidence (0.82)
3. **NetSuite Report** - Missing description, lower confidence (0.68)

Each example includes:
- Original ticket (subject + description)
- Agent's reasoning process
- Final JSON response

### Output Schema
Required fields in agent response:
```json
{
  "queue": "string (one of 9 queues)",
  "category": "string (high-level category)",
  "sub_category": "string (specific issue type)",
  "resolution_steps": ["step 1", "step 2", ...],
  "confidence": 0.0-1.0,
  "sop_reference": "Section X.X - Title",
  "reasoning": "1-2 sentence explanation"
}
```

### Validation Rules
Enforced constraints:
- Queue must be exact match from allowed list
- Resolution steps: 3-10 items
- Confidence: 0.0-1.0 float
- Reasoning: 20-500 characters
- All fields required

## Helper Functions

### `format_ticket_context(subject, description)`
Formats incoming ticket for agent consumption.

### `extract_queue_info()`
Returns metadata about queues, categories, and routing rules.

### `create_agent_prompt(subject, description)`
Creates complete prompt by combining:
- System prompt
- Few-shot examples
- Current ticket
- Instructions

### `get_reflection_prompt(response, ticket)`
Generates self-verification prompt for agent to review its output.

### `get_error_correction_prompt(error_type, field)`
Creates targeted correction prompts for validation errors.

## Usage Example

```python
from app.agent.tools import get_agent_tools
from app.agent.prompts import create_agent_prompt

# Get tools
tools = get_agent_tools()

# Create prompt for new ticket
prompt = create_agent_prompt(
    subject="Cannot login to VPN",
    description="Error: Connection timeout after 30 seconds"
)

# Tools will be used by the agent (Module 7) like this:
# 1. Agent receives prompt
# 2. Agent calls search_similar_tickets
# 3. Agent calls search_sop_procedures
# 4. Agent analyzes and returns JSON
```

## Testing

Run comprehensive verification:
```bash
python test_module6.py
```

Tests verify:
- ✅ Tool initialization (2 LangChain tools)
- ✅ Ticket retriever functionality
- ✅ SOP retriever functionality
- ✅ LangChain tool interface
- ✅ Helper functions
- ✅ Prompt templates
- ✅ Validation schema
- ✅ End-to-end workflow

## Search Quality

**Ticket Search:**
- Query: "Cannot access email outlook"
- Top result: 72.74% similarity
- Returns relevant queue (STACK Service Desk)
- Includes category and description

**SOP Search:**
- Query: "Email access issues"
- Top result: [1.7] Email Account Locked (54.73% relevance)
- Full procedure steps included
- Database integration working

## Confidence Thresholds

The agent uses these routing rules:

| Confidence | Action | Example |
|------------|--------|---------|
| >= 0.85 | Auto-resolve | Clear issue, exact SOP match |
| 0.60-0.84 | Route with suggestion | Issue understood, reasonable solution |
| < 0.60 | Escalate to human | Ambiguous, missing info |

## Architecture

```
User Ticket
    ↓
create_agent_prompt()
    ↓
LangChain Agent (Module 7)
    ↓
┌─────────────────┐
│ Tools Available │
├─────────────────┤
│ 1. search_similar_tickets → TicketRetriever → FAISS tickets.index
│ 2. search_sop_procedures  → SOPRetriever   → FAISS sop.index + MySQL
└─────────────────┘
    ↓
Agent Response (JSON)
    ↓
Validation + Routing
```

## Integration Points

Module 6 integrates with:
- **Module 4** - Uses embedder for query embedding
- **Module 5** - Uses FAISS indexes and SOP database
- **Module 7** - Provides tools to the ReAct agent (next module)
- **Module 8** - Validation rules used by API endpoints

## Performance

- Tool initialization: ~3 seconds (loads embedder + indexes)
- Ticket search: ~50ms per query
- SOP search: ~100ms per query (includes DB lookup)
- Prompt generation: <1ms

## Next Steps

Module 6 provides the tools and prompts. **Module 7** will:
- Create the LangChain ReAct agent
- Implement confidence-based routing
- Add retry logic and error handling
- Create the main `triage_agent.py` orchestrator
