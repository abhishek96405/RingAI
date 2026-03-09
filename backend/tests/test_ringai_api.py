"""
RingAI Backend API Tests
Tests for P0/P1 bug fixes related to Gemini JSON parsing and call simulation

Modules tested:
- /api/status - Service status check
- /api/demo/simulate-call - Call simulation with Gemini analysis
- /api/calls/{call_id}/analyse - Re-analysis endpoint
- /api/restaurants/{restaurant_id}/calls - Call list retrieval
"""

import pytest
import requests
import os
import time
import json

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
RESTAURANT_ID = "demo-restaurant-001"


class TestServiceStatus:
    """Test API status and Gemini availability"""
    
    def test_api_status(self):
        """GET /api/status - verify API is operational and Gemini available"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200, f"Status endpoint failed: {response.text}"
        
        data = response.json()
        assert data["api"] == "operational", "API should be operational"
        assert "gemini" in data, "Gemini status should be in response"
        assert data["gemini"]["available"] == True, "Gemini should be available"
        print(f"✓ API Status: {data['api']}, Gemini available: {data['gemini']['available']}")


class TestCallSimulation:
    """Test call simulation endpoint with Gemini analysis (P0 bug fix)"""
    
    def test_simulate_call_returns_valid_json(self):
        """POST /api/demo/simulate-call - Call should complete with valid analysis JSON"""
        response = requests.post(
            f"{BASE_URL}/api/demo/simulate-call",
            params={"restaurant_id": RESTAURANT_ID}
        )
        assert response.status_code == 200, f"Simulate call failed: {response.text}"
        
        data = response.json()
        
        # Verify call record structure
        assert "id" in data, "Call should have an ID"
        assert "transcript" in data, "Call should have transcript"
        assert "analysis_json" in data, "Call should have analysis_json"
        assert data["analysis_json"] is not None, "analysis_json should not be None"
        
        # Verify analysis_json structure (P0 bug fix validation)
        analysis = data["analysis_json"]
        assert isinstance(analysis, dict), "analysis_json should be a dictionary"
        assert "quality_score" in analysis, "analysis should have quality_score"
        assert isinstance(analysis["quality_score"], int), "quality_score should be int"
        assert 1 <= analysis["quality_score"] <= 100, "quality_score should be 1-100"
        
        print(f"✓ Call simulated: ID={data['id']}, Quality={analysis['quality_score']}")
        return data["id"]
    
    def test_simulate_call_multiple_runs_consistency(self):
        """Run 5 simulate-call tests to verify JSON parsing is consistent"""
        success_count = 0
        failure_reasons = []
        call_ids = []
        
        for i in range(5):
            try:
                response = requests.post(
                    f"{BASE_URL}/api/demo/simulate-call",
                    params={"restaurant_id": RESTAURANT_ID}
                )
                
                if response.status_code != 200:
                    failure_reasons.append(f"Run {i+1}: HTTP {response.status_code}")
                    continue
                
                data = response.json()
                analysis = data.get("analysis_json")
                
                if analysis is None:
                    failure_reasons.append(f"Run {i+1}: analysis_json is None")
                    continue
                
                if not isinstance(analysis, dict):
                    failure_reasons.append(f"Run {i+1}: analysis_json is not a dict")
                    continue
                
                if "quality_score" not in analysis:
                    failure_reasons.append(f"Run {i+1}: missing quality_score")
                    continue
                
                success_count += 1
                call_ids.append(data["id"])
                print(f"  Run {i+1}: ✓ Quality={analysis.get('quality_score')}")
                
                # Small delay between runs
                time.sleep(0.5)
                
            except Exception as e:
                failure_reasons.append(f"Run {i+1}: Exception - {str(e)}")
        
        print(f"✓ Consistency test: {success_count}/5 successful")
        assert success_count >= 4, f"Expected at least 4/5 successes, got {success_count}. Failures: {failure_reasons}"
        return call_ids


class TestCallReanalysis:
    """Test re-analysis endpoint (P0 bug fix)"""
    
    def test_reanalyse_call_returns_valid_json(self):
        """POST /api/calls/{call_id}/analyse - Re-analysis should return valid JSON"""
        # First create a call to reanalyse
        create_response = requests.post(
            f"{BASE_URL}/api/demo/simulate-call",
            params={"restaurant_id": RESTAURANT_ID}
        )
        assert create_response.status_code == 200, "Failed to create call for reanalysis"
        call_id = create_response.json()["id"]
        
        # Now reanalyse
        response = requests.post(f"{BASE_URL}/api/calls/{call_id}/analyse")
        assert response.status_code == 200, f"Reanalyse failed: {response.text}"
        
        data = response.json()
        assert "analysis" in data, "Response should contain analysis"
        
        analysis = data["analysis"]
        assert isinstance(analysis, dict), "analysis should be a dict"
        assert "quality_score" in analysis, "analysis should have quality_score"
        assert isinstance(analysis["quality_score"], int), "quality_score should be int"
        
        # Check for required fields
        expected_fields = ["quality_score", "order_accuracy", "issues", "highlights", "summary"]
        for field in expected_fields:
            assert field in analysis, f"Missing field: {field}"
        
        print(f"✓ Reanalysis complete: call_id={call_id}, quality_score={analysis['quality_score']}")
    
    def test_reanalyse_nonexistent_call(self):
        """POST /api/calls/{call_id}/analyse - Should return 404 for non-existent call"""
        response = requests.post(f"{BASE_URL}/api/calls/nonexistent-id/analyse")
        assert response.status_code == 404, "Should return 404 for non-existent call"


class TestCallList:
    """Test call list retrieval with valid analysis"""
    
    def test_get_calls_with_valid_analysis(self):
        """GET /api/restaurants/{restaurant_id}/calls - Calls should have valid analysis_json"""
        response = requests.get(
            f"{BASE_URL}/api/restaurants/{RESTAURANT_ID}/calls",
            params={"limit": 10}
        )
        assert response.status_code == 200, f"Failed to get calls: {response.text}"
        
        data = response.json()
        assert "calls" in data, "Response should have 'calls' key"
        
        calls = data["calls"]
        assert len(calls) > 0, "Should have at least one call"
        
        # Check that calls have valid analysis_json
        calls_with_valid_analysis = 0
        for call in calls:
            analysis = call.get("analysis_json")
            if analysis and isinstance(analysis, dict):
                if "quality_score" in analysis:
                    calls_with_valid_analysis += 1
        
        print(f"✓ Retrieved {len(calls)} calls, {calls_with_valid_analysis} with valid analysis")
        assert calls_with_valid_analysis > 0, "At least one call should have valid analysis_json"


class TestLongConversationHandling:
    """Test P1 bug fix: Long conversation handling without Budget Exceeded errors"""
    
    def test_conversation_context_summarization(self):
        """
        Test that simulated calls can handle conversations
        This indirectly tests _summarize_conversation_context
        """
        # Run multiple simulate calls which generate 10+ exchanges internally
        success_count = 0
        budget_errors = 0
        
        for i in range(3):
            try:
                response = requests.post(
                    f"{BASE_URL}/api/demo/simulate-call",
                    params={"restaurant_id": RESTAURANT_ID}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    transcript = data.get("transcript", [])
                    
                    # Check if analysis completed without budget error
                    analysis = data.get("analysis_json")
                    if analysis and "quality_score" in analysis:
                        success_count += 1
                        print(f"  Run {i+1}: ✓ {len(transcript)} transcript entries, quality={analysis['quality_score']}")
                    else:
                        print(f"  Run {i+1}: ? Analysis incomplete")
                else:
                    error_text = response.text.lower()
                    if "budget" in error_text or "quota" in error_text:
                        budget_errors += 1
                        print(f"  Run {i+1}: ✗ Budget error")
                    else:
                        print(f"  Run {i+1}: ✗ HTTP {response.status_code}")
                
                time.sleep(0.5)
                
            except Exception as e:
                print(f"  Run {i+1}: ✗ Exception: {e}")
        
        assert budget_errors == 0, f"Got {budget_errors} budget exceeded errors"
        assert success_count >= 2, f"Expected at least 2/3 successes, got {success_count}"
        print(f"✓ Long conversation test: {success_count}/3 passed, {budget_errors} budget errors")


class TestRestaurantEndpoints:
    """Basic restaurant endpoint tests"""
    
    def test_get_restaurant(self):
        """GET /api/restaurants/{restaurant_id} - Get demo restaurant"""
        response = requests.get(f"{BASE_URL}/api/restaurants/{RESTAURANT_ID}")
        assert response.status_code == 200, f"Failed to get restaurant: {response.text}"
        
        data = response.json()
        assert data["id"] == RESTAURANT_ID
        assert "name" in data
        print(f"✓ Restaurant: {data['name']}")
    
    def test_get_restaurant_menu(self):
        """GET /api/restaurants/{restaurant_id}/menu - Get menu items"""
        response = requests.get(f"{BASE_URL}/api/restaurants/{RESTAURANT_ID}/menu")
        assert response.status_code == 200, f"Failed to get menu: {response.text}"
        
        items = response.json()
        assert isinstance(items, list)
        assert len(items) > 0, "Should have menu items"
        print(f"✓ Menu has {len(items)} items")
    
    def test_get_analytics_summary(self):
        """GET /api/restaurants/{restaurant_id}/analytics/summary - Get analytics"""
        response = requests.get(f"{BASE_URL}/api/restaurants/{RESTAURANT_ID}/analytics/summary")
        assert response.status_code == 200, f"Failed to get analytics: {response.text}"
        
        data = response.json()
        assert "total_calls" in data
        assert "avg_quality_score" in data
        print(f"✓ Analytics: {data['total_calls']} calls, avg quality={data['avg_quality_score']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
