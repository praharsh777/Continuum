"""
Test False-Match Avoidance on Superficially Similar Incident (FR-4 & FR-7 Incident C)
Verifies that when an incident superficially resembles prior incidents (same service, checkout failure)
but has a different actual root cause (Postgres database deadlocks vs Redis buffer overflow):
1. The agent avoids false match.
2. Does NOT cite INC-DEMO-A as a root-cause match.
3. Correctly identifies database deadlocks / lock ordering in root_cause_hypothesis.
"""

import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import unittest
from agent.db import create_incident, reset_db
from agent.diagnosis import default_diagnosis_service


class TestDiagnosisFalseMatchAvoidance(unittest.TestCase):

    def setUp(self):
        reset_db()
        self.incident_c = create_incident(
            incident_id="INC-DEMO-C",
            service_name="order-fulfillment",
            severity="SEV2",
            symptoms="Order fulfillment timeouts and failing order confirmations under concurrent checkout peak.",
            log_excerpt=(
                "2026-09-29T18:05:40.312Z [ERROR] [order-fulfillment] org.postgresql.util.PSQLException: ERROR: deadlock detected\n"
                "2026-09-29T18:05:40.313Z [DETAIL] Process 29188 waits for ShareLock on transaction 849201; blocked by process 29195.\n"
                "2026-09-29T18:05:40.314Z [HINT] Statement: UPDATE inventory_items SET reserved_qty = reserved_qty + 1 WHERE sku = $1"
            )
        )

    def test_avoids_false_match_with_redis_precedent(self):
        """Must not cite INC-DEMO-A (Redis buffer) for a PostgreSQL deadlock."""
        # Incident A memory is present in recall results
        recalled_memories = [
            {
                "id": "mem_demo_a_001",
                "document_id": "INC-DEMO-A",
                "type": "world",
                "text": (
                    "Incident Postmortem for INC-DEMO-A [order-fulfillment]: Silent drop of checkout confirmations "
                    "caused by Redis command buffer watermark exceeded (64MB). Remediated by increasing Redis buffer to 256MB. Outcome: RESOLVED."
                ),
                "metadata": {"incident_id": "INC-DEMO-A", "service_name": "order-fulfillment"}
            }
        ]

        result = default_diagnosis_service.diagnose_incident(
            incident=self.incident_c,
            recalled_memories_override=recalled_memories
        )

        # Must not cite INC-DEMO-A
        self.assertNotIn(
            "INC-DEMO-A",
            result["cited_incident_ids"],
            "Incident C must NOT cite INC-DEMO-A because the root cause is completely different."
        )

        # Must correctly diagnose deadlock
        root_cause_lower = result["root_cause_hypothesis"].lower()
        self.assertTrue(
            "deadlock" in root_cause_lower or "lock" in root_cause_lower or "postgresql" in root_cause_lower or "database" in root_cause_lower,
            f"Diagnosis must recognize database deadlock, got: {result['root_cause_hypothesis']}"
        )


if __name__ == "__main__":
    unittest.main()
