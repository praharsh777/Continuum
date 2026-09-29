"""
Continuum Confidence Scoring Module
Implements FR-5: Memory-driven confidence scoring based on Hindsight recall against candidate fix patterns.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from agent.db import get_resolution
from agent.memory import default_memory_manager, HindsightMemoryManager

logger = logging.getLogger(__name__)


class ConfidenceScorer:
    """
    Computes confidence score for a suggested fix by querying Hindsight memory
    for past postmortems/experiences that applied similar fixes and checking their outcomes.
    """

    def __init__(self, memory_manager: Optional[HindsightMemoryManager] = None):
        self.memory = memory_manager or default_memory_manager

    def compute_confidence(
        self,
        suggested_fix: str,
        current_incident_id: Optional[str] = None,
        top_n: int = 3
    ) -> Tuple[Optional[float], str, List[Dict[str, Any]]]:
        """
        Calculates confidence score:
        score = (count of past resolutions with outcome='RESOLVED') / (total count of past resolutions)
        
        Returns:
            Tuple of (confidence_score, confidence_label, supporting_records)
        """
        if not suggested_fix or not suggested_fix.strip():
            return None, "no prior track record — first time this fix is suggested", []

        try:
            # Recall similar fix patterns from Hindsight
            recalled_fix_memories = self.memory.recall_similar_fixes(suggested_fix, top_n=top_n)
        except Exception as e:
            logger.error(f"Error querying Hindsight for fix similarity: {e}")
            return None, "confidence unavailable — memory lookup failed", []

        if not recalled_fix_memories:
            return None, "no prior track record — first time this fix is suggested", []

        total_attempts = 0
        successful_attempts = 0
        seen_incident_ids = set()
        supporting_records: List[Dict[str, Any]] = []

        for mem in recalled_fix_memories:
            # Extract incident reference
            inc_id = mem.get("document_id") or mem.get("metadata", {}).get("incident_id")
            if not inc_id or inc_id == current_incident_id:
                # Skip self-references or entries without incident IDs
                continue

            if inc_id in seen_incident_ids:
                continue
            seen_incident_ids.add(inc_id)

            # Determine outcome: prioritize SQLite resolutions table, fallback to memory metadata/text
            outcome = None
            res_record = get_resolution(inc_id)
            if res_record:
                outcome = res_record.get("outcome")
            elif "outcome" in mem.get("metadata", {}):
                outcome = mem["metadata"]["outcome"]
            else:
                mem_text = mem.get("text", "").upper()
                if "OUTCOME: RESOLVED" in mem_text or "SUCCESSFULLY RESOLVED" in mem_text:
                    outcome = "RESOLVED"
                elif "DID_NOT_RESOLVE" in mem_text or "FAILED TO RESOLVE" in mem_text:
                    outcome = "DID_NOT_RESOLVE"

            if outcome in ("RESOLVED", "DID_NOT_RESOLVE"):
                total_attempts += 1
                if outcome == "RESOLVED":
                    successful_attempts += 1
                supporting_records.append({
                    "incident_id": inc_id,
                    "outcome": outcome,
                    "memory_id": mem.get("id"),
                    "text_snippet": mem.get("text", "")[:120]
                })

        if total_attempts == 0:
            return None, "no prior track record — first time this fix is suggested", []

        confidence_score = round(successful_attempts / total_attempts, 2)
        confidence_label = f"{successful_attempts} of {total_attempts} similar past incidents resolved with this fix"

        return confidence_score, confidence_label, supporting_records


# Singleton convenience instance
default_confidence_scorer = ConfidenceScorer()
