"""
Auto-Learning Service for RingAI

Enables the AI to improve automatically without manual owner intervention:
- Tracks recurring menu suggestions and auto-applies aliases
- Learns from successful order patterns
- Flags only problematic calls for review
- Applies rule suggestions after confidence threshold

The goal: 85.6 → 95+ quality score through passive learning
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

# Thresholds for auto-learning
MENU_ALIAS_THRESHOLD = 5  # Apply alias after 5 occurrences (safety margin)
RULE_SUGGESTION_THRESHOLD = 3  # Apply rule after 3 occurrences
LOW_QUALITY_THRESHOLD = 70  # Flag calls below this score
AUTO_ALIAS_CONFIDENCE = 0.8  # Confidence needed for auto-apply


class AutoLearningService:
    """
    Processes call analysis results and automatically improves the AI.
    """
    
    def __init__(self, db):
        self.db = db
    
    async def process_call_analysis(
        self,
        restaurant_id: str,
        call_id: str,
        analysis: Dict[str, Any],
        order_completed: bool = False,
        order_total: int = 0,
    ) -> Dict[str, Any]:
        """
        Process a completed call's analysis and trigger learning actions.
        
        Args:
            restaurant_id: Restaurant identifier
            call_id: The call/session ID
            analysis: Output from analyse_call_transcript
            order_completed: Whether an order was successfully placed
            order_total: Order total in cents (if completed)
        
        Returns:
            Dict with learning actions taken
        """
        actions_taken = {
            "aliases_learned": [],
            "rules_suggested": [],
            "flagged_for_review": False,
            "quality_score": analysis.get("quality_score"),
        }
        
        # A7-17: may be None when Gemini was unavailable (honest "analysis
        # unavailable" marker). None can't be compared with < / >= below, so we
        # guard every numeric branch on `is not None`.
        quality_score = analysis.get("quality_score")
        menu_suggestions = analysis.get("menu_suggestions", [])
        rule_suggestions = analysis.get("rule_suggestions", [])
        
        # 1. Process menu suggestions → potential aliases
        for suggestion in menu_suggestions:
            alias_result = await self._process_menu_suggestion(
                restaurant_id, suggestion, call_id
            )
            if alias_result:
                actions_taken["aliases_learned"].append(alias_result)
        
        # 2. Process rule suggestions
        for rule in rule_suggestions:
            rule_result = await self._process_rule_suggestion(
                restaurant_id, rule, call_id
            )
            if rule_result:
                actions_taken["rules_suggested"].append(rule_result)
        
        # 3. Flag low-quality calls for review
        if quality_score is not None and quality_score < LOW_QUALITY_THRESHOLD:
            await self._flag_call_for_review(
                restaurant_id, call_id, analysis, quality_score
            )
            actions_taken["flagged_for_review"] = True

        # 4. Track successful patterns (positive reinforcement)
        if order_completed and quality_score is not None and quality_score >= 80:
            await self._record_success_pattern(
                restaurant_id, call_id, order_total
            )
        
        # 5. Update restaurant learning stats
        await self._update_learning_stats(restaurant_id, actions_taken)
        
        logger.info(
            f"Learning processed for {restaurant_id}: "
            f"aliases={len(actions_taken['aliases_learned'])}, "
            f"flagged={actions_taken['flagged_for_review']}, "
            f"quality_score={actions_taken['quality_score']}"
        )
        
        return actions_taken
    
    async def _process_menu_suggestion(
        self,
        restaurant_id: str,
        suggestion,
        call_id: str,
    ) -> Optional[Dict[str, str]]:
        """
        Process a menu suggestion and potentially create an alias.

        Accepts either:
          - dict: {"said": "bowl of fish", "resolved_as": "Apollo Fish"}  <- structured format
          - str:  "Add 'X' as alias for Y"  <- legacy string format
        """
        # Structured dict format from updated analysis prompt
        if isinstance(suggestion, dict):
            alias_term = (suggestion.get("said") or "").strip()
            target_item = (suggestion.get("resolved_as") or "").strip()
            if not alias_term or not target_item:
                return None
        else:
            # Legacy string format — fall through to regex parser
            parsed = self._parse_menu_suggestion(suggestion)
            if not parsed:
                return None
            alias_term = parsed["alias"]
            target_item = parsed["target"]
        
        # Check if this suggestion already exists
        existing = await self.db.learning_suggestions.find_one({
            "restaurant_id": restaurant_id,
            "type": "menu_alias",
            "alias_term": alias_term.lower(),
        })
        
        if existing:
            # Increment occurrence count
            count = existing.get("occurrence_count", 1) + 1
            await self.db.learning_suggestions.update_one(
                {"_id": existing["_id"]},
                {
                    "$set": {"occurrence_count": count, "last_seen": datetime.now(timezone.utc).isoformat()},
                    "$push": {"call_ids": call_id}
                }
            )
            
            # Check if threshold reached for auto-apply
            if count >= MENU_ALIAS_THRESHOLD and not existing.get("applied"):
                applied = await self._apply_menu_alias(
                    restaurant_id, alias_term, target_item
                )
                if applied:
                    await self.db.learning_suggestions.update_one(
                        {"_id": existing["_id"]},
                        {"$set": {"applied": True, "applied_at": datetime.now(timezone.utc).isoformat()}}
                    )
                    return {"alias": alias_term, "target": target_item, "auto_applied": True}
        else:
            # First occurrence - record it
            await self.db.learning_suggestions.insert_one({
                "restaurant_id": restaurant_id,
                "type": "menu_alias",
                "alias_term": alias_term.lower(),
                "target_item": target_item,
                "occurrence_count": 1,
                "call_ids": [call_id],
                "first_seen": datetime.now(timezone.utc).isoformat(),
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "applied": False,
            })
        
        return {"alias": alias_term, "target": target_item, "auto_applied": False}
    
    def _parse_menu_suggestion(self, suggestion: str) -> Optional[Dict[str, str]]:
        """
        Parse menu suggestion text to extract alias and target.
        
        Examples:
        - "Add 'coke' as alias for Coca-Cola"
        - "Customer said 'wings', matched to 'Buffalo Wings'"
        - "'kung pao' should map to 'Kung Pao Chicken'"
        """
        import re
        
        suggestion_lower = suggestion.lower()
        
        # Pattern 1: "Add 'X' as alias for Y"
        match = re.search(r"add ['\"]?([^'\"]+)['\"]? as alias for ['\"]?([^'\"]+)['\"]?", suggestion_lower)
        if match:
            return {"alias": match.group(1).strip(), "target": match.group(2).strip()}
        
        # Pattern 2: "'X' should map to 'Y'"
        match = re.search(r"['\"]([^'\"]+)['\"]?\s*(?:should|could|might)\s*(?:map|match|link)\s*to\s*['\"]?([^'\"]+)['\"]?", suggestion_lower)
        if match:
            return {"alias": match.group(1).strip(), "target": match.group(2).strip()}
        
        # Pattern 3: "Customer said 'X', matched to 'Y'"
        match = re.search(r"(?:customer|caller)\s*said\s*['\"]([^'\"]+)['\"]?,?\s*(?:matched|match)\s*(?:to|with)\s*['\"]?([^'\"]+)['\"]?", suggestion_lower)
        if match:
            return {"alias": match.group(1).strip(), "target": match.group(2).strip()}
        
        # Pattern 4: Simple "X → Y" or "X = Y"
        match = re.search(r"['\"]?([^'\"→=]+)['\"]?\s*[→=]\s*['\"]?([^'\"]+)['\"]?", suggestion)
        if match:
            return {"alias": match.group(1).strip(), "target": match.group(2).strip()}
        
        return None
    
    async def _apply_menu_alias(
        self,
        restaurant_id: str,
        alias_term: str,
        target_item: str,
    ) -> bool:
        """
        Apply a learned alias to the menu system.
        """
        # Find the target menu item
        menu_item = await self.db.menu_items.find_one({
            "restaurant_id": restaurant_id,
            "name": {"$regex": f"^{re.escape(target_item)}$", "$options": "i"}
        })
        
        if not menu_item:
            # Try fuzzy match
            menu_item = await self.db.menu_items.find_one({
                "restaurant_id": restaurant_id,
                "name": {"$regex": target_item, "$options": "i"}
            })
        
        if menu_item:
            # Add alias to the item
            existing_aliases = menu_item.get("aliases", [])
            if alias_term.lower() not in [a.lower() for a in existing_aliases]:
                await self.db.menu_items.update_one(
                    {"_id": menu_item["_id"]},
                    {"$addToSet": {"aliases": alias_term.lower()}}
                )
                logger.info(f"Auto-applied alias: '{alias_term}' → '{menu_item['name']}'")
                return True
        
        # If no menu item found, store in global aliases collection
        await self.db.menu_aliases.update_one(
            {"restaurant_id": restaurant_id, "alias": alias_term.lower()},
            {
                "$set": {
                    "target": target_item,
                    "auto_learned": True,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
            upsert=True
        )
        logger.info(f"Stored global alias: '{alias_term}' → '{target_item}'")
        return True
    
    async def _process_rule_suggestion(
        self,
        restaurant_id: str,
        rule: str,
        call_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Track rule suggestions for potential auto-application.
        """
        rule_key = rule.lower().strip()[:200]  # Normalize
        
        existing = await self.db.learning_suggestions.find_one({
            "restaurant_id": restaurant_id,
            "type": "rule_suggestion",
            "rule_key": rule_key,
        })
        
        if existing:
            count = existing.get("occurrence_count", 1) + 1
            await self.db.learning_suggestions.update_one(
                {"_id": existing["_id"]},
                {
                    "$set": {"occurrence_count": count, "last_seen": datetime.now(timezone.utc).isoformat()},
                    "$push": {"call_ids": call_id}
                }
            )
            
            # Flag for owner attention if threshold reached
            if count >= RULE_SUGGESTION_THRESHOLD and not existing.get("flagged"):
                await self.db.learning_suggestions.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"flagged": True}}
                )
                return {"rule": rule, "occurrences": count, "needs_review": True}
        else:
            await self.db.learning_suggestions.insert_one({
                "restaurant_id": restaurant_id,
                "type": "rule_suggestion",
                "rule_key": rule_key,
                "rule_text": rule,
                "occurrence_count": 1,
                "call_ids": [call_id],
                "first_seen": datetime.now(timezone.utc).isoformat(),
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "flagged": False,
            })
        
        return None
    
    async def _flag_call_for_review(
        self,
        restaurant_id: str,
        call_id: str,
        analysis: Dict[str, Any],
        quality_score: int,
    ):
        """
        Flag a low-quality call for owner review.
        """
        await self.db.flagged_calls.insert_one({
            "restaurant_id": restaurant_id,
            "call_id": call_id,
            "quality_score": quality_score,
            "issues": analysis.get("issues", []),
            "order_accuracy": analysis.get("order_accuracy", "unknown"),
            "flagged_at": datetime.now(timezone.utc).isoformat(),
            "reviewed": False,
            "review_action": None,
        })
        logger.info(f"Flagged call {call_id} for review (score: {quality_score})")
    
    async def _record_success_pattern(
        self,
        restaurant_id: str,
        call_id: str,
        order_total: int,
    ):
        """
        Record successful call patterns for positive reinforcement.
        """
        await self.db.success_patterns.insert_one({
            "restaurant_id": restaurant_id,
            "call_id": call_id,
            "order_total": order_total,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })
    
    async def _update_learning_stats(
        self,
        restaurant_id: str,
        actions: Dict[str, Any],
    ):
        """
        Update restaurant's learning statistics.
        """
        await self.db.learning_stats.update_one(
            {"restaurant_id": restaurant_id},
            {
                "$inc": {
                    "total_calls_processed": 1,
                    "aliases_learned": len(actions.get("aliases_learned", [])),
                    "calls_flagged": 1 if actions.get("flagged_for_review") else 0,
                },
                "$set": {
                    "last_processed": datetime.now(timezone.utc).isoformat(),
                }
            },
            upsert=True
        )
    
    # ========================================
    # Query Methods for Dashboard
    # ========================================
    
    async def get_flagged_calls(
        self,
        restaurant_id: str,
        limit: int = 10,
        include_reviewed: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get calls flagged for owner review.
        """
        query = {"restaurant_id": restaurant_id}
        if not include_reviewed:
            query["reviewed"] = False
        
        calls = await (
            self.db.flagged_calls.find(query, {"_id": 0})
            .sort("flagged_at", -1)
            .limit(limit)
            .to_list(limit)
        )
        return calls
    
    async def get_learned_aliases(
        self,
        restaurant_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get all auto-learned aliases for a restaurant.
        """
        aliases = await (
            self.db.learning_suggestions.find({
                "restaurant_id": restaurant_id,
                "type": "menu_alias",
                "applied": True,
            }, {"_id": 0})
            .to_list(100)
        )
        return aliases
    
    async def get_pending_suggestions(
        self,
        restaurant_id: str,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get pending suggestions that haven't reached threshold yet.
        """
        aliases = await (
            self.db.learning_suggestions.find({
                "restaurant_id": restaurant_id,
                "type": "menu_alias",
                "applied": False,
            }, {"_id": 0})
            .to_list(50)
        )
        
        rules = await (
            self.db.learning_suggestions.find({
                "restaurant_id": restaurant_id,
                "type": "rule_suggestion",
                "flagged": True,
            }, {"_id": 0})
            .to_list(20)
        )
        
        return {"pending_aliases": aliases, "suggested_rules": rules}
    
    async def get_learning_stats(
        self,
        restaurant_id: str,
    ) -> Dict[str, Any]:
        """
        Get learning statistics for a restaurant.
        """
        stats = await self.db.learning_stats.find_one(
            {"restaurant_id": restaurant_id},
            {"_id": 0}
        )
        
        if not stats:
            return {
                "total_calls_processed": 0,
                "aliases_learned": 0,
                "calls_flagged": 0,
                "last_processed": None,
            }
        
        return stats
    
    async def mark_call_reviewed(
        self,
        call_id: str,
        action: str,  # "correct", "incorrect", "ignore"
        notes: Optional[str] = None,
    ):
        """
        Mark a flagged call as reviewed by owner.
        """
        await self.db.flagged_calls.update_one(
            {"call_id": call_id},
            {
                "$set": {
                    "reviewed": True,
                    "review_action": action,
                    "review_notes": notes,
                    "reviewed_at": datetime.now(timezone.utc).isoformat(),
                }
            }
        )


# Import for regex in _apply_menu_alias
import re


# Singleton instance
_learning_service: Optional[AutoLearningService] = None


def get_learning_service(db) -> AutoLearningService:
    """Get or create the auto-learning service instance."""
    global _learning_service
    if _learning_service is None:
        _learning_service = AutoLearningService(db)
    return _learning_service
