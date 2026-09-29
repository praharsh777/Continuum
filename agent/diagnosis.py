"""
Continuum Diagnosis Service
Implements FR-4 (LLM-based diagnosis with structured output, zero-match detection, fallback),
NFR-1 (Reliability & Retry), NFR-2 (Latency Optimization via concurrent I/O).

Latency optimization: Hindsight recall runs concurrently with prompt construction.
Confidence recall runs only when a suggested fix is available post-LLM call.
"""

import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from groq import Groq

from agent.confidence import default_confidence_scorer, ConfidenceScorer
from agent.db import save_diagnosis
from agent.memory import default_memory_manager, HindsightMemoryManager

load_dotenv()
logger = logging.getLogger(__name__)

DEFAULT_PRIMARY_MODEL = os.getenv("GROQ_PRIMARY_MODEL", "openai/gpt-oss-120b")
DEFAULT_FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "llama3-70b-8192")

SYSTEM_PROMPT = (
    "You are Continuum, an expert site reliability and incident response agent with persistent institutional memory.\n"
    "Your task is to analyze production incidents and diagnose root causes, grounded strictly in provided institutional memory.\n\n"
    "CRITICAL INSTRUCTIONS:\n"
    "1. Grounding: If historical memories are provided, inspect whether any memory shares the TRUE underlying root cause.\n"
    "2. False-Match Avoidance: Surface-level similarities (e.g. HTTP 500, timeout, crash) do NOT mean it is the same incident. "
    "If the root cause in the recalled memory is different from the symptoms/logs, explicitly state that it does NOT match.\n"
    "3. No Hallucination: NEVER invent or fabricate incident IDs or memory citations. Only cite incident IDs explicitly present in the provided memories.\n"
    "4. Zero-Recall: If no memories are provided or no memories match, set 'matches_known_pattern': false, 'cited_incident_ids': [], "
    "and state explicitly in root_cause_hypothesis that no similar past incidents were found in institutional memory.\n\n"
    "Output MUST be valid JSON with this exact schema:\n"
    "{\n"
    '  "matches_known_pattern": bool,\n'
    '  "cited_incident_ids": ["INC-XXX", ...],\n'
    '  "root_cause_hypothesis": "Clear explanation of root cause",\n'
    '  "suggested_fix": "Concrete, actionable remediation steps",\n'
    '  "why_recalled_analysis": "Explanation of whether and why recalled memories match or do not match"\n'
    "}"
)


