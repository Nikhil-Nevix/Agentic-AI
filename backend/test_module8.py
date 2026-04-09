"""
Test Module 8: FastAPI Endpoints
Tests the REST API for ticket triaging.
"""

import sys
from pathlib import Path
import httpx
import asyncio
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent))

# Test configuration
BASE_URL = "http://localhost:8000"
API_V1 = f"{BASE_URL}/api/v1"

logger.info("=" * 70)
logger.info("MODULE 8 VERIFICATION - FastAPI REST API")
logger.info("=" * 70)
logger.info(f"⚠️  Make sure the server is running: python main.py")
logger.info(f"⚠️  Testing against: {BASE_URL}")
logger.info("=" * 70)


async def test_api():
    """Run all API tests."""
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        
        # Test 1: Root Endpoint
        logger.info("\nTest 1: Root Endpoint (GET /)")
        logger.info("-" * 70)
        
        try:
            response = await client.get(BASE_URL + "/")
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            
            logger.info(f"✅ Root endpoint accessible")
            logger.info(f"   Name: {data.get('name')}")
            logger.info(f"   Version: {data.get('version')}")
            logger.info(f"   Status: {data.get('status')}")
        except Exception as e:
            logger.error(f"❌ Test 1 failed: {e}")
            return False
        
        # Test 2: Health Check
        logger.info("\nTest 2: Health Check (GET /api/v1/health)")
        logger.info("-" * 70)
        
        try:
            response = await client.get(f"{API_V1}/health")
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            
            logger.info(f"✅ Health endpoint working")
            logger.info(f"   Status: {data.get('status')}")
            logger.info(f"   Version: {data.get('version')}")
            logger.info(f"   Components: {data.get('components')}")
            
            assert data.get('status') in ['healthy', 'degraded'], "Status should be healthy or degraded"
            logger.info("✅ Test 2: PASSED")
        except Exception as e:
            logger.error(f"❌ Test 2 failed: {e}")
            return False
        
        # Test 3: Get Queues
        logger.info("\nTest 3: Get Available Queues (GET /api/v1/queues)")
        logger.info("-" * 70)
        
        try:
            response = await client.get(f"{API_V1}/queues")
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            
            queues = data.get('queues', [])
            count = data.get('count', 0)
            
            logger.info(f"✅ Queues endpoint working")
            logger.info(f"   Total queues: {count}")
            logger.info(f"   Sample queues:")
            for queue in queues[:3]:
                logger.info(f"      - {queue}")
            
            assert count == 9, f"Expected 9 queues, got {count}"
            assert "AMER - STACK Service Desk Group" in queues, "Expected STACK queue"
            logger.info("✅ Test 3: PASSED")
        except Exception as e:
            logger.error(f"❌ Test 3 failed: {e}")
            return False
        
        # Test 4: Get Stats
        logger.info("\nTest 4: Get Agent Statistics (GET /api/v1/stats)")
        logger.info("-" * 70)
        
        try:
            response = await client.get(f"{API_V1}/stats")
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            
            logger.info(f"✅ Stats endpoint working")
            logger.info(f"   Total tickets: {data.get('total_tickets_in_db')}")
            logger.info(f"   Total SOPs: {data.get('total_sop_chunks')}")
            logger.info(f"   LLM Provider: {data.get('llm_provider')}")
            logger.info(f"   Embedding: {data.get('embedding_provider')}")
            logger.info(f"   Tools: {', '.join(data.get('available_tools', []))}")
            
            assert data.get('total_tickets_in_db', 0) > 0, "Should have tickets"
            assert data.get('total_sop_chunks', 0) > 0, "Should have SOPs"
            logger.info("✅ Test 4: PASSED")
        except Exception as e:
            logger.error(f"❌ Test 4 failed: {e}")
            return False
        
        # Test 5: Triage Ticket - Password Reset (High Confidence)
        logger.info("\nTest 5: Triage Password Reset Ticket (POST /api/v1/triage)")
        logger.info("-" * 70)
        
        try:
            payload = {
                "subject": "User cannot login - password expired",
                "description": "Employee jsmith@jadeglobal.com unable to access email. Password has expired.",
                "verbose": False,
                "max_iterations": 10
            }
            
            logger.info(f"Sending triage request...")
            response = await client.post(f"{API_V1}/triage", json=payload)
            
            if response.status_code != 200:
                logger.error(f"Status code: {response.status_code}")
                logger.error(f"Response: {response.text}")
                raise Exception(f"Expected 200, got {response.status_code}")
            
            data = response.json()
            
            logger.info("\n" + "=" * 70)
            logger.info("TRIAGE RESULT")
            logger.info("=" * 70)
            logger.info(f"Queue: {data.get('queue')}")
            logger.info(f"Category: {data.get('category')}")
            logger.info(f"Sub-Category: {data.get('sub_category')}")
            logger.info(f"Confidence: {data.get('confidence'):.2%}")
            logger.info(f"Routing Action: {data.get('routing_action')}")
            logger.info(f"SOP Reference: {data.get('sop_reference')}")
            logger.info(f"\nReasoning: {data.get('reasoning')}")
            logger.info(f"\nResolution Steps ({len(data.get('resolution_steps', []))}):")
            for i, step in enumerate(data.get('resolution_steps', []), 1):
                logger.info(f"  {i}. {step}")
            
            # Validations
            assert data.get('queue'), "Queue should be assigned"
            assert data.get('category'), "Category should be assigned"
            assert data.get('confidence', 0) > 0, "Confidence should be > 0"
            assert len(data.get('resolution_steps', [])) >= 3, "Should have at least 3 steps"
            assert data.get('routing_action') in ['auto_resolve', 'route_with_suggestion', 'escalate_to_human']
            
            logger.info("\n✅ Test 5: PASSED - Valid triage result")
            
            if data.get('confidence', 0) >= 0.85:
                logger.info("✅ High confidence detected (correct for password reset)")
            
        except Exception as e:
            logger.error(f"❌ Test 5 failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        # Test 6: Triage with Empty Description
        logger.info("\n\nTest 6: Triage with Minimal Input")
        logger.info("-" * 70)
        
        try:
            payload = {
                "subject": "VPN not working",
                "description": "",
                "verbose": False
            }
            
            response = await client.post(f"{API_V1}/triage", json=payload)
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            
            logger.info(f"✅ Handled ticket with empty description")
            logger.info(f"   Queue: {data.get('queue')}")
            logger.info(f"   Confidence: {data.get('confidence'):.2%}")
            logger.info("✅ Test 6: PASSED")
        except Exception as e:
            logger.error(f"❌ Test 6 failed: {e}")
            return False
        
        # Test 7: Invalid Request (Missing Subject)
        logger.info("\n\nTest 7: Invalid Request Handling")
        logger.info("-" * 70)
        
        try:
            payload = {
                "subject": "",  # Empty subject
                "description": "Some description"
            }
            
            response = await client.post(f"{API_V1}/triage", json=payload)
            
            # Should get 422 validation error
            assert response.status_code == 422, f"Expected 422, got {response.status_code}"
            
            logger.info("✅ Correctly rejected invalid request (empty subject)")
            logger.info("✅ Test 7: PASSED - Validation working")
        except AssertionError:
            logger.error(f"❌ Test 7 failed: Expected 422 validation error")
            return False
        except Exception as e:
            logger.error(f"❌ Test 7 failed: {e}")
            return False
        
        # Test 8: OpenAPI Documentation
        logger.info("\n\nTest 8: OpenAPI Documentation")
        logger.info("-" * 70)
        
        try:
            response = await client.get(f"{BASE_URL}/openapi.json")
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            openapi = response.json()
            
            logger.info(f"✅ OpenAPI schema accessible")
            logger.info(f"   Title: {openapi.get('info', {}).get('title')}")
            logger.info(f"   Version: {openapi.get('info', {}).get('version')}")
            logger.info(f"   Endpoints: {len(openapi.get('paths', {}))}")
            
            # Check key endpoints exist
            paths = openapi.get('paths', {})
            assert '/api/v1/triage' in paths, "Triage endpoint missing"
            assert '/api/v1/health' in paths, "Health endpoint missing"
            
            logger.info("✅ Test 8: PASSED - Documentation complete")
        except Exception as e:
            logger.error(f"❌ Test 8 failed: {e}")
            return False
        
        return True


# Main test runner
async def main():
    """Run all tests."""
    try:
        success = await test_api()
        
        # Summary
        logger.info("\n" + "=" * 70)
        logger.info("MODULE 8 VERIFICATION COMPLETE")
        logger.info("=" * 70)
        
        if success:
            logger.info("✅ All tests passed!")
            logger.info("✅ REST API fully functional")
            logger.info("✅ Triaging endpoint working")
            logger.info("✅ Validation and error handling")
            logger.info("✅ Documentation available at /docs")
            logger.info("\n🎉 Module 8 is operational!")
            logger.info("\nAccess the API:")
            logger.info(f"  - Swagger UI: {BASE_URL}/docs")
            logger.info(f"  - ReDoc: {BASE_URL}/redoc")
            logger.info(f"  - OpenAPI: {BASE_URL}/openapi.json")
        else:
            logger.error("❌ Some tests failed")
            logger.error("Check the logs above for details")
            sys.exit(1)
    
    except httpx.ConnectError:
        logger.error("❌ Cannot connect to server")
        logger.error(f"⚠️  Make sure the server is running:")
        logger.error("   cd /home/NikhilRokade/Agentic_AI/backend")
        logger.error("   source venv_clean/bin/activate")
        logger.error("   python main.py")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Test suite failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
