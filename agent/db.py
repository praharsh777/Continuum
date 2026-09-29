"""
Continuum Data Access Layer (SQLite)
Implements FR-1 data models and operations.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Default database path
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "continuum.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS incidents (
  incident_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  service_name TEXT NOT NULL,
  symptoms TEXT NOT NULL,
  log_excerpt TEXT,
  severity TEXT NOT NULL CHECK(severity IN ('SEV1','SEV2','SEV3','SEV4')),
  status TEXT NOT NULL CHECK(status IN ('OPEN','DIAGNOSING','RESOLVED')) DEFAULT 'OPEN'
);

CREATE TABLE IF NOT EXISTS diagnoses (
  diagnosis_id TEXT PRIMARY KEY,
  incident_id TEXT NOT NULL REFERENCES incidents(incident_id),
  root_cause_hypothesis TEXT,
  suggested_fix TEXT,
  cited_memory_ids TEXT,        -- JSON array, stored as text
  confidence_score REAL,        -- 0.0–1.0, or NULL if no track record
  confidence_label TEXT,        -- human-readable, e.g. "4 of 5 similar past incidents"
  generated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS resolutions (
  incident_id TEXT PRIMARY KEY REFERENCES incidents(incident_id),
  fix_applied TEXT NOT NULL,
  outcome TEXT NOT NULL CHECK(outcome IN ('RESOLVED','DID_NOT_RESOLVE')),
  resolved_at TEXT NOT NULL,
  time_to_resolve_seconds INTEGER
);

CREATE TABLE IF NOT EXISTS postmortems (
  incident_id TEXT PRIMARY KEY REFERENCES incidents(incident_id),
  narrative_summary TEXT NOT NULL,
  retained_memory_id TEXT,      -- populated if Hindsight's retain returns ID/operation_id
  retained_at TEXT NOT NULL
);
"""


