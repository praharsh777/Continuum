"""
Test Diagnosis on Novel Incident (FR-4 & FR-7 Incident A)
Verifies that when an incident is novel (no matching historical memory):
1. matches_known_pattern is strictly False.
2. cited_incident_ids is strictly empty (never hallucinates).
3. confidence_score is None (no prior track record).
"""

import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import unittest
from agent.db import create_incident, get_diagnosis, reset_db
from agent.diagnosis import default_diagnosis_service


class TestDiagnosisNovelIncident(unittest.TestCase):

    def setUp(self):
        reset_db()
        self.novel_incident = create_incident(
            incident_id="INC-DEMO-A",
            service_name="order-fulfillment",
            severity="SEV1",
            symptoms="Silent drop of checkout confirmation events; orders stuck in pending-payment state without error dispatch.",
            log_excerpt=(
                "2026-09-29T12:14:02.104Z [ERROR] [order-fulfillment] redis_pipe: buffer watermark exceeded (98.4MB > 64MB limit)\n"
                "2026-09-29T12:14:02.105Z [WARN] [order-fulfillment] dispatch_event: connection drained, dropping payload batch [order_id: ord_91823]"
            )
        )

    def test_novel_incident_zero_recall(self):
        """Zero recalled memories must yield matches_known_pattern=False, empty citations, and confidence=None."""
        result = default_diagnosis_service.diagnose_incident(
            incident=self.novel_incident,
            recalled_memories_override=[]
        )

        self.assertFalse(result["matches_known_pattern"], "Novel incident must not match known pattern.")
        self.assertEqual(len(result["cited_incident_ids"]), 0, "Novel incident must have zero cited incidents.")
        self.assertIsNone(result["confidence_score"], "Novel fix must have confidence score NULL (None).")
        self.assertIn("no prior track record", result["confidence_label"].lower())
        self.assertTrue(len(result["suggested_fix"]) > 0, "Must provide actionable remediation.")
        
        # Verify persistence in SQLite
        saved = get_diagnosis("INC-DEMO-A")
        self.assertIsNotNone(saved)
        self.assertEqual(saved["cited_memory_ids"], [])
        self.assertIsNone(saved["confidence_score"])


if __name__ == "__main__":
    unittest.main()
