"""
Test Mode Infrastructure for RingAI

Provides sandbox testing capabilities that work without real API keys.
When sandbox keys are provided, uses actual sandbox environments.
Otherwise, uses intelligent simulation that mirrors real behavior.

Supported Sandbox Modes:
- Telnyx: Uses TELNYX_API_KEY when configured
- Stripe Test Mode: Uses Stripe test keys (sk_test_*)
- Gemini: Uses the official Google Gemini API when configured
"""
import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)

# Application code (sandbox/integration status helpers), NOT a pytest module —
# but the filename matches python_files=test_*.py and TestModeStatus matches
# python_classes=Test*, so pytest tries to collect it, can't (it's an Enum), and
# filterwarnings=error turns the collection warning into a hard abort. Mark the
# module non-test so pytest skips it entirely. (PL-38)
__test__ = False


class TestModeStatus(str, Enum):
    SANDBOX = "sandbox"      # Real sandbox credentials configured
    SIMULATION = "simulation" # No credentials, using simulation
    LIVE = "live"            # Production credentials


class IntegrationStatus:
    """Track status of each integration."""
    
    def __init__(self):
        self.refresh()
    
    def refresh(self):
        """Refresh integration status from environment."""
        self.integrations = {
            "gemini": self._check_gemini(),
            "telnyx": self._check_telnyx(),
            "stripe": self._check_stripe(),
            "clerk": self._check_clerk(),
        }
    
    def _check_gemini(self) -> Dict[str, Any]:
        """Check Gemini/AI integration status."""
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_GENAI_API_KEY")
        if api_key:
            return {
                "status": TestModeStatus.SANDBOX,
                "configured": True,
                "message": "Gemini via official Google API",
                "model": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
            }
        return {
            "status": TestModeStatus.SIMULATION,
            "configured": False,
            "message": "Using mock AI responses",
        }
    
    def _check_telnyx(self) -> Dict[str, Any]:
        """Check Telnyx integration status."""
        api_key = os.environ.get("TELNYX_API_KEY", "")
        phone_number = os.environ.get("TELNYX_PHONE_NUMBER", "")

        if api_key and phone_number:
            return {
                "status": TestModeStatus.LIVE,
                "configured": True,
                "message": "Telnyx live mode",
                "phone_number": phone_number,
            }
        return {
            "status": TestModeStatus.SIMULATION,
            "configured": False,
            "message": "Telnyx not configured - using call simulation",
        }
    
    def _check_stripe(self) -> Dict[str, Any]:
        """Check Stripe integration status."""
        secret_key = os.environ.get("STRIPE_SECRET_KEY", "")
        
        if secret_key.startswith("sk_test_"):
            return {
                "status": TestModeStatus.SANDBOX,
                "configured": True,
                "message": "Stripe test mode ready",
                "test_cards": {
                    "success": "4242424242424242",
                    "decline": "4000000000000002",
                    "insufficient": "4000000000009995",
                },
            }
        elif secret_key.startswith("sk_live_"):
            return {
                "status": TestModeStatus.LIVE,
                "configured": True,
                "message": "Stripe live mode (caution!)",
            }
        return {
            "status": TestModeStatus.SIMULATION,
            "configured": False,
            "message": "Stripe not configured - billing simulated",
            "test_cards": None,
        }
    
    def _check_clerk(self) -> Dict[str, Any]:
        """Check Clerk auth integration status."""
        publishable = os.environ.get("CLERK_PUBLISHABLE_KEY", "")
        secret = os.environ.get("CLERK_SECRET_KEY", "")
        
        if publishable.startswith("pk_test_") and secret.startswith("sk_test_"):
            return {
                "status": TestModeStatus.SANDBOX,
                "configured": True,
                "message": "Clerk test mode ready",
            }
        elif publishable.startswith("pk_live_") and secret.startswith("sk_live_"):
            return {
                "status": TestModeStatus.LIVE,
                "configured": True,
                "message": "Clerk live mode",
            }
        return {
            "status": TestModeStatus.SIMULATION,
            "configured": False,
            "message": "Auth not configured - using demo mode",
        }
    
    def get_overall_mode(self) -> TestModeStatus:
        """Get overall test mode status."""
        statuses = [i["status"] for i in self.integrations.values()]
        if TestModeStatus.LIVE in statuses:
            return TestModeStatus.LIVE
        if TestModeStatus.SANDBOX in statuses:
            return TestModeStatus.SANDBOX
        return TestModeStatus.SIMULATION
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "mode": self.get_overall_mode(),
            "integrations": self.integrations,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# Global instance
