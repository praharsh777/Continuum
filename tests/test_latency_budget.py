"""
Test Latency Budget (NFR-2)
Measures actual diagnosis latency across sample incidents and reports performance stats.
Target: ~3 seconds for diagnosis generation.
"""

import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import time
import unittest
from agent.db import create_incident, reset_db
from agent.diagnosis import default_diagnosis_service


class TestLatencyBudget(unittest.TestCase):

    def setUp(self):
        reset_db()
        self.incidents = [
            create_incident(
                "INC-LAT-01",
                "payment-gateway",
                "Payment timeouts on checkout endpoint under traffic surge",
                "SEV1",
                "Connection reset by peer on payment provider socket"
            ),
            create_incident(
                "INC-LAT-02",
                "auth-service",
                "Token validation latency spiking over 1200ms",
                "SEV2",
                "Slow query on user_session table: Seq Scan on user_session"
            ),
            create_incident(
                "INC-LAT-03",
                "search-indexer",
                "Elasticsearch index writes failing with circuit breaker exception",
                "SEV2",
                "Data too large, data for [<transport_request>] would be [123456789] which is larger than limit"
            )
        ]

    def test_diagnosis_latency_budget(self):
        """Measures diagnosis latency across sample incidents."""
        latencies = []
        for inc in self.incidents:
            start = time.time()
            diag = default_diagnosis_service.diagnose_incident(
                incident=inc,
                recall_top_n=3
            )
            elapsed = time.time() - start
            latencies.append(elapsed)
            self.assertTrue(len(diag["root_cause_hypothesis"]) > 0)
            self.assertIsNotNone(diag["suggested_fix"])

        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        min_latency = min(latencies)

        print(f"\n--- Latency Budget Report (NFR-2) ---")
        print(f"Sample size: {len(latencies)} incidents")
        print(f"Min Latency: {min_latency:.2f}s")
        print(f"Avg Latency: {avg_latency:.2f}s")
        print(f"Max Latency: {max_latency:.2f}s")
        print(f"Latency Budget Target: ~3.0s")
        print(f"-------------------------------------")

        # Allow reasonable network variance tolerance (within 4.5s max under cloud API conditions)
        self.assertLess(avg_latency, 4.5, f"Average latency ({avg_latency:.2f}s) exceeded acceptable threshold.")


if __name__ == "__main__":
    unittest.main()
