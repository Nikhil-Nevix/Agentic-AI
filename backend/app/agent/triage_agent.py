"""
Ticket Triaging Agent
Main LangChain ReAct agent that triages IT support tickets using RAG and SOP retrieval.
"""

import json
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
        max_retries: int = 2
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
        try:
            # Try to find JSON in response
            # Look for {...} pattern
            start = response_text.find('{')
            end = response_text.rfind('}')
            
            if start == -1 or end == -1:
                return None, "No JSON object found in response"
            
            json_str = response_text[start:end+1]
            parsed = json.loads(json_str)
            
            return parsed, None
            
        except json.JSONDecodeError as e:
            return None, f"Invalid JSON: {str(e)}"
        except Exception as e:
            return None, f"Parse error: {str(e)}"
    
    def triage(
        self,
        subject: str,
        description: str,
        max_iterations: int = 10,
        verbose: bool = False
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
                if attempt == self.max_retries:
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