integration_status = IntegrationStatus()


def get_test_mode_status() -> Dict[str, Any]:
    """Get current test mode status for all integrations."""
    integration_status.refresh()
    return integration_status.to_dict()


def is_sandbox_mode() -> bool:
    """Check if we're running in sandbox mode."""
    return integration_status.get_overall_mode() in [TestModeStatus.SANDBOX, TestModeStatus.SIMULATION]


# =============================================================================
# Test Call Generation (for sandbox testing)
# =============================================================================

SAMPLE_CUSTOMER_SCENARIOS = [
    {
        "name": "Simple Pickup Order",
        "caller_name": "Sarah Johnson",
        "messages": [
            "Hi, I'd like to place an order for pickup",
            "Can I get a Margherita Pizza please?",
            "That's all, thanks",
            "Yes, that's correct",
        ],
        "expected_items": ["Margherita Pizza"],
        "order_type": "pickup",
    },
    {
        "name": "Delivery Order with Upsell",
        "caller_name": "Michael Chen",
        "messages": [
            "Hello, I want to order for delivery",
            "I'll have the Spaghetti Bolognese and a Caesar Salad",
            "Sure, I'll add an Italian Soda",
            "My address is 456 Oak Street, Apt 12",
            "Perfect, thank you!",
        ],
        "expected_items": ["Spaghetti Bolognese", "Caesar Salad", "Italian Soda"],
        "order_type": "delivery",
    },
    {
        "name": "Reservation Request",
        "caller_name": "Emily Davis",
        "messages": [
            "Hi, I'd like to make a reservation",
            "For 4 people, this Saturday at 7pm",
            "Yes, Emily Davis",
            "Thank you!",
        ],
        "expected_items": [],
        "order_type": "reservation",
    },
    {
        "name": "Complex Order with Modifications",
        "caller_name": "James Wilson",
        "messages": [
            "Hey, I want to order a few things",
            "I'll take 2 Pepperoni Pizzas and a Fettuccine Alfredo",
            "Can I also get 3 Cannolis for dessert?",
            "And 2 Espressos",
            "Actually, make that 3 Espressos",
            "That's everything",
            "Yes, perfect!",
        ],
        "expected_items": ["Pepperoni Pizza", "Fettuccine Alfredo", "Cannoli", "Espresso"],
        "order_type": "pickup",
    },
    {
        "name": "Allergy Question",
        "caller_name": "Lisa Park",
        "messages": [
            "Hi, I have a question about allergies",
            "Does the Chicken Parmesan contain gluten?",
            "Okay, I'll have the Grilled Salmon instead",
            "For pickup please",
            "Yes, that's all",
        ],
        "expected_items": ["Grilled Salmon"],
        "order_type": "pickup",
    },
    {
        "name": "Escalation Request",
        "caller_name": "Robert Brown",
        "messages": [
            "I need to speak with a manager",
            "I had an issue with my last order",
        ],
        "expected_items": [],
        "order_type": "escalation",
    },
]


def get_test_scenarios() -> List[Dict[str, Any]]:
    """Get available test call scenarios."""
    return [
        {
            "id": i,
            "name": s["name"],
            "caller_name": s["caller_name"],
            "message_count": len(s["messages"]),
            "order_type": s["order_type"],
            "expected_items": s["expected_items"],
        }
        for i, s in enumerate(SAMPLE_CUSTOMER_SCENARIOS)
    ]


def get_scenario_by_id(scenario_id: int) -> Optional[Dict[str, Any]]:
    """Get a specific test scenario by ID."""
    if 0 <= scenario_id < len(SAMPLE_CUSTOMER_SCENARIOS):
        return SAMPLE_CUSTOMER_SCENARIOS[scenario_id]
    return None
