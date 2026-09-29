"""
Synthetic Incident Generator for Continuum
Implements FR-7 & FR-8: Generates 50 realistic microservice incidents embedding the A -> B -> C demo arc.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SYNTHETIC_DATA_PATH = DATA_DIR / "synthetic_incidents.json"

SERVICES = [
    "payment-gateway",
    "auth-service",
    "inventory-manager",
    "order-fulfillment",
    "notification-worker",
    "search-indexer",
    "user-profile-svc",
    "ledger-service",
    "api-edge-router",
    "recommendation-engine"
]

def build_50_synthetic_incidents() -> List[Dict[str, Any]]:
    incidents: List[Dict[str, Any]] = []
    base_time = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)

    # ------------------------------------------------------------------
    # The Core Demonstration Arc (Incidents A, B, C)
    # ------------------------------------------------------------------
    # INC-DEMO-A: Novel incident with Redis pipeline buffer overflow causing silent packet drops
    incident_a = {
        "incident_id": "INC-DEMO-A",
        "service_name": "order-fulfillment",
        "severity": "SEV1",
        "status": "OPEN",
        "created_at": (base_time + timedelta(days=9, hours=2)).isoformat(),
        "symptoms": "Silent drop of checkout confirmation events; orders stuck in pending-payment state without error dispatch.",
        "log_excerpt": (
            "2026-09-29T12:14:02.104Z [ERROR] [order-fulfillment] redis_pipe: buffer watermark exceeded (98.4MB > 64MB limit)\n"
            "2026-09-29T12:14:02.105Z [WARN] [order-fulfillment] dispatch_event: connection drained, dropping payload batch [order_id: ord_91823]\n"
            "2026-09-29T12:14:03.412Z [ERROR] [order-fulfillment] pipeline backpressure: TCP send queue choked, ACK timed out after 5000ms"
        ),
        "target_fix": "Increase Redis client command buffer from 64MB to 256MB and enable auto-flushing on pipeline backpressure threshold.",
        "resolution": None,
        "postmortem": None,
        "is_demo_arc": "Incident A (Novel Incident)"
    }

    # INC-DEMO-B: Same root cause as A, differently worded, later timestamp
    incident_b = {
        "incident_id": "INC-DEMO-B",
        "service_name": "order-fulfillment",
        "severity": "SEV1",
        "status": "OPEN",
        "created_at": (base_time + timedelta(days=9, hours=6)).isoformat(),
        "symptoms": "Purchases hanging on confirmation step; queue processing stalling with pipeline write timeouts.",
        "log_excerpt": (
            "2026-09-29T16:22:11.881Z [WARN] [order-fulfillment] async_stream: TCP buffer full while flushing batch pipeline\n"
            "2026-09-29T16:22:12.002Z [ERROR] [order-fulfillment] ClientBufferExceededException: downstream redis pipeline writer unable to append command\n"
            "2026-09-29T16:22:13.119Z [ERROR] [order-fulfillment] order_state_machine: transaction ord_99214 transitioned to UNCONFIRMED due to unhandled pipeline stall"
        ),
        "target_fix": "Increase Redis client command buffer from 64MB to 256MB and enable auto-flushing on pipeline backpressure threshold.",
        "resolution": None,
        "postmortem": None,
        "is_demo_arc": "Incident B (Repeat of A with different wording)"
    }

    # INC-DEMO-C: Superficially similar (order confirmation failure on order-fulfillment), but different root cause (Database deadlocks, not Redis pipeline)
    incident_c = {
        "incident_id": "INC-DEMO-C",
        "service_name": "order-fulfillment",
        "severity": "SEV2",
        "status": "OPEN",
        "created_at": (base_time + timedelta(days=9, hours=8)).isoformat(),
        "symptoms": "Order fulfillment timeouts and failing order confirmations under concurrent checkout peak.",
        "log_excerpt": (
            "2026-09-29T18:05:40.312Z [ERROR] [order-fulfillment] org.postgresql.util.PSQLException: ERROR: deadlock detected\n"
            "2026-09-29T18:05:40.313Z [DETAIL] Process 29188 waits for ShareLock on transaction 849201; blocked by process 29195.\n"
            "2026-09-29T18:05:40.314Z [HINT] See server log for query details. Statement: UPDATE inventory_items SET reserved_qty = reserved_qty + 1 WHERE sku = $1"
        ),
        "target_fix": "Enforce consistent SKU lock acquisition ordering (alphabetical by SKU) before updating inventory rows to prevent cyclic deadlocks.",
        "resolution": None,
        "postmortem": None,
        "is_demo_arc": "Incident C (Superficially resembles A/B, but distinct root cause)"
    }

    # ------------------------------------------------------------------
    # 47 Diverse Historical and Open Microservice Incidents
    # ------------------------------------------------------------------
    historical_templates = [
        # 1. Connection Pool Exhaustion (auth-service)
        {
            "service": "auth-service",
            "sev": "SEV2",
            "symptoms": "HTTP 500 errors and elevated latency on user token validation endpoints.",
            "logs": "TimeoutError: QueuePool limit of size 20 overflow 10 reached, connection timed out after 30.00 seconds\nSQLAlchemy.exc.TimeoutError: could not obtain connection from pool",
            "root_cause": "Database connection pool exhausted due to unclosed sessions in OAuth refresh handler.",
            "fix": "Wrapped session lifecycle in context manager and increased pool size to 50 with 10s idle recycle.",
            "outcome": "RESOLVED"
        },
        # 2. Redis Eviction Storm (search-indexer)
        {
            "service": "search-indexer",
            "sev": "SEV2",
            "symptoms": "Search index queries failing with cache misses and latency spiking by 400%.",
            "logs": "OOM command not allowed when used memory > 'maxmemory' (policy: volatile-lru)\nCache miss rate climbed from 4% to 92% across all search nodes",
            "root_cause": "Key TTLs missing on product category search facets, triggering bulk LRU key evictions.",
            "fix": "Applied explicit 3600s TTL to facet caches and increased Redis maxmemory reservation.",
            "outcome": "RESOLVED"
        },
        # 3. Kafka Consumer Lag (notification-worker)
        {
            "service": "notification-worker",
            "sev": "SEV3",
            "symptoms": "Email notifications delayed by over 45 minutes; user password resets delayed.",
            "logs": "CommitFailedException: Commit cannot be completed since the group has already rebalanced\nConsumer poll interval exceeded max.poll.interval.ms (300000ms)",
            "root_cause": "Downstream SMTP provider throttled connections, causing message processing loop to block beyond poll interval.",
            "fix": "Offloaded email dispatch to asynchronous threadpool and decoupled Kafka message ack from SMTP delivery.",
            "outcome": "RESOLVED"
        },
        # 4. Out of Memory JVM Crash (ledger-service)
        {
            "service": "ledger-service",
            "sev": "SEV1",
            "symptoms": "Ledger service pod crash-looping with ExitCode 137; accounting reconciliations failed.",
            "logs": "java.lang.OutOfMemoryError: Java heap space\nDumping heap to java_pid1.hprof ...\nkubelet: Container ledger-service was killed by OOMKilled",
            "root_cause": "Unbounded query loading 500,000 monthly transaction lines into memory for end-of-day audit.",
            "fix": "Refactored transaction reconciliation into cursor-based streaming batch iterator of 1000 items.",
            "outcome": "RESOLVED"
        },
        # 5. DNS Resolution Failure (api-edge-router)
        {
            "service": "api-edge-router",
            "sev": "SEV1",
            "symptoms": "Upstream microservices reporting 502 Bad Gateway across all external traffic.",
            "logs": "nginx: [error] 14#14: *92102 payment-gateway.internal could not be resolved (3: Host not found)\nresolver 10.96.0.10:53 query timed out for cluster domain",
            "root_cause": "CoreDNS pods overwhelmed by single-concurrency UDP connection limits during traffic surge.",
            "fix": "Deployed NodeLocal DNSCache daemonset and enabled TCP fallback for cluster internal DNS queries.",
            "outcome": "RESOLVED"
        },
        # 6. Disk Space Exhaustion (search-indexer)
        {
            "service": "search-indexer",
            "sev": "SEV2",
            "symptoms": "Elasticsearch indices marked read-only; documents cannot be indexed.",
            "logs": "cluster_block_exception: index [catalog_v3] blocked by: [TOO_MANY_REQUESTS/12/disk usage exceeded flood-stage watermark 95%]",
            "root_cause": "Debug level audit logs consuming root partition without logrotate compression.",
            "fix": "Purged archived audit logs, configured 7-day log rotation, and expanded persistent volume by 200GB.",
            "outcome": "RESOLVED"
        },
        # 7. Expired TLS Certificate (payment-gateway)
        {
            "service": "payment-gateway",
            "sev": "SEV1",
            "symptoms": "Payment processing completely down; credit card tokenization requests failing with SSL handshake error.",
            "logs": "SSLHandshakeException: PKIX path validation failed: java.security.cert.CertificateExpiredException: NotAfter: Sun Sep 21 00:00:00 UTC 2026\nRemote peer terminated handshake",
            "root_cause": "Automated cert-manager renewal webhook secret expired without triggering alert.",
            "fix": "Manually rotated payment provider mTLS certificates and updated cert-manager Prometheus alert rule.",
            "outcome": "RESOLVED"
        },
        # 8. JWT Key ID Mismatch (auth-service)
        {
            "service": "auth-service",
            "sev": "SEV2",
            "symptoms": "Users suddenly logged out; valid session tokens rejected with HTTP 401 Unauthorized.",
            "logs": "InvalidTokenException: Key with kid 'auth-key-2026-b' not found in JWKS key set\nFailed to verify signature for inbound Bearer authorization token",
            "root_cause": "Canary deployment published new key ID before JWKS endpoint cache was purged across edge nodes.",
            "fix": "Flushed edge CDN cache for /.well-known/jwks.json and synchronized signing key rollover schedule.",
            "outcome": "RESOLVED"
        },
        # 9. Circuit Breaker Stuck Open (user-profile-svc)
        {
            "service": "user-profile-svc",
            "sev": "SEV3",
            "symptoms": "User preferences failing to load; displaying fallback default values for all users.",
            "logs": "CircuitBreaker 'UserProfileDB' is OPEN and does not permit further calls (failure rate 78.4% >= threshold 50%)\nFallback method getStaticProfile invoked",
            "root_cause": "Database transient network blip tripped circuit breaker; reset timeout was misconfigured to 24 hours.",
            "fix": "Reduced circuit breaker sleepWindowInMilliseconds from 86400000 to 15000 and manually reset breaker state.",
            "outcome": "RESOLVED"
        },
        # 10. Thread Pool Saturation (inventory-manager)
        {
            "service": "inventory-manager",
            "sev": "SEV2",
            "symptoms": "Inventory reservation API latency jumped from 25ms to 8500ms; thread pool rejects incoming tasks.",
            "logs": "RejectedExecutionException: Task java.util.concurrent.FutureTask@381af rejected from ThreadPoolExecutor [Running, pool size 64, active threads 64, queued tasks 500]",
            "root_cause": "Synchronous HTTP call to legacy ERP supplier API had no read timeout configured, holding worker threads indefinitely.",
            "fix": "Added strict 1500ms HTTP timeout and configured circuit breaker around legacy ERP gateway.",
            "outcome": "RESOLVED"
        },
        # 11. Rate Limit Throttling (recommendation-engine)
        {
            "service": "recommendation-engine",
            "sev": "SEV3",
            "symptoms": "Personalized product recommendations absent on homepage; fallback popular products shown.",
            "logs": "HTTP 429 Too Many Requests from VectorDB endpoint /v1/embeddings/query\nRetry-After: 60s header received. Dropping batch request.",
            "root_cause": "Batch recommendation recalculation job burst exceeded external embedding provider rate limit.",
            "fix": "Implemented client-side token bucket rate limiter and distributed recalculation across 6 hour window.",
            "outcome": "RESOLVED"
        },
        # 12. Bad Deploy Database Migration Lock (ledger-service)
        {
            "service": "ledger-service",
            "sev": "SEV1",
            "symptoms": "All ledger write operations blocked; transactions failing with query lock timeout.",
            "logs": "Lock wait timeout exceeded; try restarting transaction: ALTER TABLE accounts ADD COLUMN risk_tier VARCHAR(16) NOT NULL DEFAULT 'STANDARD'\nTable accounts locked exclusively by migration pid 4812",
            "root_cause": "Migration script ran ALTER TABLE with default value on large table without pt-online-schema-change.",
            "fix": "Terminated blocking ALTER query, reverted migration, and executed non-blocking online schema update.",
            "outcome": "RESOLVED"
        }
    ]

    # Generate 47 incidents based on templates with varied parameters
    counter = 1
    for i in range(47):
        template = historical_templates[i % len(historical_templates)]
        inc_id = f"INC-{1000 + counter}"
        counter += 1
        
        # Stagger timestamp over previous 9 days
        days_ago = 9 - (i * 9 // 47)
        hour_offset = (i * 7) % 24
        minute_offset = (i * 13) % 60
        created_time = (base_time + timedelta(days=days_ago, hours=hour_offset, minutes=minute_offset)).isoformat()
        
        # Decide status: 38 resolved, 9 open
        is_resolved = (i < 38)
        status = "RESOLVED" if is_resolved else "OPEN"
        
        svc = template["service"]
        symptoms = f"{template['symptoms']} (Incident variation {i+1})"
        log_excerpt = f"[{created_time}] [{svc}] {template['logs']}"
        sev = template["sev"]
        
        resolution = None
        postmortem = None
        if is_resolved:
            resolved_time = (datetime.fromisoformat(created_time) + timedelta(minutes=25 + (i * 3 % 45))).isoformat()
            duration = int((datetime.fromisoformat(resolved_time) - datetime.fromisoformat(created_time)).total_seconds())
            resolution = {
                "incident_id": inc_id,
                "fix_applied": template["fix"],
                "outcome": template["outcome"],
                "resolved_at": resolved_time,
                "time_to_resolve_seconds": duration
            }
            postmortem = {
                "incident_id": inc_id,
                "narrative_summary": f"Incident {inc_id} in {svc}. Symptom: {symptoms}. Root cause: {template['root_cause']}. Fix applied: {template['fix']}. Outcome: {template['outcome']}.",
                "retained_memory_id": f"OP-HIST-{inc_id}",
                "retained_at": resolved_time
            }

        incidents.append({
            "incident_id": inc_id,
            "service_name": svc,
            "severity": sev,
            "status": status,
            "created_at": created_time,
            "symptoms": symptoms,
            "log_excerpt": log_excerpt,
            "target_fix": template["fix"],
            "resolution": resolution,
            "postmortem": postmortem,
            "is_demo_arc": None
        })

    # Add Incidents A, B, C into the corpus (total 50)
    incidents.extend([incident_a, incident_b, incident_c])

    # Sort deterministically by created_at
    incidents.sort(key=lambda x: x["created_at"])
    return incidents


def write_synthetic_data_file() -> List[Dict[str, Any]]:
    incidents = build_50_synthetic_incidents()
    assert len(incidents) == 50, f"Expected exactly 50 incidents, got {len(incidents)}"
    
    with open(SYNTHETIC_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(incidents, f, indent=2)
        
    print(f"Generated {len(incidents)} synthetic incidents at {SYNTHETIC_DATA_PATH}")
    return incidents


if __name__ == "__main__":
    write_synthetic_data_file()
