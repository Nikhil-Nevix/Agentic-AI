"""
Complete Module 8 Test - All endpoints without LLM dependency
"""
import httpx
import asyncio
from loguru import logger
import sys

BASE_URL = "http://localhost:8000"
API_V1 = f"{BASE_URL}/api/v1"

async def test_all_endpoints():
    """Test all Module 8 endpoints."""
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        
        logger.info("=" * 70)
        logger.info("MODULE 8 COMPLETE TEST")
        logger.info("=" * 70)
        
        tests_passed = 0
        tests_failed = 0
        
        # Test 1: Root Endpoint
        logger.info("\n[1/6] Testing Root Endpoint (GET /)")
        try:
            response = await client.get(BASE_URL + "/")
            assert response.status_code == 200
            data = response.json()
            assert data.get('name') == "Service Desk Triaging Agent"
            assert data.get('version') == "1.0.0"
            assert data.get('status') == "online"
            logger.success("✅ PASSED - Root endpoint working")
            tests_passed += 1
        except Exception as e:
            logger.error(f"❌ FAILED - {e}")
            tests_failed += 1
        
        # Test 2: Health Check
        logger.info("\n[2/6] Testing Health Check (GET /api/v1/health)")
        try:
            response = await client.get(f"{API_V1}/health")
            assert response.status_code == 200
            data = response.json()
            assert data.get('status') in ['healthy', 'degraded']
            assert data.get('version') == "1.0.0"
            assert 'components' in data
            logger.success(f"✅ PASSED - Health: {data.get('status')}")
            logger.info(f"   Components: {data.get('components')}")
            tests_passed += 1
        except Exception as e:
            logger.error(f"❌ FAILED - {e}")
            tests_failed += 1
        
        # Test 3: Get Queues
        logger.info("\n[3/6] Testing Get Queues (GET /api/v1/queues)")
        try:
            response = await client.get(f"{API_V1}/queues")
            assert response.status_code == 200
            data = response.json()
            assert 'queues' in data
            assert 'count' in data
            assert data['count'] == 9
            assert "AMER - STACK Service Desk Group" in data['queues']
            logger.success(f"✅ PASSED - {data['count']} queues available")
            tests_passed += 1
        except Exception as e:
            logger.error(f"❌ FAILED - {e}")
            tests_failed += 1
        
        # Test 4: Get Stats
        logger.info("\n[4/6] Testing Get Stats (GET /api/v1/stats)")
        try:
            response = await client.get(f"{API_V1}/stats")
            assert response.status_code == 200
            data = response.json()
            assert data.get('total_tickets_in_db', 0) > 0
            assert data.get('total_sop_chunks', 0) > 0
            logger.success(f"✅ PASSED")
            logger.info(f"   Tickets: {data.get('total_tickets_in_db')}")
            logger.info(f"   SOPs: {data.get('total_sop_chunks')}")
            logger.info(f"   LLM: {data.get('llm_provider')}")
            tests_passed += 1
        except Exception as e:
            logger.error(f"❌ FAILED - {e}")
            tests_failed += 1
        
        # Test 5: OpenAPI Schema
        logger.info("\n[5/6] Testing OpenAPI Schema (GET /openapi.json)")
        try:
            response = await client.get(f"{BASE_URL}/openapi.json")
            assert response.status_code == 200
            openapi = response.json()
            assert openapi.get('openapi') == "3.1.0"
            assert '/api/v1/triage' in openapi.get('paths', {})
            assert '/api/v1/health' in openapi.get('paths', {})
            logger.success(f"✅ PASSED - {len(openapi.get('paths', {}))} endpoints documented")
            tests_passed += 1
        except Exception as e:
            logger.error(f"❌ FAILED - {e}")
            tests_failed += 1
        
        # Test 6: Validation Error Handling
        logger.info("\n[6/6] Testing Validation (POST /api/v1/triage with empty subject)")
        try:
            response = await client.post(f"{API_V1}/triage", json={
                "subject": "",
                "description": "test"
            })
            assert response.status_code == 422  # Validation error
            logger.success("✅ PASSED - Validation correctly rejects empty subject")
            tests_passed += 1
        except Exception as e:
            logger.error(f"❌ FAILED - {e}")
            tests_failed += 1
        
        # Summary
        logger.info("\n" + "=" * 70)
        logger.info("TEST SUMMARY")
        logger.info("=" * 70)
        logger.info(f"✅ Passed: {tests_passed}/6")
        logger.info(f"❌ Failed: {tests_failed}/6")
        
        if tests_failed == 0:
            logger.success("\n🎉 ALL TESTS PASSED - MODULE 8 WORKING PERFECTLY!")
            return True
        else:
            logger.error(f"\n⚠️  {tests_failed} test(s) failed")
            return False

async def main():
    try:
        success = await test_all_endpoints()
        sys.exit(0 if success else 1)
    except httpx.ConnectError:
        logger.error("❌ Cannot connect to server")
        logger.error("Please start the server: python main.py")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
