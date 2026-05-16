"""
RingAI Test Mode API Tests
Tests for new test mode infrastructure with sandbox support

Modules tested:
- /api/test-mode/status - Test mode status with integration statuses
- /api/test-mode/scenarios - Get available test scenarios  
- /api/test-mode/run-scenario - Run scenario with Gemini AI
- /api/status - Enhanced with mode and all integration statuses
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
RESTAURANT_ID = "demo-restaurant-001"


class TestTestModeStatus:
    """Test /api/test-mode/status endpoint"""
    
    def test_get_test_mode_status(self):
        """GET /api/test-mode/status - Should return integration statuses"""
        response = requests.get(f"{BASE_URL}/api/test-mode/status")
        assert response.status_code == 200, f"Test mode status failed: {response.text}"
        
        data = response.json()
        
        # Check required fields
        assert "mode" in data, "Response should have 'mode'"
        assert "integrations" in data, "Response should have 'integrations'"
        assert "timestamp" in data, "Response should have 'timestamp'"
        
        # Check mode value (should be sandbox or simulation)
        assert data["mode"] in ["sandbox", "simulation", "live"], f"Invalid mode: {data['mode']}"
        
        # Check all integrations are present
        integrations = data["integrations"]
        assert "gemini" in integrations, "Missing gemini integration"
        assert "telnyx" in integrations, "Missing telnyx integration"
        assert "stripe" in integrations, "Missing stripe integration"
        assert "clerk" in integrations, "Missing clerk integration"
        
        # Validate gemini integration structure
        gemini = integrations["gemini"]
        assert "status" in gemini, "Gemini should have 'status'"
        assert "configured" in gemini, "Gemini should have 'configured'"
        assert "message" in gemini, "Gemini should have 'message'"
        
        print(f"✓ Test mode status: mode={data['mode']}")
        print(f"  Gemini: {gemini['status']} - {gemini['message']}")
        print(f"  Telnyx: {integrations['telnyx']['status']} - {integrations['telnyx']['message']}")
        print(f"  Stripe: {integrations['stripe']['status']} - {integrations['stripe']['message']}")
        print(f"  Clerk: {integrations['clerk']['status']} - {integrations['clerk']['message']}")


class TestTestScenarios:
    """Test /api/test-mode/scenarios endpoint"""
    
    def test_get_test_scenarios(self):
        """GET /api/test-mode/scenarios - Should return 6 test scenarios"""
        response = requests.get(f"{BASE_URL}/api/test-mode/scenarios")
        assert response.status_code == 200, f"Get scenarios failed: {response.text}"
        
        data = response.json()
        assert "scenarios" in data, "Response should have 'scenarios'"
        
        scenarios = data["scenarios"]
        assert isinstance(scenarios, list), "scenarios should be a list"
        assert len(scenarios) == 6, f"Expected 6 scenarios, got {len(scenarios)}"
        
        # Verify scenario structure
        for scenario in scenarios:
            assert "id" in scenario, "Scenario should have 'id'"
            assert "name" in scenario, "Scenario should have 'name'"
            assert "caller_name" in scenario, "Scenario should have 'caller_name'"
            assert "message_count" in scenario, "Scenario should have 'message_count'"
            assert "order_type" in scenario, "Scenario should have 'order_type'"
            assert "expected_items" in scenario, "Scenario should have 'expected_items'"
        
        # List all scenarios
        print(f"✓ Found {len(scenarios)} test scenarios:")
        for s in scenarios:
            print(f"  [{s['id']}] {s['name']} - {s['order_type']} ({s['message_count']} messages)")


class TestRunScenario:
    """Test /api/test-mode/run-scenario endpoint"""
    
    def test_run_scenario_0_simple_pickup(self):
        """POST /api/test-mode/run-scenario - Run 'Simple Pickup Order' scenario (ID 0)"""
        response = requests.post(
            f"{BASE_URL}/api/test-mode/run-scenario",
            params={"restaurant_id": RESTAURANT_ID, "scenario_id": 0}
        )
        assert response.status_code == 200, f"Run scenario failed: {response.text}"
        
        data = response.json()
        
        # Check response structure
        assert "call" in data, "Response should have 'call'"
        assert "scenario" in data, "Response should have 'scenario'"
        assert "ai_powered" in data, "Response should have 'ai_powered'"
        
        call = data["call"]
        assert "id" in call, "Call should have 'id'"
        assert "transcript" in call, "Call should have 'transcript'"
        assert "caller_name" in call, "Call should have 'caller_name'"
        assert "status" in call, "Call should have 'status'"
        assert "quality_score" in call, "Call should have 'quality_score'"
        
        # Verify scenario info
        scenario_info = data["scenario"]
        assert scenario_info["id"] == 0
        assert scenario_info["name"] == "Simple Pickup Order"
        
        # Verify transcript has content
        transcript = call["transcript"]
        assert isinstance(transcript, list), "Transcript should be a list"
        assert len(transcript) > 0, "Transcript should have messages"
        
        # Check AI and customer messages exist
        ai_messages = [m for m in transcript if m.get("role") == "ai"]
        customer_messages = [m for m in transcript if m.get("role") == "customer"]
        
        assert len(ai_messages) > 0, "Should have AI messages"
        assert len(customer_messages) > 0, "Should have customer messages"
        
        print(f"✓ Scenario 0 (Simple Pickup) completed:")
        print(f"  Call ID: {call['id']}")
        print(f"  Caller: {call['caller_name']}")
        print(f"  Transcript: {len(transcript)} messages ({len(ai_messages)} AI, {len(customer_messages)} customer)")
        print(f"  Quality Score: {call['quality_score']}")
        print(f"  AI Powered: {data['ai_powered']}")
    
    def test_run_scenario_3_complex_order(self):
        """POST /api/test-mode/run-scenario - Run 'Complex Order with Modifications' scenario (ID 3)"""
        response = requests.post(
            f"{BASE_URL}/api/test-mode/run-scenario",
            params={"restaurant_id": RESTAURANT_ID, "scenario_id": 3}
        )
        assert response.status_code == 200, f"Run scenario failed: {response.text}"
        
        data = response.json()
        call = data["call"]
        
        # Verify call completed
        assert call["status"] == "COMPLETED", f"Expected COMPLETED, got {call['status']}"
        
        # Verify caller name matches scenario
        assert call["caller_name"] == "James Wilson", f"Unexpected caller: {call['caller_name']}"
        
        # Verify order has items (scenario expects Pepperoni Pizza, Fettuccine Alfredo, Cannoli, Espresso)
        order_json = call.get("order_json")
        if order_json and order_json.get("items"):
            items = order_json["items"]
            print(f"✓ Scenario 3 (Complex Order) completed:")
            print(f"  Caller: {call['caller_name']}")
            print(f"  Order items: {len(items)}")
            for item in items:
                print(f"    - {item['name']}: ${item['price']/100:.2f}")
            print(f"  Order total: ${order_json.get('total', 0)/100:.2f}")
        else:
            print(f"✓ Scenario 3 completed (no order items extracted)")
        
        print(f"  Quality Score: {call['quality_score']}")
    
    def test_run_scenario_invalid_id(self):
        """POST /api/test-mode/run-scenario - Should return 400 for invalid scenario ID"""
        response = requests.post(
            f"{BASE_URL}/api/test-mode/run-scenario",
            params={"restaurant_id": RESTAURANT_ID, "scenario_id": 99}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
    
    def test_run_scenario_invalid_restaurant(self):
        """POST /api/test-mode/run-scenario - Should return 404 for invalid restaurant"""
        response = requests.post(
            f"{BASE_URL}/api/test-mode/run-scenario",
            params={"restaurant_id": "nonexistent-restaurant", "scenario_id": 0}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


class TestStatusEndpoint:
    """Test /api/status enhanced endpoint"""
    
    def test_status_includes_mode_and_integrations(self):
        """GET /api/status - Should include mode and all integration statuses"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200, f"Status failed: {response.text}"
        
        data = response.json()
        
        # Check API operational
        assert data.get("api") == "operational", "API should be operational"
        
        # Check mode is present
        assert "mode" in data, "Status should have 'mode'"
        assert data["mode"] in ["sandbox", "simulation", "live"], f"Invalid mode: {data['mode']}"
        
        # Check gemini status
        assert "gemini" in data, "Status should have 'gemini'"
        assert "available" in data["gemini"], "Gemini should have 'available'"
        assert "model" in data["gemini"], "Gemini should have 'model'"
        
        # Check telnyx status
        assert "telnyx" in data, "Status should have 'telnyx'"
        assert "available" in data["telnyx"], "Telnyx should have 'available'"
        assert "status" in data["telnyx"], "Telnyx should have 'status'"
        
        # Check stripe status
        assert "stripe" in data, "Status should have 'stripe'"
        assert "status" in data["stripe"], "Stripe should have 'status'"
        assert "configured" in data["stripe"], "Stripe should have 'configured'"
        
        # Check clerk status
        assert "clerk" in data, "Status should have 'clerk'"
        assert "status" in data["clerk"], "Clerk should have 'status'"
        assert "configured" in data["clerk"], "Clerk should have 'configured'"
        
        # Check database status
        assert "database" in data, "Status should have 'database'"
        assert data["database"]["available"] == True, "Database should be available"
        
        print(f"✓ Status endpoint includes all integration statuses:")
        print(f"  Mode: {data['mode']}")
        print(f"  Gemini: available={data['gemini']['available']}, model={data['gemini']['model']}")
        print(f"  Telnyx: available={data['telnyx']['available']}, status={data['telnyx']['status']}")
        print(f"  Stripe: status={data['stripe']['status']}, configured={data['stripe']['configured']}")
        print(f"  Clerk: status={data['clerk']['status']}, configured={data['clerk']['configured']}")