def get_db_path(custom_path: Optional[str | Path] = None) -> Path:
    if custom_path:
        path = Path(custom_path)
    else:
        env_path = os.getenv("SQLITE_DB_PATH")
        path = Path(env_path) if env_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection(custom_path: Optional[str | Path] = None) -> sqlite3.Connection:
    path = get_db_path(custom_path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(custom_path: Optional[str | Path] = None) -> None:
    """Initialize database tables according to FR-1 schema."""
    with get_connection(custom_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


def reset_db(custom_path: Optional[str | Path] = None) -> None:
    """Drop and recreate all tables for a clean state."""
    path = get_db_path(custom_path)
    with get_connection(path) as conn:
        conn.execute("PRAGMA foreign_keys = OFF;")
        conn.execute("DROP TABLE IF EXISTS postmortems;")
        conn.execute("DROP TABLE IF EXISTS resolutions;")
        conn.execute("DROP TABLE IF EXISTS diagnoses;")
        conn.execute("DROP TABLE IF EXISTS incidents;")
        conn.commit()
    init_db(path)


# ---------------------------------------------------------
# Incidents Operations
# ---------------------------------------------------------

def create_incident(
    incident_id: str,
    service_name: str,
    symptoms: str,
    severity: str,
    log_excerpt: Optional[str] = None,
    created_at: Optional[str] = None,
    status: str = "OPEN",
    custom_path: Optional[str | Path] = None
) -> Dict[str, Any]:
    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat()
        
    with get_connection(custom_path) as conn:
        conn.execute(
            """
            INSERT INTO incidents (incident_id, created_at, service_name, symptoms, log_excerpt, severity, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (incident_id, created_at, service_name, symptoms, log_excerpt, severity, status)
        )
        conn.commit()
    return get_incident(incident_id, custom_path=custom_path) # type: ignore


def get_incident(incident_id: str, custom_path: Optional[str | Path] = None) -> Optional[Dict[str, Any]]:
    with get_connection(custom_path) as conn:
        cursor = conn.execute("SELECT * FROM incidents WHERE incident_id = ?", (incident_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def list_incidents(
    status: Optional[str] = None,
    service_name: Optional[str] = None,
    limit: int = 100,
    custom_path: Optional[str | Path] = None
) -> List[Dict[str, Any]]:
    query = "SELECT * FROM incidents WHERE 1=1"
    params: List[Any] = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if service_name:
        query += " AND service_name = ?"
        params.append(service_name)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with get_connection(custom_path) as conn:
        cursor = conn.execute(query, tuple(params))
        return [dict(row) for row in cursor.fetchall()]


def update_incident_status(incident_id: str, status: str, custom_path: Optional[str | Path] = None) -> bool:
    with get_connection(custom_path) as conn:
        cursor = conn.execute(
            "UPDATE incidents SET status = ? WHERE incident_id = ?",
            (status, incident_id)
        )
        conn.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------
# Diagnoses Operations
# ---------------------------------------------------------

def save_diagnosis(
    diagnosis_id: str,
    incident_id: str,
    root_cause_hypothesis: str,
    suggested_fix: str,
    cited_memory_ids: List[str],
    confidence_score: Optional[float] = None,
    confidence_label: Optional[str] = None,
    generated_at: Optional[str] = None,
    custom_path: Optional[str | Path] = None
) -> Dict[str, Any]:
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat()
    
    cited_json = json.dumps(cited_memory_ids)
    with get_connection(custom_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO diagnoses 
            (diagnosis_id, incident_id, root_cause_hypothesis, suggested_fix, cited_memory_ids, confidence_score, confidence_label, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (diagnosis_id, incident_id, root_cause_hypothesis, suggested_fix, cited_json, confidence_score, confidence_label, generated_at)
        )
        conn.commit()
    return get_diagnosis(incident_id, custom_path=custom_path) # type: ignore


def get_diagnosis(incident_id: str, custom_path: Optional[str | Path] = None) -> Optional[Dict[str, Any]]:
    with get_connection(custom_path) as conn:
        cursor = conn.execute(
            "SELECT * FROM diagnoses WHERE incident_id = ? ORDER BY generated_at DESC LIMIT 1",
            (incident_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        try:
            res["cited_memory_ids"] = json.loads(res["cited_memory_ids"]) if res.get("cited_memory_ids") else []
        except Exception:
            res["cited_memory_ids"] = []
        return res


# ---------------------------------------------------------
# Resolutions Operations
# ---------------------------------------------------------

def save_resolution(
    incident_id: str,
    fix_applied: str,
    outcome: str,
    resolved_at: Optional[str] = None,
    time_to_resolve_seconds: Optional[int] = None,
    custom_path: Optional[str | Path] = None
) -> Dict[str, Any]:
    if resolved_at is None:
        resolved_at = datetime.now(timezone.utc).isoformat()
    
    with get_connection(custom_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO resolutions 
            (incident_id, fix_applied, outcome, resolved_at, time_to_resolve_seconds)
            VALUES (?, ?, ?, ?, ?)
            """,
            (incident_id, fix_applied, outcome, resolved_at, time_to_resolve_seconds)
        )
        conn.commit()
    return get_resolution(incident_id, custom_path=custom_path) # type: ignore


def get_resolution(incident_id: str, custom_path: Optional[str | Path] = None) -> Optional[Dict[str, Any]]:
    with get_connection(custom_path) as conn:
        cursor = conn.execute("SELECT * FROM resolutions WHERE incident_id = ?", (incident_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def list_resolutions(custom_path: Optional[str | Path] = None) -> List[Dict[str, Any]]:
    with get_connection(custom_path) as conn:
        cursor = conn.execute("SELECT * FROM resolutions")
        return [dict(row) for row in cursor.fetchall()]


# ---------------------------------------------------------
# Postmortems Operations
# ---------------------------------------------------------

def save_postmortem(
    incident_id: str,
    narrative_summary: str,
    retained_memory_id: Optional[str] = None,
    retained_at: Optional[str] = None,
    custom_path: Optional[str | Path] = None
) -> Dict[str, Any]:
    if retained_at is None:
        retained_at = datetime.now(timezone.utc).isoformat()
        
    with get_connection(custom_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO postmortems 
            (incident_id, narrative_summary, retained_memory_id, retained_at)
            VALUES (?, ?, ?, ?)
            """,
            (incident_id, narrative_summary, retained_memory_id, retained_at)
        )
        conn.commit()
    return get_postmortem(incident_id, custom_path=custom_path) # type: ignore


def get_postmortem(incident_id: str, custom_path: Optional[str | Path] = None) -> Optional[Dict[str, Any]]:
    with get_connection(custom_path) as conn:
        cursor = conn.execute("SELECT * FROM postmortems WHERE incident_id = ?", (incident_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_incident_full_detail(incident_id: str, custom_path: Optional[str | Path] = None) -> Optional[Dict[str, Any]]:
    """Retrieve combined view of incident, diagnosis, resolution, and postmortem."""
    inc = get_incident(incident_id, custom_path=custom_path)
    if not inc:
        return None
    diag = get_diagnosis(incident_id, custom_path=custom_path)
    res = get_resolution(incident_id, custom_path=custom_path)
    pm = get_postmortem(incident_id, custom_path=custom_path)
    return {
        "incident": inc,
        "diagnosis": diag,
        "resolution": res,
        "postmortem": pm
    }
