"""
Continuum State Reset and Demo Rehearsal Script
Implements NFR-4: Resets SQLite and Hindsight memory bank, then seeds the 50-incident dataset.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("reset_demo_state")

from agent.db import (
    create_incident,
    init_db,
    reset_db,
    save_postmortem,
    save_resolution,
)
from agent.memory import default_memory_manager
from scripts.generate_synthetic_data import SYNTHETIC_DATA_PATH, write_synthetic_data_file


def reset_and_seed(retain_historical_in_hindsight: bool = True, max_retained_history: int = 15):
    logger.info("==================================================")
    logger.info("   CONTINUUM: RESETTING DEMO STATE (NFR-4)")
    logger.info("==================================================")

    # 1. Reset SQLite Database
    logger.info("Resetting SQLite database...")
    reset_db()
    logger.info("SQLite tables created cleanly.")

    # 2. Reset Hindsight Memory Bank
    logger.info(f"Resetting Hindsight bank '{default_memory_manager.bank_id}'...")
    try:
        bank_reset_ok = default_memory_manager.reset_bank()
        if bank_reset_ok:
            logger.info("Hindsight bank reset and recreated successfully.")
        else:
            logger.warning("Bank reset returned False, proceeding with existing bank.")
    except Exception as e:
        logger.warning(f"Could not reset Hindsight bank directly ({e}). Proceeding...")

    # 3. Load or generate synthetic data
    if not SYNTHETIC_DATA_PATH.exists():
        logger.info("Generating synthetic incidents...")
        incidents = write_synthetic_data_file()
    else:
        with open(SYNTHETIC_DATA_PATH, "r", encoding="utf-8") as f:
            incidents = json.load(f)

    logger.info(f"Loaded {len(incidents)} incidents from {SYNTHETIC_DATA_PATH.name}.")

    # 4. Seed SQLite database
    retained_count = 0
    resolved_count = 0
    open_count = 0

    # Retain a diverse subset of historical postmortems into Hindsight
    # Ensure INC-DEMO-A, INC-DEMO-B, INC-DEMO-C are NOT in Hindsight (they must start fresh)
    seen_services = set()

    for inc in incidents:
        inc_id = inc["incident_id"]
        create_incident(
            incident_id=inc_id,
            service_name=inc["service_name"],
            symptoms=inc["symptoms"],
            severity=inc["severity"],
            log_excerpt=inc.get("log_excerpt"),
            created_at=inc["created_at"],
            status=inc["status"]
        )

        res = inc.get("resolution")
        pm = inc.get("postmortem")

        if res:
            resolved_count += 1
            save_resolution(
                incident_id=inc_id,
                fix_applied=res["fix_applied"],
                outcome=res["outcome"],
                resolved_at=res["resolved_at"],
                time_to_resolve_seconds=res.get("time_to_resolve_seconds")
            )

        if pm:
            save_postmortem(
                incident_id=inc_id,
                narrative_summary=pm["narrative_summary"],
                retained_memory_id=pm.get("retained_memory_id"),
                retained_at=pm["retained_at"]
            )

            # Retain in Hindsight for historical institutional memory
            # Exclude demo arc (A, B, C)
            if (
                retain_historical_in_hindsight
                and not inc.get("is_demo_arc")
                and retained_count < max_retained_history
                and inc["service_name"] not in seen_services
            ):
                try:
                    logger.info(f"Retaining historical memory for {inc_id} ({inc['service_name']})...")
                    ret_res = default_memory_manager.retain_postmortem(
                        incident_id=inc_id,
                        service_name=inc["service_name"],
                        narrative_summary=pm["narrative_summary"],
                        outcome=res["outcome"] if res else "RESOLVED"
                    )
                    retained_count += 1
                    seen_services.add(inc["service_name"])
                    time.sleep(0.3)  # Gentle spacing for API
                except Exception as e:
                    logger.warning(f"Failed to retain {inc_id} in Hindsight: {e}")
        else:
            open_count += 1

    logger.info("--------------------------------------------------")
    logger.info(f"Database seeded with {len(incidents)} incidents:")
    logger.info(f" - {resolved_count} Resolved incidents in SQLite")
    logger.info(f" - {open_count} Open incidents in SQLite (including Incidents A, B, and C)")
    logger.info(f" - {retained_count} Historical postmortems seeded into Hindsight Cloud")
    logger.info("Demo arc (Incident A, B, C) is clean and ready for rehearsal.")
    logger.info("==================================================")


if __name__ == "__main__":
    reset_and_seed()