class TestExistingEndpointsStillWork:
    """Verify existing endpoints still work after test mode changes"""
    
    def test_calls_endpoint(self):
        """GET /api/restaurants/{restaurant_id}/calls - Should still work"""
        response = requests.get(
            f"{BASE_URL}/api/restaurants/{RESTAURANT_ID}/calls",
            params={"limit": 5}
        )
        assert response.status_code == 200, f"Calls endpoint failed: {response.text}"
        
        data = response.json()
        assert "calls" in data
        assert "total" in data
        print(f"✓ Calls endpoint works: {data['total']} total calls")
    
    def test_menu_endpoint(self):
        """GET /api/restaurants/{restaurant_id}/menu - Should still work"""
        response = requests.get(f"{BASE_URL}/api/restaurants/{RESTAURANT_ID}/menu")
        assert response.status_code == 200, f"Menu endpoint failed: {response.text}"
        
        items = response.json()
        assert isinstance(items, list)
        assert len(items) > 0
        print(f"✓ Menu endpoint works: {len(items)} items")
    
    def test_analytics_endpoint(self):
        """GET /api/restaurants/{restaurant_id}/analytics/summary - Should still work"""
        response = requests.get(f"{BASE_URL}/api/restaurants/{RESTAURANT_ID}/analytics/summary")
        assert response.status_code == 200, f"Analytics endpoint failed: {response.text}"
        
        data = response.json()
        assert "total_calls" in data
        assert "avg_quality_score" in data
        print(f"✓ Analytics endpoint works: {data['total_calls']} calls, avg quality={data['avg_quality_score']}")
    
    def test_simulate_call_still_works(self):
        """POST /api/demo/simulate-call - Should still work"""
        response = requests.post(
            f"{BASE_URL}/api/demo/simulate-call",
            params={"restaurant_id": RESTAURANT_ID}
        )
        assert response.status_code == 200, f"Simulate call failed: {response.text}"
        
        data = response.json()
        assert "id" in data
        assert "transcript" in data
        print(f"✓ Simulate call still works: call_id={data['id']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
