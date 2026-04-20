# Existing Chatbot Code Snapshot

This document captures the current chatbot implementation so you can upgrade from existing code instead of rewriting from scratch.

## Included Files

- backend/main.py
- backend/app/agent/triage_agent.py
- backend/app/agent/prompts.py
- backend/app/agent/tools.py
- backend/app/routers/google_chat_webhook.py
- backend/app/services/google_chat_service.py
- backend/app/services/triage_service.py
- backend/app/utils/google_chat_cards.py
- backend/app/models/chat_conversation.py
- backend/app/routers/triage.py
- frontend/src/api/client.js
- frontend/src/pages/TriagePage.tsx
- frontend/src/components/TriageResultCard.tsx

## backend/main.py

```python
"""
FastAPI Application - Service Desk Triaging Agent
Main application entry point for Module 8.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from loguru import logger
import time

from app.config import settings
from app.routers import triage_router, auth_router, google_chat_webhook_router, freshservice_webhook_router
from app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("=" * 70)

    try:
        init_db()
    except Exception as db_error:
        logger.error(f"Database initialization failed: {db_error}")
        raise
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info("=" * 70)
    
    # Initialize agent on startup (singleton pattern)
    try:
        from app.agent.triage_agent import get_triage_agent
        agent = get_triage_agent()
        logger.success(f"Agent initialized: {agent.llm_provider}")
    except Exception as e:
        logger.error(f"Agent initialization failed: {e}")
        logger.warning("API will start but triaging may not work")
    
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"LLM Provider: {settings.llm_provider}")
    logger.info(f"Embedding Provider: {settings.embedding_provider}")
    logger.info("=" * 70)
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
    ## AI-Powered Ticket Triaging Agent
    
    Automatically triage IT support tickets using:
    - **RAG (Retrieval-Augmented Generation)** - Search 9,442 historical tickets
    - **SOP Retrieval** - Find relevant procedures from 160+ SOPs
    - **LangChain ReAct Agent** - Intelligent reasoning and tool usage
    - **Confidence-Based Routing** - Auto-resolve, suggest, or escalate
    
    ### Key Features
    - Smart queue assignment to 9 specialized teams
    - Actionable resolution steps based on SOPs
    - Confidence scoring (0.0-1.0) for quality control
    - Historical pattern matching for consistency
    
    ### Endpoints
    - `POST /api/v1/triage` - Triage a new ticket
    - `GET /api/v1/health` - Check service health
    - `GET /api/v1/queues` - List available queues
    - `GET /api/v1/stats` - Agent statistics
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    debug=settings.debug
)


# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests with timing."""
    start_time = time.time()
    
    # Log request
    logger.info(f"{request.method} {request.url.path}")
    
    # Process request
    response = await call_next(request)
    
    # Log response
    duration = (time.time() - start_time) * 1000
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Duration: {duration:.2f}ms"
    )
    
    return response


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "InternalServerError",
            "message": "An unexpected error occurred",
            "details": str(exc) if settings.debug else None
        }
    )


# Include routers
app.include_router(triage_router)
app.include_router(auth_router)
app.include_router(
    google_chat_webhook_router,
    prefix="/api/v1/google-chat",
    tags=["google-chat"],
)
app.include_router(
    freshservice_webhook_router,
    prefix="/api/v1/freshservice",
    tags=["freshservice"],
)


# Root endpoint
@app.get("/", tags=["root"])
async def root():
    """API root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "online",
        "docs": "/docs",
        "health": "/api/v1/health"
    }


if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting development server...")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=2027,
        reload=True,
        log_level="info"
    )

\`\`\`

## backend/app/agent/triage_agent.py

```python
"""
Ticket Triaging Agent
Main LangChain ReAct agent that triages IT support tickets using RAG and SOP retrieval.
"""

import json
import re
import time
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum

from langchain.agents import AgentExecutor, create_react_agent
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain.schema import AgentAction, AgentFinish
from loguru import logger

from app.config import settings
from app.agent.tools import get_agent_tools
from app.agent.prompts import (
    create_agent_prompt,
    VALIDATION_RULES,
    ERROR_MESSAGES
)


class RoutingAction(str, Enum):
    """Routing actions based on confidence score."""
    AUTO_RESOLVE = "auto_resolve"
    ROUTE_WITH_SUGGESTION = "route_with_suggestion"
    ESCALATE_TO_HUMAN = "escalate_to_human"


class TriageResult:
    """Structured result from ticket triaging."""
    
    def __init__(
        self,
        queue: str,
        category: str,
        sub_category: str,
        resolution_steps: List[str],
        confidence: float,
        sop_reference: str,
        reasoning: str,
        routing_action: RoutingAction,
        raw_response: Optional[str] = None,
        validation_errors: Optional[List[str]] = None
    ):
        self.queue = queue
        self.category = category
        self.sub_category = sub_category
        self.resolution_steps = resolution_steps
        self.confidence = confidence
        self.sop_reference = sop_reference
        self.reasoning = reasoning
        self.routing_action = routing_action
        self.raw_response = raw_response
        self.validation_errors = validation_errors or []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            'queue': self.queue,
            'category': self.category,
            'sub_category': self.sub_category,
            'resolution_steps': self.resolution_steps,
            'confidence': self.confidence,
            'sop_reference': self.sop_reference,
            'reasoning': self.reasoning,
            'routing_action': self.routing_action.value,
            'validation_errors': self.validation_errors
        }
    
    def is_valid(self) -> bool:
        """Check if result has no validation errors."""
        return len(self.validation_errors) == 0