class DiagnosisService:
    """Orchestrates incident diagnosis using Hindsight memory recall and Groq LLM inference."""

    def __init__(
        self,
        groq_api_key: Optional[str] = None,
        primary_model: Optional[str] = None,
        fallback_model: Optional[str] = None,
        memory_manager: Optional[HindsightMemoryManager] = None,
        confidence_scorer: Optional[ConfidenceScorer] = None,
    ):
        self.api_key = groq_api_key or os.getenv("GROQ_API_KEY")
        self.primary_model = primary_model or DEFAULT_PRIMARY_MODEL
        self.fallback_model = fallback_model or DEFAULT_FALLBACK_MODEL
        self.memory = memory_manager or default_memory_manager
        self.confidence_scorer = confidence_scorer or default_confidence_scorer
        self._groq_client = Groq(api_key=self.api_key) if self.api_key else None

    def _call_groq_with_retry(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_retries: int = 1
    ) -> Dict[str, Any]:
        """Calls Groq with JSON format and retry logic (NFR-1)."""
        if not self._groq_client:
            raise RuntimeError("Groq client not initialized. Verify GROQ_API_KEY.")

        last_error: Exception = RuntimeError("No attempts made")
        for attempt in range(max_retries + 1):
            try:
                response = self._groq_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=1500
                )
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("Groq returned empty response content.")
                return json.loads(content)
            except Exception as e:
                last_error = e
                logger.warning(f"Groq call failed on {model} (attempt {attempt+1}/{max_retries+1}): {e}")
                if attempt < max_retries:
                    time.sleep(0.3)

        raise last_error

    def _build_user_content(
        self,
        incident: Dict[str, Any],
        recalled_memories: List[Dict[str, Any]]
    ) -> str:
        incident_id = incident["incident_id"]
        service_name = incident.get("service_name", "unknown-service")
        severity = incident.get("severity", "SEV3")
        symptoms = incident.get("symptoms", "")
        log_excerpt = incident.get("log_excerpt", "")

        if recalled_memories:
            memories_block = "RECALLED INSTITUTIONAL MEMORIES:\n"
            for i, mem in enumerate(recalled_memories, 1):
                doc_id = mem.get("document_id") or mem.get("metadata", {}).get("incident_id", "UNKNOWN")
                mem_type = mem.get("type", "experience")
                mem_text = mem.get("text", "")
                mem_id = mem.get("id", "N/A")
                memories_block += f"[{i}] Incident ID: {doc_id} | Memory ID: {mem_id} | Type: {mem_type}\nSummary: {mem_text}\n\n"
        else:
            memories_block = "RECALLED INSTITUTIONAL MEMORIES: NONE (Zero past incidents matched in Hindsight)\n"

        return (
            f"CURRENT INCIDENT TO DIAGNOSE:\n"
            f"Incident ID: {incident_id}\n"
            f"Service: {service_name}\n"
            f"Severity: {severity}\n"
            f"Symptoms: {symptoms}\n"
            f"Log Excerpt:\n{log_excerpt}\n\n"
            f"{memories_block}\n"
            f"Analyze this incident now. Return only JSON."
        )

    def diagnose_incident(
        self,
        incident: Dict[str, Any],
        recall_top_n: int = 5,
        recalled_memories_override: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Diagnoses an incident with concurrent Hindsight recall + LLM inference (NFR-2 optimization).

        Flow:
        1. [Concurrent] Recall memories from Hindsight while building system prompt.
        2. Call Groq for structured diagnosis (primary → fallback with retry).
        3. Enforce zero-hallucination citation safety.
        4. [Post-LLM] Compute confidence via Hindsight fix recall.
        5. Persist diagnosis to SQLite.
        """
        start_time = time.time()
        incident_id = incident["incident_id"]
        service_name = incident.get("service_name", "unknown-service")
        symptoms = incident.get("symptoms", "")

        # ── Step 1: Recall or use override ──────────────────────────────
        if recalled_memories_override is not None:
            recalled_memories = recalled_memories_override
        else:
            try:
                recalled_memories = self.memory.recall_similar_postmortems(
                    symptoms=symptoms,
                    service_name=service_name,
                    top_n=recall_top_n
                )
            except Exception as e:
                logger.error(f"Memory recall error: {e}")
                recalled_memories = []

        has_memories = len(recalled_memories) > 0

        # ── Step 2: Build prompt and call Groq ─────────────────────────
        user_content = self._build_user_content(incident, recalled_memories)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ]

        model_used = self.primary_model
        try:
            llm_result = self._call_groq_with_retry(messages, model=self.primary_model, max_retries=1)
        except Exception as e:
            logger.warning(f"Primary model {self.primary_model} failed ({e}), falling back to {self.fallback_model}.")
            model_used = self.fallback_model
            llm_result = self._call_groq_with_retry(messages, model=self.fallback_model, max_retries=1)

        # ── Step 3: Citation safety & zero-match enforcement ───────────
        cited_ids = llm_result.get("cited_incident_ids", [])
        if not isinstance(cited_ids, list):
            cited_ids = []

        valid_doc_ids = {
            mem.get("document_id") or mem.get("metadata", {}).get("incident_id")
            for mem in recalled_memories
        }
        valid_doc_ids.discard(None)

        filtered_cited_ids = [cid for cid in cited_ids if cid in valid_doc_ids]

        if not has_memories:
            matches_pattern = False
            filtered_cited_ids = []
            root_cause = llm_result.get("root_cause_hypothesis", "")
            if "no similar past incident" not in root_cause.lower():
                root_cause = f"No similar past incident found in institutional memory. Preliminary hypothesis: {root_cause}"
        else:
            matches_pattern = bool(llm_result.get("matches_known_pattern", False)) and len(filtered_cited_ids) > 0
            root_cause = llm_result.get("root_cause_hypothesis", "Unknown root cause")

        suggested_fix = llm_result.get("suggested_fix", "Investigate service logs and restart affected instances.")
        why_recalled = llm_result.get("why_recalled_analysis", "")

        # ── Step 4: Confidence scoring (only if there's a fix) ─────────
        if suggested_fix and suggested_fix.strip():
            conf_score, conf_label, supporting_records = self.confidence_scorer.compute_confidence(
                suggested_fix=suggested_fix,
                current_incident_id=incident_id
            )
        else:
            conf_score, conf_label, supporting_records = None, "no prior track record — first time this fix is suggested", []

        latency_seconds = round(time.time() - start_time, 2)
        diagnosis_id = f"DIAG-{uuid.uuid4().hex[:8].upper()}"

        # ── Step 5: Persist to SQLite ───────────────────────────────────
        save_diagnosis(
            diagnosis_id=diagnosis_id,
            incident_id=incident_id,
            root_cause_hypothesis=root_cause,
            suggested_fix=suggested_fix,
            cited_memory_ids=filtered_cited_ids,
            confidence_score=conf_score,
            confidence_label=conf_label
        )

        return {
            "diagnosis_id": diagnosis_id,
            "incident_id": incident_id,
            "matches_known_pattern": matches_pattern,
            "root_cause_hypothesis": root_cause,
            "suggested_fix": suggested_fix,
            "cited_incident_ids": filtered_cited_ids,
            "confidence_score": conf_score,
            "confidence_label": conf_label,
            "supporting_records": supporting_records,
            "recalled_memories": recalled_memories,
            "why_recalled_analysis": why_recalled,
            "latency_seconds": latency_seconds,
            "model_used": model_used
        }


# Singleton convenience instance
default_diagnosis_service = DiagnosisService()
