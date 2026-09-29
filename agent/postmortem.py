"""
Continuum Postmortem Generation and Resolution Loop
Implements FR-6: Resolution capture -> LLM Postmortem Generation -> Hindsight Retention -> Database Persistence.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from dotenv import load_dotenv
from groq import Groq

from agent.db import (
    get_diagnosis,
    get_incident,
    save_postmortem,
    save_resolution,
    update_incident_status,
)
from agent.memory import default_memory_manager, HindsightMemoryManager

load_dotenv()
logger = logging.getLogger(__name__)

DEFAULT_PRIMARY_MODEL = os.getenv("GROQ_PRIMARY_MODEL", "openai/gpt-oss-120b")
DEFAULT_FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.3-70b-versatile")


class PostmortemService:
    """Manages the lifecycle of incident resolution and persistent institutional memory retention."""

    def __init__(
        self,
        groq_api_key: Optional[str] = None,
        primary_model: Optional[str] = None,
        fallback_model: Optional[str] = None,
        memory_manager: Optional[HindsightMemoryManager] = None
    ):
        self.api_key = groq_api_key or os.getenv("GROQ_API_KEY")
        self.primary_model = primary_model or DEFAULT_PRIMARY_MODEL
        self.fallback_model = fallback_model or DEFAULT_FALLBACK_MODEL
        self.memory = memory_manager or default_memory_manager
        self._groq_client = Groq(api_key=self.api_key) if self.api_key else None

    def _generate_narrative_with_llm(
        self,
        incident: Dict[str, Any],
        diagnosis: Optional[Dict[str, Any]],
        fix_applied: str,
        outcome: str
    ) -> str:
        """Calls Groq to generate a concise, professional postmortem narrative."""
        if not self._groq_client:
            # Fallback if Groq client is not configured
            root_cause = diagnosis.get("root_cause_hypothesis", "Unknown") if diagnosis else "Investigated during response"
            return (
                f"Incident {incident['incident_id']} [{incident['service_name']}]. "
                f"Symptoms: {incident['symptoms']}. Root Cause: {root_cause}. "
                f"Fix Applied: {fix_applied}. Outcome: {outcome}."
            )

        root_cause = diagnosis.get("root_cause_hypothesis", "") if diagnosis else ""
        system_prompt = (
            "You are Continuum's Postmortem Synthesizer. Generate a high-density, authoritative, "
            "and factual postmortem narrative for institutional engineering memory.\n"
            "Format: A single cohesive paragraph covering: "
            "1. Service and incident symptoms, "
            "2. Verified underlying root cause, "
            "3. Precise fix applied, "
            "4. Resolution outcome."
        )

        user_content = (
            f"Incident ID: {incident['incident_id']}\n"
            f"Service: {incident['service_name']}\n"
            f"Severity: {incident['severity']}\n"
            f"Symptoms: {incident['symptoms']}\n"
            f"Log Excerpt:\n{incident.get('log_excerpt', 'None')}\n"
            f"Diagnosed Root Cause: {root_cause}\n"
            f"Fix Applied: {fix_applied}\n"
            f"Resolution Outcome: {outcome}\n\n"
            f"Generate the postmortem summary paragraph now."
        )

        models = [self.primary_model, self.fallback_model]
        for model in models:
            try:
                response = self._groq_client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    temperature=0.2,
                    max_tokens=400
                )
                content = response.choices[0].message.content
                if content and content.strip():
                    return content.strip()
            except Exception as e:
                logger.warning(f"Postmortem generation failed on {model}: {e}")

        # Deterministic fallback narrative if LLM calls fail
        return (
            f"Incident {incident['incident_id']} on {incident['service_name']} was marked {outcome}. "
            f"Symptoms: {incident['symptoms']}. Fix applied: {fix_applied}."
        )

    def resolve_incident(
        self,
        incident_id: str,
        fix_applied: str,
        outcome: str = "RESOLVED",
        time_to_resolve_seconds: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Executes FR-6 live resolution loop:
        1. Persists resolution to SQLite.
        2. Updates incident status to RESOLVED.
        3. Synthesizes postmortem narrative via LLM.
        4. Retains postmortem into Hindsight Cloud.
        5. Saves postmortem to SQLite.
        """
        incident = get_incident(incident_id)
        if not incident:
            raise ValueError(f"Incident with ID '{incident_id}' not found.")

        # 1. Save Resolution to SQLite
        res_record = save_resolution(
            incident_id=incident_id,
            fix_applied=fix_applied,
            outcome=outcome,
            time_to_resolve_seconds=time_to_resolve_seconds
        )

        # 2. Update status in SQLite
        update_incident_status(incident_id, "RESOLVED")

        # 3. Generate Postmortem Narrative
        diagnosis = get_diagnosis(incident_id)
        narrative_summary = self._generate_narrative_with_llm(
            incident=incident,
            diagnosis=diagnosis,
            fix_applied=fix_applied,
            outcome=outcome
        )

        # 4. Retain into Hindsight Cloud (Live Memory Expansion)
        retained_memory_id = None
        try:
            logger.info(f"Retaining postmortem for {incident_id} in Hindsight Cloud...")
            ret_res = self.memory.retain_postmortem(
                incident_id=incident_id,
                service_name=incident["service_name"],
                narrative_summary=narrative_summary,
                outcome=outcome,
                metadata={
                    "fix_applied": fix_applied,
                    "severity": incident["severity"]
                }
            )
            retained_memory_id = ret_res.get("operation_id") or f"OP-RETAINED-{incident_id}"
            logger.info(f"Successfully retained {incident_id} in Hindsight. Result: {ret_res}")
        except Exception as e:
            logger.error(f"Failed to retain {incident_id} in Hindsight during resolution: {e}")
            retained_memory_id = f"LOCAL-FALLBACK-{incident_id}"

        # 5. Save Postmortem to SQLite
        pm_record = save_postmortem(
            incident_id=incident_id,
            narrative_summary=narrative_summary,
            retained_memory_id=retained_memory_id
        )

        return {
            "incident_id": incident_id,
            "status": "RESOLVED",
            "resolution": res_record,
            "postmortem": pm_record,
            "narrative_summary": narrative_summary,
            "retained_memory_id": retained_memory_id
        }


# Singleton convenience instance
default_postmortem_service = PostmortemService()
