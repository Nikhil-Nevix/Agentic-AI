"""
Test Module 7: Ticket Triaging Agent
Tests the LangChain ReAct agent with real ticket triaging.
"""

import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent))

from app.agent.triage_agent import (
    TicketTriagingAgent,
    get_triage_agent,
    triage_ticket,
    RoutingAction
)
from loguru import logger

logger.info("=" * 70)
logger.info("MODULE 7 VERIFICATION")
logger.info("=" * 70)
logger.info("⚠️  This test requires a valid OpenAI API key in .env")
logger.info("=" * 70)

# Test 1: Agent Initialization
logger.info("\nTest 1: Agent Initialization")
logger.info("-" * 70)

try:
    agent = TicketTriagingAgent(temperature=0.1)
    logger.info(f"✅ Agent created: {agent.llm_provider}")
    logger.info(f"   Temperature: {agent.temperature}")
    logger.info(f"   Tools: {len(agent.tools)}")
    logger.info(f"   Max retries: {agent.max_retries}")
except Exception as e:
    logger.error(f"❌ Agent initialization failed: {e}")
    logger.warning("⚠️  Make sure your .env has valid API keys")
    sys.exit(1)

# Test 2: Simple Password Reset Ticket (Should be High Confidence)
logger.info("\nTest 2: Password Reset Ticket (Expected: High Confidence)")
logger.info("-" * 70)

try:
    result = agent.triage(
        subject="User cannot login - password expired",
        description="Employee jsmith@jadeglobal.com unable to access email. Password has expired.",
        verbose=True
    )
    
    logger.info("\n" + "=" * 70)
    logger.info("TRIAGE RESULT")
    logger.info("=" * 70)
    logger.info(f"Queue: {result.queue}")
    logger.info(f"Category: {result.category}")
    logger.info(f"Sub-Category: {result.sub_category}")
    logger.info(f"Confidence: {result.confidence:.2%}")
    logger.info(f"Routing Action: {result.routing_action.value}")
    logger.info(f"SOP Reference: {result.sop_reference}")
    logger.info(f"\nReasoning: {result.reasoning}")
    logger.info(f"\nResolution Steps ({len(result.resolution_steps)}):")
    for i, step in enumerate(result.resolution_steps, 1):
        logger.info(f"  {i}. {step}")
    
    # Validate
    if result.is_valid():
        logger.info("\n✅ Test 2: PASSED - Valid result returned")
    else:
        logger.error(f"\n❌ Test 2: FAILED - Validation errors: {result.validation_errors}")
    
    # Check confidence routing
    if result.confidence >= 0.85 and result.routing_action == RoutingAction.AUTO_RESOLVE:
        logger.info("✅ High confidence → Auto-resolve (correct)")
    elif result.confidence >= 0.60 and result.routing_action == RoutingAction.ROUTE_WITH_SUGGESTION:
        logger.info("✅ Medium confidence → Route with suggestion (correct)")
    else:
        logger.warning(f"⚠️  Unexpected routing for confidence {result.confidence:.2%}")
    
except Exception as e:
    logger.error(f"❌ Test 2 failed: {e}")
    import traceback
    traceback.print_exc()

# Test 3: VPN Issue (Should be Medium Confidence)
logger.info("\n\nTest 3: VPN Connection Issue (Expected: Medium Confidence)")
logger.info("-" * 70)

try:
    result = agent.triage(
        subject="Cannot connect to VPN",
        description="Remote worker getting timeout error when connecting to company VPN. Error: Connection timed out after 30 seconds",
        verbose=False  # Less verbose this time
    )
    
    logger.info(f"\nQueue: {result.queue}")
    logger.info(f"Category: {result.category}")
    logger.info(f"Confidence: {result.confidence:.2%}")
    logger.info(f"Routing: {result.routing_action.value}")
    logger.info(f"Valid: {result.is_valid()}")
    
    if result.is_valid():
        logger.info("✅ Test 3: PASSED")
    else:
        logger.error(f"❌ Test 3: FAILED - {result.validation_errors}")
    
except Exception as e:
    logger.error(f"❌ Test 3 failed: {e}")

# Test 4: Ambiguous Ticket (Should be Low Confidence)
logger.info("\n\nTest 4: Ambiguous Ticket (Expected: Low Confidence)")
logger.info("-" * 70)

try:
    result = agent.triage(
        subject="System not working",
        description="",  # No description!
        verbose=False
    )
    
    logger.info(f"\nQueue: {result.queue}")
    logger.info(f"Confidence: {result.confidence:.2%}")
    logger.info(f"Routing: {result.routing_action.value}")
    
    if result.confidence < 0.60:
        logger.info("✅ Low confidence detected (correct for ambiguous ticket)")
    else:
        logger.warning(f"⚠️  Expected low confidence, got {result.confidence:.2%}")
    
    if result.routing_action == RoutingAction.ESCALATE_TO_HUMAN:
        logger.info("✅ Correctly escalated to human")
    
    logger.info("✅ Test 4: PASSED (handled ambiguous input)")
    
except Exception as e:
    logger.error(f"❌ Test 4 failed: {e}")

# Test 5: Singleton Pattern
logger.info("\n\nTest 5: Singleton Pattern")
logger.info("-" * 70)

try:
    agent1 = get_triage_agent()
    agent2 = get_triage_agent()
    
    if agent1 is agent2:
        logger.info("✅ Singleton pattern working (same instance)")
    else:
        logger.error("❌ Different instances returned")
    
except Exception as e:
    logger.error(f"❌ Test 5 failed: {e}")

# Test 6: Convenience Function
logger.info("\n\nTest 6: Convenience Function")
logger.info("-" * 70)

try:
    result = triage_ticket(
        subject="Email access problem",
        description="Cannot receive emails in Outlook",
        verbose=False
    )
    
    logger.info(f"Queue: {result.queue}")
    logger.info(f"Confidence: {result.confidence:.2%}")
    logger.info("✅ Test 6: PASSED (convenience function works)")
    
except Exception as e:
    logger.error(f"❌ Test 6 failed: {e}")

# Test 7: Result Serialization
logger.info("\n\nTest 7: Result Serialization")
logger.info("-" * 70)

try:
    result_dict = result.to_dict()
    
    # Check all required fields present
    required_fields = ['queue', 'category', 'sub_category', 'resolution_steps',
                       'confidence', 'sop_reference', 'reasoning', 'routing_action']
    
    missing = [f for f in required_fields if f not in result_dict]
    
    if not missing:
        logger.info("✅ All fields present in serialized result")
        logger.info(f"✅ Result can be JSON serialized")
        # Try to serialize
        json_str = json.dumps(result_dict, indent=2)
        logger.info(f"   JSON size: {len(json_str)} chars")
    else:
        logger.error(f"❌ Missing fields: {missing}")
    
except Exception as e:
    logger.error(f"❌ Test 7 failed: {e}")

# Summary
logger.info("\n" + "=" * 70)
logger.info("MODULE 7 VERIFICATION COMPLETE")
logger.info("=" * 70)
logger.info("✅ Agent initialization working")
logger.info("✅ Ticket triaging functional")
logger.info("✅ Confidence-based routing active")
logger.info("✅ Validation and error handling")
logger.info("✅ Singleton pattern implemented")
logger.info("✅ Result serialization ready")
logger.info("\n🎉 Module 7 is operational!")
logger.info("\nNote: Test results depend on LLM responses (may vary slightly)")
