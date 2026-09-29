"""
Test Confidence Scoring (FR-5)
Verifies memory-driven confidence calculation based on historical fix track records.
"""

import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import unittest
from unittest.mock import MagicMock
from agent.confidence import ConfidenceScorer
from agent.db import create_incident, init_db, reset_db, save_resolution


class TestConfidenceScoring(unittest.TestCase):

    def setUp(self):
        reset_db()
        self.mock_memory = MagicMock()
        self.scorer = ConfidenceScorer(memory_manager=self.mock_memory)

    def test_no_prior_track_record_empty_recall(self):
        """When Hindsight returns no past memories for the fix, score must be NULL."""
        self.mock_memory.recall_similar_fixes.return_value = []
        score, label, records = self.scorer.compute_confidence("Increase Redis client buffer to 256MB")
        self.assertIsNone(score)
        self.assertIn("no prior track record", label.lower())
        self.assertEqual(len(records), 0)

    def test_single_successful_precedent(self):
        """When 1 past incident applied this fix and resolved it, score must be 1.0 (100%)."""
        create_incident("INC-HIST-01", "auth-service", "Timeout", "SEV2")
        save_resolution(
            incident_id="INC-HIST-01",
            fix_applied="Increased connection pool size to 50",
            outcome="RESOLVED"
        )
        self.mock_memory.recall_similar_fixes.return_value = [
            {
                "id": "mem_001",
                "document_id": "INC-HIST-01",
                "text": "Fixed by increasing connection pool to 50",
                "metadata": {"incident_id": "INC-HIST-01", "outcome": "RESOLVED"}
            }
        ]

        score, label, records = self.scorer.compute_confidence("Increased connection pool size to 50")
        self.assertEqual(score, 1.0)
        self.assertIn("1 of 1", label)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["outcome"], "RESOLVED")

    def test_mixed_resolution_outcomes(self):
        """When 2 resolved and 1 failed attempt exist, score must be 0.67 (67%)."""
        create_incident("INC-HIST-10", "worker", "Crash", "SEV2")
        create_incident("INC-HIST-11", "worker", "Crash", "SEV2")
        create_incident("INC-HIST-12", "worker", "Crash", "SEV2")

        save_resolution("INC-HIST-10", "Restart worker instances", "RESOLVED")
        save_resolution("INC-HIST-11", "Restart worker instances", "RESOLVED")
        save_resolution("INC-HIST-12", "Restart worker instances", "DID_NOT_RESOLVE")

        self.mock_memory.recall_similar_fixes.return_value = [
            {"id": "m1", "document_id": "INC-HIST-10", "metadata": {"incident_id": "INC-HIST-10"}},
            {"id": "m2", "document_id": "INC-HIST-11", "metadata": {"incident_id": "INC-HIST-11"}},
            {"id": "m3", "document_id": "INC-HIST-12", "metadata": {"incident_id": "INC-HIST-12"}}
        ]

        score, label, records = self.scorer.compute_confidence("Restart worker instances")
        self.assertEqual(score, 0.67)
        self.assertIn("2 of 3", label)
        self.assertEqual(len(records), 3)

    def test_excludes_current_incident_self_reference(self):
        """Must not count the current open incident against itself."""
        create_incident("INC-CURRENT", "worker", "Crash", "SEV2")
        save_resolution("INC-CURRENT", "Applied hotfix", "RESOLVED")
        self.mock_memory.recall_similar_fixes.return_value = [
            {"id": "m1", "document_id": "INC-CURRENT", "metadata": {"incident_id": "INC-CURRENT"}}
        ]

        score, label, records = self.scorer.compute_confidence("Applied hotfix", current_incident_id="INC-CURRENT")
        self.assertIsNone(score)
        self.assertIn("no prior track record", label)


if __name__ == "__main__":
    unittest.main()