class TicketTriagingAgent:
    """
    AI agent for triaging IT support tickets.
    
    Uses LangChain ReAct agent with:
    - Ticket similarity search (RAG)
    - SOP procedure retrieval
    - Confidence-based routing
    """
    
    def __init__(
        self,
        llm_provider: Optional[str] = None,
        temperature: float = 0.1,
        max_retries: int = 1
    ):
        """
        Initialize triaging agent.
        
        Args:
            llm_provider: LLM provider (openai/groq/gemini) or None for config default
            temperature: LLM temperature (0.0 = deterministic, 1.0 = creative)
            max_retries: Maximum retry attempts for failed generations
        """
        self.llm_provider = llm_provider or settings.llm_provider
        self.temperature = temperature
        self.max_retries = max_retries
        
        # Initialize LLM
        self.llm = self._initialize_llm()
        
        # Get tools
        self.tools = get_agent_tools()
        
        logger.info(
            f"Triaging agent initialized: {self.llm_provider} "
            f"(temp={temperature}, tools={len(self.tools)})"
        )
    
    def _initialize_llm(self):
        """Initialize the LLM based on provider."""
        if self.llm_provider == "openai":
            return ChatOpenAI(
                model=settings.openai_model,
                temperature=self.temperature,
                openai_api_key=settings.openai_api_key,
            )
        elif self.llm_provider == "groq":
            from langchain_groq import ChatGroq
            return ChatGroq(
                model=settings.groq_model,
                temperature=self.temperature,
                groq_api_key=settings.groq_api_key,
            )
        elif self.llm_provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=settings.gemini_model,
                temperature=self.temperature,
                google_api_key=settings.google_api_key,
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_provider}")
    
    def _determine_routing_action(self, confidence: float) -> RoutingAction:
        """
        Determine routing action based on confidence score.
        
        Args:
            confidence: Confidence score (0.0 to 1.0)
            
        Returns:
            RoutingAction enum value
        """
        if confidence >= 0.85:
            return RoutingAction.AUTO_RESOLVE
        elif confidence >= 0.60:
            return RoutingAction.ROUTE_WITH_SUGGESTION
        else:
            return RoutingAction.ESCALATE_TO_HUMAN
    
    def _validate_response(self, response: Dict[str, Any]) -> List[str]:
        """
        Validate agent response against schema.
        
        Args:
            response: Parsed JSON response
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        # Check required fields
        for field, rules in VALIDATION_RULES.items():
            if rules.get('required', False) and field not in response:
                errors.append(f"Missing required field: {field}")
                continue
            
            if field not in response:
                continue
            
            value = response[field]
            
            # Type validation
            expected_type = rules.get('type')
            if expected_type == 'string' and not isinstance(value, str):
                errors.append(f"{field} must be a string")
            elif expected_type == 'float' and not isinstance(value, (int, float)):
                errors.append(f"{field} must be a number")
            elif expected_type == 'array' and not isinstance(value, list):
                errors.append(f"{field} must be an array")
            
            # String length validation
            if isinstance(value, str):
                min_len = rules.get('min_length', 0)
                max_len = rules.get('max_length', float('inf'))
                if len(value) < min_len:
                    errors.append(f"{field} must be at least {min_len} characters")
                if len(value) > max_len:
                    errors.append(f"{field} must be at most {max_len} characters")
            
            # Array validation
            if isinstance(value, list):
                min_items = rules.get('min_items', 0)
                max_items = rules.get('max_items', float('inf'))
                if len(value) < min_items:
                    errors.append(f"{field} must have at least {min_items} items")
                if len(value) > max_items:
                    errors.append(f"{field} must have at most {max_items} items")
            
            # Number range validation
            if isinstance(value, (int, float)):
                min_val = rules.get('min', float('-inf'))
                max_val = rules.get('max', float('inf'))
                if value < min_val or value > max_val:
                    errors.append(f"{field} must be between {min_val} and {max_val}")
            
            # Enum validation
            if 'must_be_one_of' in rules:
                if value not in rules['must_be_one_of']:
                    errors.append(
                        f"{field} must be one of: {', '.join(rules['must_be_one_of'][:3])}..."
                    )
        
        return errors
    
    def _parse_agent_response(self, response_text: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Parse agent's text response to extract JSON.
        
        Args:
            response_text: Raw text from agent
            
        Returns:
            Tuple of (parsed_dict, error_message)
        """
        text = str(response_text or "").strip()
        if not text:
            return None, "Empty model response"

        # 1) Direct JSON parse if entire output is JSON.
        try:
            parsed_direct = json.loads(text)
            if isinstance(parsed_direct, dict):
                return parsed_direct, None
        except Exception:
            pass

        # 2) Parse fenced JSON blocks first (```json ... ``` or ``` ... ```).
        fenced_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
        for block in fenced_blocks:
            block_text = block.strip()
            if not block_text:
                continue
            try:
                parsed_block = json.loads(block_text)
                if isinstance(parsed_block, dict):
                    return parsed_block, None
            except Exception:
                continue

        # 3) Fallback to first '{' ... last '}' extraction.
        start = text.find('{')
        end = text.rfind('}')
        if start == -1 or end == -1 or end <= start:
            return None, "No JSON object found in response"

        try:
            candidate = text[start:end + 1]
            parsed_candidate = json.loads(candidate)
            if isinstance(parsed_candidate, dict):
                return parsed_candidate, None
            return None, "Parsed JSON was not an object"
        except json.JSONDecodeError as e:
            return None, f"Invalid JSON: {str(e)}"
        except Exception as e:
            return None, f"Parse error: {str(e)}"

    def _extract_retry_seconds(self, message: str) -> Optional[float]:
        """Extract retry-after hint from provider error message when available."""
        match = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)s", message, flags=re.IGNORECASE)
        if not match:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None

    def _normalize_confidence(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Coerce confidence labels (high|medium|low) into numeric scores for routing logic."""
        confidence = parsed.get("confidence")
        if isinstance(confidence, str):
            label = confidence.strip().lower()
            mapping = {
                "high": 0.90,
                "medium": 0.72,
                "low": 0.45,
            }
            if label in mapping:
                parsed["confidence"] = mapping[label]
                return parsed

            # Handle accidental percentage or numeric strings from model output.
            try:
                numeric_value = float(label.replace("%", ""))
                parsed["confidence"] = numeric_value / 100.0 if numeric_value > 1.0 else numeric_value
            except ValueError:
                pass
        return parsed
    
    def triage(
        self,
        subject: str,
        description: str,
        max_iterations: int = 4,
        verbose: bool = False,
        allow_fallback: bool = True,
    ) -> TriageResult:
        """
        Triage a support ticket.
        
        Args:
            subject: Ticket subject
            description: Ticket description
            max_iterations: Maximum agent iterations
            verbose: Enable detailed logging
            
        Returns:
            TriageResult with queue, category, resolution, etc.
        """
        logger.info(f"Triaging ticket: '{subject[:60]}...'")
        
        # Create prompt
        prompt_text = create_agent_prompt(subject, description)
        
        # Create ReAct agent prompt template with required variables
        react_prompt = PromptTemplate.from_template(
            """{input}

You have access to the following tools:

{tools}

Use the following format STRICTLY:

Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now have enough information to provide the final answer
Final Answer: <ONLY the JSON object, no other text>

CRITICAL: Your Final Answer must be ONLY valid JSON. Do not add any explanation before or after the JSON.

Example Final Answer format:
Final Answer: {{"queue": "...", "category": "...", "sub_category": "...", "resolution_steps": [...], "confidence": 0.92, "sop_reference": "...", "reasoning": "..."}}

Begin!

Question: {input}
Thought: {agent_scratchpad}"""
        )
        
        # Create ReAct agent
        agent = create_react_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=react_prompt
        )
        
        # Create executor
        agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=verbose,
            max_iterations=max_iterations,
            handle_parsing_errors=True,
            return_intermediate_steps=True
        )
        
        # Run agent with retries
        for attempt in range(self.max_retries + 1):
            try:
                logger.info(f"Agent attempt {attempt + 1}/{self.max_retries + 1}")
                
                result = agent_executor.invoke({
                    "input": prompt_text
                })
                
                raw_output = result.get('output', '')
                
                # Parse JSON response
                parsed, parse_error = self._parse_agent_response(raw_output)
                
                if parse_error:
                    logger.warning(f"Parse error: {parse_error}")
                    if attempt < self.max_retries:
                        continue
                    else:
                        # Last attempt failed, return error result
                        return self._create_error_result(
                            subject, 
                            description,
                            f"Failed to parse response: {parse_error}",
                            raw_output
                        )
                
                # Validate response
                parsed = self._normalize_confidence(parsed)
                validation_errors = self._validate_response(parsed)
                
                if validation_errors:
                    logger.warning(f"Validation errors: {validation_errors}")
                    if attempt < self.max_retries:
                        # Add validation feedback to prompt
                        prompt_text += f"\n\nPrevious attempt had errors: {validation_errors}\nPlease correct and try again."
                        continue
                
                # Success! Create result
                routing_action = self._determine_routing_action(parsed['confidence'])
                
                result = TriageResult(
                    queue=parsed['queue'],
                    category=parsed['category'],
                    sub_category=parsed['sub_category'],
                    resolution_steps=parsed['resolution_steps'],
                    confidence=float(parsed['confidence']),
                    sop_reference=parsed['sop_reference'],
                    reasoning=parsed['reasoning'],
                    routing_action=routing_action,
                    raw_response=raw_output,
                    validation_errors=validation_errors
                )
                
                logger.success(
                    f"Triage complete: {result.queue} | "
                    f"Confidence: {result.confidence:.2%} | "
                    f"Action: {routing_action.value}"
                )
                
                return result
                
            except Exception as e:
                logger.error(f"Agent error on attempt {attempt + 1}: {e}")
                error_text = str(e)
                is_rate_limit = any(token in error_text.lower() for token in ["rate limit", "429", "tokens per minute", "rate_limit_exceeded"])
                if is_rate_limit and attempt < self.max_retries:
                    retry_after = self._extract_retry_seconds(error_text)
                    sleep_seconds = max(2.0, min(20.0, retry_after if retry_after is not None else 8.0))
                    logger.warning(f"Rate limit encountered. Retrying after {sleep_seconds:.2f}s")
                    time.sleep(sleep_seconds)
                    continue
                if attempt == self.max_retries:
                    if (
                        allow_fallback
                        and self.llm_provider == "groq"
                        and is_rate_limit
                        and settings.google_api_key
                    ):
                        logger.warning(
                            "Groq rate limit persisted after retries. Falling back to Gemini provider."
                        )
                        try:
                            fallback_agent = TicketTriagingAgent(
                                llm_provider="gemini",
                                temperature=self.temperature,
                                max_retries=0,
                            )
                            return fallback_agent.triage(
                                subject=subject,
                                description=description,
                                max_iterations=max_iterations,
                                verbose=verbose,
                                allow_fallback=False,
                            )
                        except Exception as fallback_exc:
                            logger.error(f"Gemini fallback failed: {fallback_exc}")
                    return self._create_error_result(
                        subject,
                        description,
                        f"Agent execution failed: {str(e)}",
                        None
                    )
        
        # Should not reach here, but just in case
        return self._create_error_result(
            subject,
            description,
            "Max retries exceeded",
            None
        )
    
    def _create_error_result(
        self,
        subject: str,
        description: str,
        error_message: str,
        raw_response: Optional[str]
    ) -> TriageResult:
        """
        Create a fallback result when agent fails.
        
        Args:
            subject: Original ticket subject
            description: Original ticket description
            error_message: Error that occurred
            raw_response: Raw agent output (if any)
            
        Returns:
            TriageResult with escalation to human
        """
        return TriageResult(
            queue="AMER - STACK Service Desk Group",  # Default queue
            category="Unknown",
            sub_category="Needs Manual Review",
            resolution_steps=[
                "Agent was unable to automatically triage this ticket",
                "Manual review required by service desk agent",
                f"Error: {error_message}"
            ],
            confidence=0.0,
            sop_reference="No SOP - Manual triage required",
            reasoning=f"Automatic triaging failed: {error_message}",
            routing_action=RoutingAction.ESCALATE_TO_HUMAN,
            raw_response=raw_response,
            validation_errors=[error_message]
        )


# Singleton instance
_agent_instance: Optional[TicketTriagingAgent] = None


def get_triage_agent(
    llm_provider: Optional[str] = None,
    force_recreate: bool = False
) -> TicketTriagingAgent:
    """
    Get or create triage agent instance (singleton).
    
    Args:
        llm_provider: LLM provider override
        force_recreate: Force creation of new instance
        
    Returns:
        TicketTriagingAgent instance
    """
    global _agent_instance
    
    if _agent_instance is None or force_recreate:
        _agent_instance = TicketTriagingAgent(llm_provider=llm_provider)
    
    return _agent_instance


def triage_ticket(
    subject: str,
    description: str,
    verbose: bool = False
) -> TriageResult:
    """
    Convenience function to triage a single ticket.
    
    Args:
        subject: Ticket subject
        description: Ticket description
        verbose: Enable verbose logging
        
    Returns:
        TriageResult
    """
    agent = get_triage_agent()
    return agent.triage(subject, description, verbose=verbose)

\`\`\`

## backend/app/agent/prompts.py

```python
"""
Prompt Templates for Ticket Triaging Agent
Contains all prompts, instructions, and examples for the LangChain agent.
"""

from typing import Dict, Any, Optional
from datetime import datetime


# Primary conversational prompt used before formal triage starts.
CONVERSATIONAL_SYSTEM_PROMPT = """You are an intelligent IT support assistant. Your goal is to help users resolve technical issues through natural, helpful conversation.

CONVERSATIONAL BEHAVIOR:
- Respond naturally like ChatGPT or Claude - friendly, clear, and adaptive
- Do NOT immediately treat every message as a ticket
- When intent is unclear, ask clarifying questions
- Build context progressively across multiple messages
- Only start formal triage when you have concrete issue details

REQUIRED INFORMATION BEFORE TRIAGE:
You need at least these details:
1. Clear problem statement (what is not working)
2. Symptoms or error messages (if applicable)
3. Basic context (when it started, what was tried)

If information is missing, ask specific follow-up questions.

CURRENT CONVERSATION CONTEXT:
{conversation_context}

USER MESSAGE: {user_message}

Based on the conversation phase and user intent, respond appropriately:
- If greeting: Welcome warmly and offer help
- If vague help request: Ask what specific issue they're experiencing
- If issue with details: Acknowledge and proceed to triage
- If continuation: Integrate new information and assess if ready for triage

Your response:"""


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

\`\`\`

## backend/app/agent/tools.py

```python
"""
LangChain Tools for Ticket Triaging Agent
Provides retrieval tools for similar tickets and SOP procedures.
"""

from typing import List, Dict, Any, Optional
from langchain.tools import Tool
from langchain.pydantic_v1 import BaseModel, Field
from loguru import logger

from app.vector.faiss_store import get_store
from app.vector.embedder import get_embedder
from app.db.session import SessionLocal
from app.models import SOPChunk as SOPChunkModel


class TicketSearchInput(BaseModel):
    """Input schema for ticket similarity search."""
    query: str = Field(
        description="The ticket description or issue to search for similar past tickets"
    )
    top_k: int = Field(
        default=2,
        description="Number of similar tickets to retrieve (default: 2)",
        ge=1,
        le=10
    )


class SOPSearchInput(BaseModel):
    """Input schema for SOP procedure search."""
    query: str = Field(
        description="The issue or problem to search for relevant SOP procedures"
    )
    top_k: int = Field(
        default=1,
        description="Number of SOP procedures to retrieve (default: 1)",
        ge=1,
        le=5
    )


class TicketRetriever:
    """Retrieves similar tickets from FAISS index."""
    
    def __init__(self):
        """Initialize retriever with embedder and FAISS store."""
        self.embedder = get_embedder()
        self.store = get_store("tickets")
        logger.info("Ticket retriever initialized")
    
    def search(self, query: str, top_k: int = 2) -> str:
        """
        Search for similar tickets.
        
        Args:
            query: Ticket description or issue
            top_k: Number of results to return
            
        Returns:
            Formatted string with similar ticket information
        """
        try:
            # Embed query
            query_embedding = self.embedder.embed_text(query)
            
            # Search FAISS
            results = self.store.search(
                query_embedding,
                top_k=top_k,
                score_threshold=0.3  # Filter low-quality matches
            )
            
            if not results:
                return "No similar tickets found."
            
            # Format results
            output = f"Found {len(results)} similar tickets:\n\n"
            
            for i, result in enumerate(results, 1):
                metadata = result['metadata']
                score = result['score']
                
                output += f"--- Ticket {i} (Similarity: {score:.2%}) ---\n"
                output += f"Subject: {metadata.get('subject', 'N/A')}\n"
                output += f"Queue: {metadata.get('group', 'N/A')}\n"
                output += f"Category: {metadata.get('category', 'N/A')}\n"
                output += f"Sub-Category: {metadata.get('sub_category', 'N/A')}\n"
                
                # Include description if available
                desc = metadata.get('description', '')
                if desc and len(desc) > 0:
                    # Truncate long descriptions
                    desc_preview = desc[:200] + "..." if len(desc) > 200 else desc
                    output += f"Description: {desc_preview}\n"
                
                output += "\n"
            
            logger.info(f"Ticket search: '{query[:50]}...' → {len(results)} results")
            return output
            
        except Exception as e:
            logger.error(f"Ticket search failed: {e}")
            return f"Error searching tickets: {str(e)}"


class SOPRetriever:
    """Retrieves relevant SOP procedures from FAISS index and database."""
    
    def __init__(self):
        """Initialize retriever with embedder and FAISS store."""
        self.embedder = get_embedder()
        self.store = get_store("sop")
        logger.info("SOP retriever initialized")
    
    def search(self, query: str, top_k: int = 1) -> str:
        """
        Search for relevant SOP procedures.
        
        Args:
            query: Issue or problem description
            top_k: Number of procedures to return
            
        Returns:
            Formatted string with SOP procedures
        """
        try:
            # Embed query
            query_embedding = self.embedder.embed_text(query)
            
            # Search FAISS
            results = self.store.search(
                query_embedding,
                top_k=top_k,
                score_threshold=0.25  # Lower threshold for SOPs
            )
            
            if not results:
                return "No relevant SOP procedures found. Use general troubleshooting knowledge."
            
            # Get full SOP content from database
            db = SessionLocal()
            try:
                output = f"Found {len(results)} relevant SOP procedures:\n\n"
                
                for i, result in enumerate(results, 1):
                    metadata = result['metadata']
                    score = result['score']
                    embedding_id = metadata.get('id')
                    
                    # Get full content from database
                    sop_chunk = db.query(SOPChunkModel).filter(
                        SOPChunkModel.embedding_id == embedding_id
                    ).first()
                    
                    if sop_chunk:
                        output += f"--- SOP {i}: [{sop_chunk.section_num}] {sop_chunk.title} ---\n"
                        output += f"Relevance: {score:.2%}\n"
                        output += f"Procedure:\n{sop_chunk.content}\n\n"
                    else:
                        # Fallback to metadata if DB lookup fails
                        output += f"--- SOP {i}: [{metadata.get('section_num')}] {metadata.get('title')} ---\n"
                        output += f"Relevance: {score:.2%}\n"
                        output += f"{metadata.get('content', 'Content not available')}\n\n"
                
                logger.info(f"SOP search: '{query[:50]}...' → {len(results)} procedures")
                return output
                
            finally:
                db.close()
            
        except Exception as e:
            logger.error(f"SOP search failed: {e}")
            return f"Error searching SOPs: {str(e)}"
    
    def get_by_section(self, section_num: str) -> str:
        """
        Get specific SOP by section number.
        
        Args:
            section_num: Section number (e.g., "1.1", "2.5")
            
        Returns:
            SOP procedure content
        """
        db = SessionLocal()
        try:
            sop = db.query(SOPChunkModel).filter(
                SOPChunkModel.section_num == section_num
            ).first()
            
            if sop:
                return f"[{sop.section_num}] {sop.title}\n\n{sop.content}"
            else:
                return f"SOP section {section_num} not found."
                
        finally:
            db.close()


# Initialize retrievers (singleton pattern)
_ticket_retriever = None
_sop_retriever = None


def get_ticket_retriever() -> TicketRetriever:
    """Get or create ticket retriever instance."""
    global _ticket_retriever
    if _ticket_retriever is None:
        _ticket_retriever = TicketRetriever()
    return _ticket_retriever


def get_sop_retriever() -> SOPRetriever:
    """Get or create SOP retriever instance."""
    global _sop_retriever
    if _sop_retriever is None:
        _sop_retriever = SOPRetriever()
    return _sop_retriever


def create_ticket_search_tool() -> Tool:
    """
    Create LangChain tool for ticket similarity search.
    
    Returns:
        Configured Tool instance
    """
    retriever = get_ticket_retriever()
    
    def search_tickets(query: str) -> str:
        """Search for similar past tickets to help with triaging."""
        return retriever.search(query, top_k=2)
    
    return Tool(
        name="search_similar_tickets",
        description=(
            "Search for similar past support tickets. "
            "Use this to find how similar issues were categorized and resolved. "
            "Input should be the ticket description or main issue. "
            "Returns up to 2 similar tickets with their queue, category, and resolution details."
        ),
        func=search_tickets,
    )


def create_sop_search_tool() -> Tool:
    """
    Create LangChain tool for SOP procedure search.
    
    Returns:
        Configured Tool instance
    """
    retriever = get_sop_retriever()
    
    def search_sops(query: str) -> str:
        """Search for relevant Standard Operating Procedures."""
        return retriever.search(query, top_k=1)
    
    return Tool(
        name="search_sop_procedures",
        description=(
            "Search for relevant Standard Operating Procedures (SOPs). "
            "Use this to find official troubleshooting steps and resolution procedures. "
            "Input should be the technical issue or problem type. "
            "Returns the single most relevant SOP procedure with detailed steps."
        ),
        func=search_sops,
    )


def get_agent_tools() -> List[Tool]:
    """
    Get all tools for the triaging agent.
    
    Returns:
        List of configured LangChain tools
    """
    return [
        create_ticket_search_tool(),
        create_sop_search_tool(),
    ]


def format_ticket_context(subject: str, description: str) -> str:
    """
    Format incoming ticket for agent context.
    
    Args:
        subject: Ticket subject
        description: Ticket description
        
    Returns:
        Formatted ticket string
    """
    output = "=== INCOMING TICKET ===\n"
    output += f"Subject: {subject}\n"
    
    if description and len(description.strip()) > 0:
        output += f"Description: {description}\n"
    else:
        output += "Description: (None provided)\n"
    
    output += "======================="
    
    return output


def extract_queue_info() -> Dict[str, Any]:
    """
    Get information about available queues and categories.
    
    Returns:
        Dictionary with queue metadata
    """
    return {
        "queues": [
            "AMER - STACK Service Desk Group",
            "AMER - Enterprise Applications",
            "AMER - Infra & Network",
            "AMER - GIS",
            "AMER - End User Computing",
            "AMER - DC Infra",
            "AMER - SharePoint",
            "AMER - Enterprise Unified Communications",
            "AMER - Access Management"
        ],
        "common_categories": [
            "Access Issues",
            "Hardware",
            "Software",
            "Network",
            "Email",
            "Onboarding",
            "Offboarding",
            "Password/Account",
            "Printing",
            "VPN/Remote Access"
        ],
        "routing_rules": {
            "confidence >= 0.85": "auto-resolve",
            "0.60 <= confidence < 0.85": "route to queue with suggestion",
            "confidence < 0.60": "escalate to human agent"
        }
    }

\`\`\`

## backend/app/routers/google_chat_webhook.py

```python
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
                    lines.append("Options: " + ", ".join(button_texts))

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

\`\`\`

## backend/app/services/google_chat_service.py

```python
"""Conversation state machine for Google Chat webhook chatbot."""
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.config import settings
from app.db.session import SessionLocal
from app.agent.triage_agent import get_triage_agent
from app.agent.prompts import create_conversational_prompt
from app.models import ChatConversation as ChatConversationModel
from app.services.triage_service import triage_ticket_async_start_threaded, triage_ticket_async_status
from app.utils.google_chat_cards import (
    create_dropdown_card,
    create_error_card,
    create_feature_coming_soon_card,
    create_processing_card,
    create_ai_solution_card,
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


def _generate_ai_solution(
    subject: str,
    description: str,
    triage_result: Dict[str, Any],
    attempt_index: int = 1,
    previous_solutions: Optional[List[str]] = None,
) -> str:
    prior_context = ""
    if previous_solutions:
        condensed = "\n".join([f"- {item}" for item in previous_solutions[-2:]])
        prior_context = (
            "Avoid repeating these prior AI suggestions exactly. "
            f"Prior suggestions:\n{condensed}\n"
        )

    prompt = (
        "You are an IT support assistant. Generate a concise AI-generated solution for the issue below. "
        "Keep it practical and safe. "
        f"This is alternative suggestion attempt #{attempt_index}. "
        "Provide:\n"
        "1) probable root cause\n"
        "2) best-effort remediation steps\n"
        "3) validation checks\n"
        "4) when to escalate\n\n"
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
        return _format_text_for_card(content)
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
        ai_solution = _generate_ai_solution(
            subject=str(data.get("subject") or ticket.get("subject") or "User issue"),
            description=str(data.get("description") or ""),
            triage_result=triage_result,
            attempt_index=next_attempt,
            previous_solutions=prior_solutions,
        )
        data["ai_solution"] = ai_solution
        prior_solutions.append(ai_solution)
        data["ai_solutions_history"] = prior_solutions[-5:]
        data["ai_solution_attempts"] = next_attempt
        _update_conversation(conversation.id, collected_data=data, step=STEP_SHOW_RESULTS)

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
        "Great to hear your issue is resolved. Thank you for using Service Desk AI. Reach out anytime you need help again.",
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
    data["ai_solution"] = _generate_ai_solution(
        subject=str(data.get("subject") or ticket.get("subject") or "User issue"),
        description=str(data.get("description") or ""),
        triage_result=triage_result,
    )
    _update_conversation(
        conversation.id,
        step=STEP_SHOW_RESULTS,
        collected_data=data,
        ticket_id=int(ticket["id"]),
        is_active=True,
    )
    return create_sop_solution_card(ticket=ticket, triage_result=triage_result, bot_name=_bot_name())


def _handle_ask_satisfaction_step(conversation: ChatConversationModel, user_input: str) -> Dict[str, Any]:
    if _is_satisfied_response(user_input):
        _update_conversation(
            conversation.id,
            step=STEP_COMPLETE,
            collected_data=dict(conversation.collected_data or {}),
            is_active=False,
        )
        return create_text_input_card(
            "Glad I could help. Thank you for using Service Desk AI.",
            bot_name=_bot_name(),
        )
    return create_text_input_card(
        "Thanks for the feedback. Type 'start' to create another ticket or share what still needs help.",
        bot_name=_bot_name(),
    )


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
        if action_value == ACTION_GET_AI_SOLUTION:
            return _handle_get_ai_solution(conversation, regenerate=False)
        if action_value == ACTION_ANOTHER_AI_SOLUTION:
            return _handle_get_ai_solution(conversation, regenerate=True)
        if action_value == ACTION_MARK_RESOLVED:
            return _handle_resolution_success(conversation)
        if action_value in {ACTION_AUTO_RESOLVE, ACTION_ESCALATE_TO_HUMAN}:
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

\`\`\`

## backend/app/services/triage_service.py

```python
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

\`\`\`

## backend/app/utils/google_chat_cards.py

```python
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
                    "or you can escalate to a human agent."
                ),
            }
        },
        _ai_followup_buttons(),
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

\`\`\`

## backend/app/models/chat_conversation.py

```python
"""Conversation state model for Google Chat webhook interactions."""

from datetime import datetime
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import relationship

from app.db.session import Base


class ChatConversation(Base):
    """Stores per-user Google Chat conversation state for triage flow."""

    __tablename__ = "chat_conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    google_chat_space_id = Column(String(255), nullable=False, index=True)
    google_chat_user_id = Column(String(255), nullable=False, index=True)
    google_chat_thread_id = Column(String(255), nullable=True, index=True)
    current_step = Column(String(50), nullable=False, default="welcome")
    collected_data = Column(JSON, nullable=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, nullable=False, default=True)

    ticket = relationship("Ticket", foreign_keys=[ticket_id])

    __table_args__ = (
        Index("idx_chat_conversation_space_user", "google_chat_space_id", "google_chat_user_id"),
        Index("idx_chat_conversation_active", "is_active"),
    )

    def __repr__(self) -> str:
        return (
            f"<ChatConversation(id={self.id}, space='{self.google_chat_space_id}', "
            f"user='{self.google_chat_user_id}', step='{self.current_step}')>"
        )


\`\`\`

## backend/app/routers/triage.py

```python
"""
Ticket triaging API router.
Main endpoints for Module 8.
"""

from fastapi import APIRouter, HTTPException, status, BackgroundTasks, Query
from loguru import logger
from dataclasses import dataclass
from uuid import uuid4

from app.schemas.triage import (
    TriageRequest,
    TriageResponse,
    AsyncTriageStartResponse,
    AsyncTriageJobStatusResponse,
    TicketsListResponse,
    TicketListItemResponse,
    TriageJobStatusEnum,
    HealthResponse,
    ErrorResponse,
    QueuesResponse,
    StatsResponse,
    QueueAnalyticsResponse,
    QueueAnalyticsItemResponse,
    RoutingActionEnum,
)
from app.agent.triage_agent import triage_ticket, get_triage_agent
from app.agent.prompts import VALIDATION_RULES
from app.config import settings
from app.db.session import SessionLocal
from app.models import Ticket as TicketModel, TriageResult as TriageResultModel
from app.services.triage_service import triage_ticket_sync
from datetime import datetime
from typing import Optional, Dict
from datetime import timedelta, date
from sqlalchemy import func, and_

router = APIRouter(
    prefix="/api/v1",
    tags=["triage"],
    responses={
        500: {"model": ErrorResponse, "description": "Internal server error"},
        400: {"model": ErrorResponse, "description": "Bad request"}
    }
)


@dataclass
class TriageJob:
    """In-memory async triage job state."""
    id: str
    status: TriageJobStatusEnum
    request: TriageRequest
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[TriageResponse] = None
    error: Optional[str] = None


TRIAGE_JOBS: Dict[str, TriageJob] = {}


def _map_persisted_routing_to_response(value: str) -> RoutingActionEnum:
    mapping = {
        "auto_resolve": RoutingActionEnum.AUTO_RESOLVE,
        "suggest": RoutingActionEnum.ROUTE_WITH_SUGGESTION,
        "escalate": RoutingActionEnum.ESCALATE_TO_HUMAN,
    }
    return mapping.get(value, RoutingActionEnum.ESCALATE_TO_HUMAN)


def _run_triage_job(job_id: str) -> None:
    """Background runner for async triage jobs."""
    job = TRIAGE_JOBS.get(job_id)
    if not job:
        return
    try:
        job.status = TriageJobStatusEnum.RUNNING
        job.started_at = datetime.utcnow()
        persisted = triage_ticket_sync(
            subject=job.request.subject,
            description=job.request.description,
        )
        triage_result = persisted["triage_result"]
        job.result = TriageResponse(
            queue=str(triage_result["queue"]),
            category=str(triage_result["category"]),
            sub_category=str(triage_result["sub_category"]),
            resolution_steps=[str(step) for step in (triage_result.get("resolution_steps") or [])],
            confidence=float(triage_result["confidence"]),
            sop_reference=str(triage_result["sop_reference"]),
            reasoning=str(triage_result["reasoning"]),
            routing_action=_map_persisted_routing_to_response(str(triage_result.get("routing_action", ""))),
            validation_errors=[],
            timestamp=datetime.utcnow(),
        )
        job.status = TriageJobStatusEnum.COMPLETED
        job.completed_at = datetime.utcnow()
        logger.success(f"Async triage job completed: {job_id}")
    except Exception as triage_error:
        job.status = TriageJobStatusEnum.FAILED
        job.error = str(triage_error)
        job.completed_at = datetime.utcnow()
        logger.error(f"Async triage job failed: {job_id} | {triage_error}")


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Check API health and component status"
)
async def health_check():
    """
    Check if the API and all components are operational.
    
    Returns:
        HealthResponse with status of all components
    """
    try:
        # Check agent initialization
        agent = get_triage_agent()
        agent_status = "healthy" if agent else "unhealthy"
        
        # Check vector stores
        from app.vector.faiss_store import FAISSStore
        try:
            ticket_store = FAISSStore("tickets")
            sop_store = FAISSStore("sop")
            vector_status = "healthy"
        except Exception as e:
            logger.warning(f"Vector store check failed: {e}")
            vector_status = "degraded"
        
        components = {
            "agent": agent_status,
            "vector_stores": vector_status,
            "llm_provider": settings.llm_provider,
            "embedding_provider": settings.embedding_provider
        }
        
        overall_status = "healthy" if all(
            v == "healthy" for v in [agent_status, vector_status]
        ) else "degraded"
        
        return HealthResponse(
            status=overall_status,
            version=settings.app_version,
            timestamp=datetime.utcnow(),
            components=components
        )
    
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            version=settings.app_version,
            timestamp=datetime.utcnow(),
            components={"error": str(e)}
        )


@router.post(
    "/triage",
    response_model=TriageResponse,
    status_code=status.HTTP_200_OK,
    summary="Triage a Ticket",
    description="Analyze a support ticket and provide triaging recommendations",
    responses={
        200: {
            "description": "Ticket successfully triaged",
            "content": {
                "application/json": {
                    "example": {
                        "queue": "AMER - STACK Service Desk Group",
                        "category": "Access Issues",
                        "sub_category": "Password Reset",
                        "resolution_steps": [
                            "Verify user identity",
                            "Reset password in Active Directory",
                            "Confirm successful login"
                        ],
                        "confidence": 0.92,
                        "sop_reference": "Section 1.1 - Password Reset",
                        "reasoning": "Clear password reset request",
                        "routing_action": "auto_resolve",
                        "validation_errors": [],
                        "timestamp": "2024-01-15T10:30:00Z"
                    }
                }
            }
        }
    }
)
async def triage_ticket_endpoint(request: TriageRequest):
    """
    Triage a support ticket using the AI agent.
    
    The agent will:
    1. Search for similar historical tickets
    2. Find relevant SOP procedures
    3. Analyze the ticket and provide routing recommendations
    4. Return actionable resolution steps
    
    Args:
        request: TriageRequest with subject, description, and options
        
    Returns:
        TriageResponse with queue, category, steps, confidence, etc.
        
    Raises:
        HTTPException: If triaging fails
    """
    try:
        logger.info(f"Triaging ticket: '{request.subject[:60]}...'")
        
        # Perform triaging
        result = triage_ticket(
            subject=request.subject,
            description=request.description,
            verbose=request.verbose
        )
        
        # Convert to response model
        response = TriageResponse(
            queue=result.queue,
            category=result.category,
            sub_category=result.sub_category,
            resolution_steps=result.resolution_steps,
            confidence=result.confidence,
            sop_reference=result.sop_reference,
            reasoning=result.reasoning,
            routing_action=result.routing_action,
            validation_errors=result.validation_errors,
            timestamp=datetime.utcnow()
        )
        
        logger.success(
            f"Ticket triaged: {result.queue} | "
            f"Confidence: {result.confidence:.2%} | "
            f"Action: {result.routing_action.value}"
        )
        
        return response
    
    except Exception as e:
        logger.error(f"Triage failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "TriageError",
                "message": f"Failed to triage ticket: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            }
        )


@router.post(
    "/tickets/triage",
    response_model=AsyncTriageStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start Async Triage Job",
    description="Queue a ticket triage job and return a polling token"
)
async def triage_ticket_async_endpoint(request: TriageRequest, background_tasks: BackgroundTasks):
    """Queue an asynchronous triage job and return a job id for polling."""
    job_id = str(uuid4())
    TRIAGE_JOBS[job_id] = TriageJob(
        id=job_id,
        status=TriageJobStatusEnum.QUEUED,
        request=request,
        created_at=datetime.utcnow()
    )
    background_tasks.add_task(_run_triage_job, job_id)
    logger.info(f"Queued async triage job: {job_id}")
    return AsyncTriageStartResponse(
        job_id=job_id,
        status=TriageJobStatusEnum.QUEUED,
        poll_url=f"/api/v1/tickets/triage/{job_id}",
        timestamp=datetime.utcnow()
    )


@router.get(
    "/tickets/triage/{job_id}",
    response_model=AsyncTriageJobStatusResponse,
    summary="Get Async Triage Job Status",
    description="Poll an async triage job until completion"
)
async def triage_ticket_async_status_endpoint(job_id: str):
    """Return current status for a previously queued triage job."""
    job = TRIAGE_JOBS.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "JobNotFound",
                "message": f"No triage job found for id: {job_id}",
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    return AsyncTriageJobStatusResponse(
        job_id=job.id,
        status=job.status,
        result=job.result,
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        timestamp=datetime.utcnow()
    )


@router.get(
    "/tickets",
    response_model=TicketsListResponse,
    summary="List Tickets",
    description="Fetch paginated tickets with optional filters for queue/category/search"
)
async def list_tickets(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    queue: str = Query(default=""),
    category: str = Query(default=""),
    search: str = Query(default="")
):
    """Return paginated tickets for frontend tickets page."""
    db = SessionLocal()
    try:
        query = db.query(TicketModel)

        if queue:
            query = query.filter(TicketModel.raw_group == queue)
        if category:
            query = query.filter(TicketModel.raw_category == category)
        if search:
            like_search = f"%{search}%"
            query = query.filter(
                (TicketModel.subject.ilike(like_search)) |
                (TicketModel.description.ilike(like_search))
            )

        total = query.count()
        rows = (
            query
            .order_by(TicketModel.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )

        tickets: list[TicketListItemResponse] = []
        for ticket in rows:
            latest_triage = (
                db.query(TriageResultModel)
                .filter(TriageResultModel.ticket_id == ticket.id)
                .order_by(TriageResultModel.created_at.desc())
                .first()
            )

            routing = "routed"
            confidence = 0.7
            reasoning = ""
            sop_reference = ""
            resolution_steps: list[str] = []
            category_value = ticket.raw_category or "General Incident"
            sub_category_value = ticket.raw_subcategory or ""

            if latest_triage:
                confidence = latest_triage.confidence
                reasoning = latest_triage.reasoning or ""
                sop_reference = latest_triage.sop_reference or ""
                resolution_steps = latest_triage.resolution_steps or []
                category_value = latest_triage.category or category_value
                sub_category_value = latest_triage.sub_category or sub_category_value

                if latest_triage.routing_action == "auto_resolve":
                    routing = "auto-resolved"
                elif latest_triage.routing_action == "escalate":
                    routing = "escalated"
                else:
                    routing = "routed"

            tickets.append(
                TicketListItemResponse(
                    id=f"INC-{ticket.id:06d}",
                    subject=ticket.subject,
                    queue=ticket.raw_group or "STACK Service Desk",
                    category=category_value,
                    confidence=confidence,
                    routing=routing,
                    created_at=ticket.created_at,
                    description=ticket.description or "",
                    sub_category=sub_category_value,
                    sop_reference=sop_reference,
                    reasoning=reasoning,
                    resolution_steps=resolution_steps
                )
            )

        return TicketsListResponse(
            tickets=tickets,
            total=total,
            page=page,
            limit=limit
        )
    except Exception as e:
        logger.error(f"Failed to list tickets: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "TicketsListError",
                "message": f"Failed to retrieve tickets: {str(e)}"
            }
        )
    finally:
        db.close()


@router.get(
    "/queues",
    response_model=QueuesResponse,
    summary="Get Available Queues",
    description="List all available support queues"
)
async def get_queues():
    """
    Get list of all available support queues.
    
    Returns:
        QueuesResponse with list of queue names
    """
    queues = VALIDATION_RULES["queue"]["must_be_one_of"]
    
    return QueuesResponse(
        queues=queues,
        count=len(queues)
    )


@router.get(
    "/queues/analytics",
    response_model=QueueAnalyticsResponse,
    summary="Get Queue Analytics",
    description="Queue KPIs and trend data for a selected date range"
)
async def get_queue_analytics(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
):
    """Return queue cards and trends for selected date range."""
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "InvalidDateFormat",
                "message": "start_date and end_date must be in YYYY-MM-DD format",
            },
        )

    if end < start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "InvalidDateRange",
                "message": "end_date must be greater than or equal to start_date",
            },
        )

    db = SessionLocal()
    try:
        start_dt = datetime.combine(start, datetime.min.time())
        end_dt = datetime.combine(end, datetime.max.time())

        labels: list[str] = []
        cursor: date = start
        while cursor <= end:
            labels.append(cursor.strftime("%d %b"))
            cursor += timedelta(days=1)

        ticket_rows = (
            db.query(TicketModel)
            .filter(and_(TicketModel.created_at >= start_dt, TicketModel.created_at <= end_dt))
            .all()
        )
        ticket_ids = [ticket.id for ticket in ticket_rows]
        total_open = len(ticket_rows)

        triage_rows = []
        if ticket_ids:
            triage_rows = (
                db.query(TriageResultModel)
                .filter(TriageResultModel.ticket_id.in_(ticket_ids))
                .all()
            )

        triage_by_ticket = {}
        for triage in triage_rows:
            triage_by_ticket[triage.ticket_id] = triage

        queue_buckets: dict[str, dict] = {}

        for ticket in ticket_rows:
            triage = triage_by_ticket.get(ticket.id)
            queue_name = (triage.queue if triage and triage.queue else ticket.raw_group) or "Other Queues"
            category_name = (triage.category if triage and triage.category else ticket.raw_category) or "General Incident"
            confidence = float(triage.confidence) if triage and triage.confidence is not None else 0.0
            day_key = ticket.created_at.date()

            if queue_name not in queue_buckets:
                queue_buckets[queue_name] = {
                    "ticket_count": 0,
                    "confidence_total": 0.0,
                    "confidence_count": 0,
                    "categories": {},
                    "day_counts": {},
                }

            bucket = queue_buckets[queue_name]
            bucket["ticket_count"] += 1
            bucket["confidence_total"] += confidence
            bucket["confidence_count"] += 1
            bucket["categories"][category_name] = bucket["categories"].get(category_name, 0) + 1
            bucket["day_counts"][day_key] = bucket["day_counts"].get(day_key, 0) + 1

        queues: list[QueueAnalyticsItemResponse] = []
        for queue_name, bucket in queue_buckets.items():
            avg_confidence = (
                bucket["confidence_total"] / bucket["confidence_count"]
                if bucket["confidence_count"] > 0
                else 0.0
            )
            top_category = "General Incident"
            if bucket["categories"]:
                top_category = max(bucket["categories"], key=bucket["categories"].get)

            trend_values: list[int] = []
            trend_cursor = start
            while trend_cursor <= end:
                trend_values.append(int(bucket["day_counts"].get(trend_cursor, 0)))
                trend_cursor += timedelta(days=1)

            queues.append(
                QueueAnalyticsItemResponse(
                    name=queue_name,
                    ticket_count=int(bucket["ticket_count"]),
                    avg_confidence=max(0.0, min(float(avg_confidence), 1.0)),
                    top_category=top_category,
                    trend=trend_values,
                )
            )

        queues.sort(key=lambda item: item.ticket_count, reverse=True)

        sla_breached = sum(1 for triage in triage_rows if triage.routing_action == "escalate")

        avg_resolution_hours = (
            (sum((triage.processing_time_ms or 0) for triage in triage_rows) / 3600000.0) / len(triage_rows)
            if triage_rows
            else 0.0
        )

        return QueueAnalyticsResponse(
            start_date=start_date,
            end_date=end_date,
            labels=labels,
            total_open=int(total_open),
            sla_breached=int(sla_breached),
            avg_resolution_hours=round(float(avg_resolution_hours), 2),
            queues=queues,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch queue analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "QueueAnalyticsError",
                "message": f"Failed to retrieve queue analytics: {str(e)}"
            }
        )
    finally:
        db.close()


@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="Get Agent Statistics",
    description="Get statistics about the triaging agent and available data"
)
async def get_stats():
    """
    Get statistics about the agent and its data sources.
    
    Returns:
        StatsResponse with counts and configuration info
    """
    try:
        from app.vector.faiss_store import FAISSStore
        
        # Get vector store stats
        ticket_store = FAISSStore("tickets")
        ticket_store.load()  # Load the index
        
        sop_store = FAISSStore("sop")
        sop_store.load()  # Load the index
        
        ticket_count = ticket_store.index.ntotal if ticket_store.index else 0
        sop_count = sop_store.index.ntotal if sop_store.index else 0
        
        # Get agent info
        agent = get_triage_agent()
        tool_names = [tool.name for tool in agent.tools]
        
        return StatsResponse(
            total_tickets_in_db=ticket_count,
            total_sop_chunks=sop_count,
            llm_provider=settings.llm_provider,
            embedding_provider=settings.embedding_provider,
            available_tools=tool_names
        )
    
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "StatsError",
                "message": f"Failed to retrieve statistics: {str(e)}"
            }
        )


@router.get(
    "/",
    summary="API Root",
    description="API information and available endpoints"
)
async def root():
    """
    Get API root information.
    
    Returns:
        API metadata and available endpoints
    """
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "endpoints": {
            "health": "/api/v1/health",
            "triage": "/api/v1/triage",
            "queues": "/api/v1/queues",
            "stats": "/api/v1/stats",
            "docs": "/docs",
            "redoc": "/redoc"
        },
        "description": "AI-powered ticket triaging agent for IT Service Desk"
    }


__all__ = ['router']

\`\`\`

## frontend/src/api/client.js

```javascript
import axios from 'axios'

// Use relative path to leverage Vite proxy in dev, or full URL in production
const API_BASE_URL = import.meta.env.VITE_API_URL || (
  import.meta.env.DEV ? '' : 'http://localhost:2027'
)

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000, // 60 seconds for triaging
  headers: {
    'Content-Type': 'application/json',
  }
})

// Request interceptor for logging
api.interceptors.request.use(
  (config) => {
    console.log(`API Request: ${config.method.toUpperCase()} ${config.url}`)
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => {
    console.log(`API Response: ${response.status} ${response.config.url}`)
    return response
  },
  (error) => {
    console.error('API Error:', error.response?.data || error.message)
    return Promise.reject(error)
  }
)

// API Methods

export const getHealth = async () => {
  const response = await api.get('/api/v1/health')
  return response.data
}

export const getQueues = async () => {
  const response = await api.get('/api/v1/queues')
  return response.data
}

export const getStats = async () => {
  const response = await api.get('/api/v1/stats')
  return response.data
}

export const triageTicket = async (ticketData) => {
  const response = await api.post('/api/v1/triage', ticketData)
  return response.data
}

export const startAsyncTriage = async (ticketData) => {
  const response = await api.post('/api/v1/tickets/triage', ticketData)
  return response.data
}

export const getAsyncTriageStatus = async (jobId) => {
  const response = await api.get(`/api/v1/tickets/triage/${jobId}`)
  return response.data
}

export const getTickets = async ({ page = 1, limit = 20, queue = '', category = '', search = '' } = {}) => {
  const response = await api.get('/api/v1/tickets', {
    params: { page, limit, queue, category, search },
  })
  return response.data
}

export const getQueueAnalytics = async ({ startDate, endDate }) => {
  const response = await api.get('/api/v1/queues/analytics', {
    params: { start_date: startDate, end_date: endDate },
  })
  return response.data
}

export const signupUser = async ({ email, password, full_name = null, role = 'Service Desk User' }) => {
  const response = await api.post('/api/v1/auth/signup', {
    email,
    password,
    full_name,
    role,
  })
  return response.data
}

export const loginUser = async ({ email, password }) => {
  const response = await api.post('/api/v1/auth/login', {
    email,
    password,
  })
  return response.data
}

export default api

\`\`\`

## frontend/src/pages/TriagePage.tsx

```tsx
import { AlertCircle, Bot, Loader2, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { getAsyncTriageStatus, startAsyncTriage } from '../api/client'
import { cn } from '../lib/utils'
import TriageResultCard from '../components/TriageResultCard'
import type { TriagePageProps, TriageResult } from '../types'

interface TriageFormState {
  subject: string
  description: string
  manualQueue: string
  manualCategory: string
}

const initialFormState: TriageFormState = {
  subject: '',
  description: '',
  manualQueue: '',
  manualCategory: '',
}

const queueOptions = [
  'STACK Service Desk',
  'Enterprise Apps',
  'Infra & Network',
  'End User Computing',
  'Other Queues',
]

const categoryOptions = [
  'Access Management',
  'Enterprise Platform',
  'Network Services',
  'Endpoint Support',
  'General Incident',
]

const inferRouting = (confidence: number): TriageResult['routing'] => {
  if (confidence >= 0.85) return 'auto-resolved'
  if (confidence >= 0.6) return 'routed'
  return 'escalated'
}

const toResultModel = (payload: Record<string, unknown>, overrides: TriageFormState): TriageResult => {
  const confidence = typeof payload.confidence === 'number' ? payload.confidence : 0.7
  return {
    queue: overrides.manualQueue || String(payload.queue ?? 'STACK Service Desk'),
    category: overrides.manualCategory || String(payload.category ?? 'General Incident'),
    sub_category: String(payload.sub_category ?? 'General'),
    resolution_steps: Array.isArray(payload.resolution_steps)
      ? payload.resolution_steps.map((step) => String(step))
      : ['Validate incident details', 'Execute SOP workflow', 'Confirm resolution with requester'],
    confidence,
    sop_reference: String(payload.sop_reference ?? 'SOP-STACK-100'),
    reasoning: String(payload.reasoning ?? 'Routing selected based on issue pattern confidence.'),
    routing: inferRouting(confidence),
    timestamp: new Date().toISOString(),
  }
}

const TriageResultSkeleton = () => (
  <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800 dark:shadow-none">
    <div className="mb-4 h-6 w-40 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
    <div className="mb-4 h-28 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-700/60" />
    <div className="mb-4 grid gap-2">
      <div className="h-4 w-full animate-pulse rounded bg-slate-100 dark:bg-slate-700/60" />
      <div className="h-4 w-11/12 animate-pulse rounded bg-slate-100 dark:bg-slate-700/60" />
      <div className="h-4 w-4/5 animate-pulse rounded bg-slate-100 dark:bg-slate-700/60" />
    </div>
    <div className="h-10 w-44 animate-pulse rounded-lg bg-slate-200 dark:bg-slate-700" />
  </div>
)

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

export const TriagePage = ({ onTriageSaved }: TriagePageProps) => {
  const [formState, setFormState] = useState<TriageFormState>(initialFormState)
  const [result, setResult] = useState<TriageResult | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [actionMessage, setActionMessage] = useState('')

  const handleAnalyze = async () => {
    if (!formState.subject.trim() || !formState.description.trim()) {
      setError('Subject and description are required before analysis.')
      return
    }

    setIsLoading(true)
    setError('')
    setActionMessage('')

    try {
      const startResponse = await startAsyncTriage({
        subject: formState.subject,
        description: formState.description,
      })
      const jobId = String(startResponse?.job_id ?? '')
      if (!jobId) {
        throw new Error('Invalid async triage job id.')
      }

      let finalPayload: Record<string, unknown> | null = null
      for (let attempt = 0; attempt < 60; attempt += 1) {
        const statusResponse = await getAsyncTriageStatus(jobId)
        const jobStatus = String(statusResponse?.status ?? '')
        if (jobStatus === 'completed') {
          finalPayload = (statusResponse?.result ?? null) as Record<string, unknown> | null
          break
        }
        if (jobStatus === 'failed') {
          throw new Error(String(statusResponse?.error ?? 'Async triage job failed.'))
        }
        await wait(1500)
      }

      if (!finalPayload) {
        throw new Error('Triage still processing. Please retry in a moment.')
      }

      const normalized = toResultModel(finalPayload, formState)
      setResult(normalized)
      onTriageSaved?.(normalized)
    } catch (analysisError) {
      setError(analysisError instanceof Error ? analysisError.message : 'Unable to analyze ticket.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <section className="grid grid-cols-1 gap-6 xl:grid-cols-5">
      <article className="xl:col-span-2 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800 dark:shadow-none">
        <header className="mb-5">
          <h2 className="text-lg font-semibold tracking-tight text-slate-900 dark:text-slate-100">
            Ticket Submission
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Enter ticket details to run real-time AI triage.
          </p>
        </header>

        <div className="space-y-4">
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-200">Subject</span>
            <input
              type="text"
              value={formState.subject}
              onChange={(event) =>
                setFormState((prev) => ({ ...prev, subject: event.target.value }))
              }
              placeholder="Brief incident summary"
              className="h-11 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm text-slate-900 outline-none transition-all duration-200 focus:border-brand-jade focus:bg-white dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:bg-slate-900"
            />
          </label>

          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-200">
              Description
            </span>
            <textarea
              rows={6}
              value={formState.description}
              onChange={(event) =>
                setFormState((prev) => ({ ...prev, description: event.target.value }))
              }
              placeholder="Provide detailed context, impact, and observed errors."
              className="w-full resize-y rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900 outline-none transition-all duration-200 focus:border-brand-jade focus:bg-white dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:bg-slate-900"
            />
          </label>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-200">
                Queue Override
              </span>
              <select
                value={formState.manualQueue}
                onChange={(event) =>
                  setFormState((prev) => ({ ...prev, manualQueue: event.target.value }))
                }
                className="h-11 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm text-slate-900 outline-none transition-all duration-200 focus:border-brand-jade focus:bg-white dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:bg-slate-900"
              >
                <option value="">AI Suggested</option>
                {queueOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-200">
                Category Override
              </span>
              <select
                value={formState.manualCategory}
                onChange={(event) =>
                  setFormState((prev) => ({ ...prev, manualCategory: event.target.value }))
                }
                className="h-11 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm text-slate-900 outline-none transition-all duration-200 focus:border-brand-jade focus:bg-white dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:bg-slate-900"
              >
                <option value="">AI Suggested</option>
                {categoryOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {error && (
            <div className="inline-flex w-full items-center gap-2 rounded-lg border border-danger-red/30 bg-danger-red/10 px-3 py-2 text-sm text-danger-red">
              <AlertCircle className="h-4 w-4" />
              {error}
            </div>
          )}

          <button
            type="button"
            onClick={handleAnalyze}
            disabled={isLoading}
            className={cn(
              'inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-brand-jade px-4 text-sm font-semibold text-white transition-all duration-200 hover:bg-brand-jade-light disabled:cursor-not-allowed disabled:opacity-70',
            )}
          >
            {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            Analyze Ticket
          </button>
        </div>
      </article>

      <article className="xl:col-span-3 space-y-4">
        {isLoading && <TriageResultSkeleton />}

        {!isLoading && result && (
          <>
            <TriageResultCard
              result={result}
              onAccept={() => setActionMessage('Feature coming soon.')}
              onOverride={() => setActionMessage('AI-generated solution is now visible below.')}
              onEscalate={() => setActionMessage('Feature coming soon.')}
            />
            {actionMessage && (
              <div className="rounded-lg border border-brand-jade/30 bg-brand-jade-muted px-4 py-2 text-sm text-brand-jade dark:bg-brand-jade/15 dark:text-brand-jade-light">
                {actionMessage}
              </div>
            )}
          </>
        )}

        {!isLoading && !result && (
          <div className="flex min-h-[360px] flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white p-6 text-center dark:border-slate-600 dark:bg-slate-800">
            <span className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-brand-jade-muted text-brand-jade dark:bg-brand-jade/15 dark:text-brand-jade-light">
              <Bot className="h-6 w-6" />
            </span>
            <h3 className="text-lg font-semibold tracking-tight text-slate-900 dark:text-slate-100">
              AI Result Panel
            </h3>
            <p className="mt-1 max-w-md text-sm text-slate-500 dark:text-slate-400">
              Submit a ticket to view confidence score, queue recommendation, SOP reference, and resolution steps.
            </p>
          </div>
        )}
      </article>
    </section>
  )
}

export default TriagePage

\`\`\`

## frontend/src/components/TriageResultCard.tsx

```tsx
import { Bot, ChevronDown, ChevronUp, CircleCheck, Clock3, ExternalLink, ListChecks } from 'lucide-react'
import { useMemo, useState } from 'react'
import { cn } from '../lib/utils'
import ConfidenceGauge from './ConfidenceGauge'
import type { TriageResult, TriageResultCardProps, TriageRoutingDecision } from '../types'

const getRoutingFromScore = (score: number): TriageRoutingDecision => {
  if (score >= 0.85) return 'auto-resolved'
  if (score >= 0.6) return 'routed'
  return 'escalated'
}

const routingBadgeClasses: Record<TriageRoutingDecision, string> = {
  'auto-resolved':
    'bg-brand-jade-muted text-brand-jade border border-brand-jade/30 dark:bg-brand-jade/15 dark:text-brand-jade-light dark:border-brand-jade/30',
  routed:
    'bg-amber-50 text-amber-700 border border-amber-200 dark:bg-warning-amber/15 dark:text-amber-300 dark:border-warning-amber/30',
  escalated:
    'bg-red-50 text-red-700 border border-red-200 dark:bg-danger-red/15 dark:text-red-300 dark:border-danger-red/30',
}

const queueBadgeClass = (queue: string) => {
  if (/stack/i.test(queue)) return 'bg-brand-jade-muted text-brand-jade dark:bg-brand-jade/15 dark:text-brand-jade-light'
  if (/enterprise|apps/i.test(queue)) return 'bg-blue-50 text-blue-700 dark:bg-brand-accent/15 dark:text-blue-300'
  if (/infra|network/i.test(queue)) return 'bg-amber-50 text-amber-700 dark:bg-warning-amber/15 dark:text-amber-300'
  return 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200'
}

export const TriageResultCard = ({
  result,
  onAccept,
  onOverride,
  onEscalate,
}: TriageResultCardProps) => {
  const [showAllSteps, setShowAllSteps] = useState(false)
  const [showReasoning, setShowReasoning] = useState(true)
  const [showAISolution, setShowAISolution] = useState(false)
  const routingDecision = result.routing ?? getRoutingFromScore(result.confidence)
  const visibleSteps = showAllSteps ? result.resolution_steps : result.resolution_steps.slice(0, 3)
  const hasMoreSteps = result.resolution_steps.length > 3
  const timestamp = useMemo(
    () => (result.timestamp ? new Date(result.timestamp) : new Date()),
    [result.timestamp],
  )

  return (
    <article className="rounded-xl border border-slate-200 border-l-4 border-l-brand-jade bg-white p-6 shadow-sm dark:border-slate-700 dark:border-l-brand-jade dark:bg-slate-800 dark:shadow-none">
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-brand-jade-muted text-brand-jade dark:bg-brand-jade/15 dark:text-brand-jade-light">
            <Bot className="h-4.5 w-4.5" />
          </span>
          <div>
            <h3 className="text-lg font-semibold tracking-tight text-slate-900 dark:text-slate-100">
              Triage Result
            </h3>
            <p className="inline-flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
              <Clock3 className="h-3.5 w-3.5" />
              {timestamp.toLocaleString()}
            </p>
          </div>
        </div>

        <span className={cn('inline-flex rounded-full px-3 py-1 text-xs font-medium', routingBadgeClasses[routingDecision])}>
          {routingDecision}
        </span>
      </header>

      <div className="mb-5 flex flex-col justify-between gap-4 rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900/40 sm:flex-row sm:items-center">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Assigned Queue</p>
          <span className={cn('mt-2 inline-flex rounded-full px-4 py-1.5 text-sm font-semibold', queueBadgeClass(result.queue))}>
            {result.queue}
          </span>
        </div>
        <div className="sm:pr-2">
          <ConfidenceGauge score={result.confidence} />
        </div>
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <span className="text-sm font-medium text-slate-600 dark:text-slate-300">SOP Reference</span>
        <a
          href="#"
          onClick={(event) => event.preventDefault()}
          className="inline-flex items-center gap-1 rounded-lg bg-brand-jade-muted px-3 py-1.5 font-mono text-xs text-brand-jade transition-all duration-200 hover:bg-brand-jade hover:text-white dark:bg-brand-jade/15 dark:text-brand-jade-light dark:hover:bg-brand-jade dark:hover:text-white"
        >
          {result.sop_reference}
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      </div>

      <section className="mb-5 rounded-xl border border-slate-200 p-4 dark:border-slate-700">
        <div className="mb-3 flex items-center justify-between">
          <p className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
            <ListChecks className="h-4 w-4 text-brand-jade" />
            SOP Solution
          </p>
          {hasMoreSteps && (
            <button
              type="button"
              onClick={() => setShowAllSteps((prev) => !prev)}
              className="inline-flex items-center gap-1 text-xs font-medium text-brand-accent transition-all duration-200 hover:text-blue-700 dark:hover:text-blue-300"
            >
              {showAllSteps ? (
                <>
                  Show less <ChevronUp className="h-3.5 w-3.5" />
                </>
              ) : (
                <>
                  Show all <ChevronDown className="h-3.5 w-3.5" />
                </>
              )}
            </button>
          )}
        </div>

        <ol className="space-y-2">
          {visibleSteps.map((step, index) => (
            <li key={`${step}-${index}`} className="flex items-start gap-2.5 text-sm text-slate-700 dark:text-slate-200">
              <CircleCheck className="mt-0.5 h-4 w-4 shrink-0 text-brand-jade" />
              <span>{step}</span>
            </li>
          ))}
        </ol>
      </section>

      {showAISolution && (
        <section className="mb-5 rounded-xl border border-slate-200 p-4 dark:border-slate-700">
          <button
            type="button"
            onClick={() => setShowReasoning((prev) => !prev)}
            className="mb-3 inline-flex items-center gap-1 text-sm font-semibold text-slate-900 transition-all duration-200 hover:text-brand-accent dark:text-slate-100"
          >
            AI solution:
            {showReasoning ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
          {showReasoning && (
            <blockquote className="border-l-2 border-slate-300 pl-3 text-sm italic text-slate-500 dark:border-slate-600 dark:text-slate-400">
              {result.reasoning}
            </blockquote>
          )}
        </section>
      )}

      <footer className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => {
            setShowAISolution(true)
            onOverride()
          }}
          className="inline-flex items-center justify-center rounded-lg bg-brand-jade px-4 py-2 text-sm font-semibold text-white transition-all duration-200 hover:bg-brand-jade-light"
        >
          Get AI Solution
        </button>
        <button
          type="button"
          onClick={onAccept}
          className="inline-flex items-center justify-center rounded-lg border border-brand-accent px-4 py-2 text-sm font-semibold text-brand-accent transition-all duration-200 hover:bg-blue-50 dark:hover:bg-brand-accent/15"
        >
          Auto Resolve
        </button>
        <button
          type="button"
          onClick={onEscalate}
          className="inline-flex items-center justify-center rounded-lg border border-danger-red px-4 py-2 text-sm font-semibold text-danger-red transition-all duration-200 hover:bg-red-50 dark:hover:bg-danger-red/15"
        >
          Escalate to Human
        </button>
      </footer>
    </article>
  )
}

export default TriageResultCard

\`\`\`
