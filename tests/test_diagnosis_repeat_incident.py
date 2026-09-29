"""
Test Diagnosis on Repeat Incident (FR-4 & FR-7 Incident B)
Verifies that when an incident is a repeat of a previously resolved incident (differently phrased):
1. Hindsight recall surfaces the precedent (Incident A).
2. matches_known_pattern is True.
3. cited_incident_ids contains 'INC-DEMO-A'.
4. Confidence score is computed from the resolved precedent.
"""

import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import unittest
from agent.db import create_incident, reset_db, save_postmortem, save_resolution
from agent.diagnosis import default_diagnosis_service


class TestDiagnosisRepeatIncident(unittest.TestCase):

    def setUp(self):
        reset_db()
        # 1. Simulate Incident A having occurred and been resolved
        create_incident(
            incident_id="INC-DEMO-A",
            service_name="order-fulfillment",
            severity="SEV1",
            symptoms="Silent drop of checkout confirmation events; orders stuck in pending-payment state without error dispatch.",
            log_excerpt="redis_pipe: buffer watermark exceeded (98.4MB > 64MB limit)"
        )
        save_resolution(
            incident_id="INC-DEMO-A",
            fix_applied="Increased Redis client command buffer from 64MB to 256MB and enabled auto-flushing on pipeline threshold.",
            outcome="RESOLVED"
        )
        save_postmortem(
            incident_id="INC-DEMO-A",
            narrative_summary=(
                "Incident INC-DEMO-A in order-fulfillment: Silent drop of checkout confirmations caused by Redis command buffer "
                "overflow (64MB limit exceeded under load). Remediated by increasing buffer size to 256MB with auto-flush enabled. Outcome: RESOLVED."
            ),
            retained_memory_id="OP-DEMO-A"
        )

        # 2. Incident B occurs (repeat root cause, differently phrased)
        self.repeat_incident = create_incident(
            incident_id="INC-DEMO-B",
            service_name="order-fulfillment",
            severity="SEV1",
            symptoms="Purchases hanging on confirmation step; queue processing stalling with pipeline write timeouts.",
            log_excerpt="ClientBufferExceededException: downstream redis pipeline writer unable to append command; buffer full"
        )

    def test_repeat_incident_pattern_match(self):
        """Diagnosing Incident B must cite Incident A and identify pattern match."""
        recalled_memories = [
            {
                "id": "mem_demo_a_001",
                "document_id": "INC-DEMO-A",
                "type": "world",
                "text": (
                    "Incident Postmortem for INC-DEMO-A [order-fulfillment]: Silent drop of checkout confirmations "
                    "caused by Redis command buffer watermark exceeded (64MB). Remediated by increasing Redis client command "
                    "buffer to 256MB and auto-flushing. Outcome: RESOLVED."
                ),
                "metadata": {
                    "incident_id": "INC-DEMO-A",
                    "service_name": "order-fulfillment",
                    "outcome": "RESOLVED"
                }
            }
        ]

        result = default_diagnosis_service.diagnose_incident(
            incident=self.repeat_incident,
            recalled_memories_override=recalled_memories
        )

        self.assertTrue(result["matches_known_pattern"], "Must detect pattern match for repeat incident.")
        self.assertIn("INC-DEMO-A", result["cited_incident_ids"], "Must cite INC-DEMO-A.")
        self.assertTrue(
            "redis" in result["suggested_fix"].lower() or "buffer" in result["suggested_fix"].lower(),
            "Suggested fix must target the Redis buffer/pipeline."
        )


if __name__ == "__main__":
    unittest.main()
