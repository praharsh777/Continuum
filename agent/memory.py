"""
Continuum Memory Layer (Hindsight Integration)
Implements Phase 2: retain, recall, reflect, and bank reset operations.
Authoritative against official Hindsight API & hindsight-client SDK.
"""

import logging
import os
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from hindsight_client import Hindsight

load_dotenv()
logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = os.getenv("HINDSIGHT_BASE_URL", "https://api.hindsight.vectorize.io")
DEFAULT_BANK_ID = os.getenv("HINDSIGHT_BANK_ID", "continuum-demo")


class HindsightMemoryManager:
    """Manages persistent institutional memory interactions via Hindsight Cloud."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        bank_id: Optional[str] = None,
        timeout: float = 30.0
    ):
        self.api_key = api_key or os.getenv("HINDSIGHT_API_KEY")
        self.base_url = base_url or DEFAULT_BASE_URL
        self.bank_id = bank_id or DEFAULT_BANK_ID
        self.timeout = timeout

        if not self.api_key:
            logger.warning("HINDSIGHT_API_KEY is not set. Memory operations will fail if unauthenticated.")

    def _get_client(self) -> Hindsight:
        if not hasattr(self, "_cached_client") or self._cached_client is None:
            self._cached_client = Hindsight(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout
            )
        return self._cached_client

    def retain_postmortem(
        self,
        incident_id: str,
        service_name: str,
        narrative_summary: str,
        outcome: str = "RESOLVED",
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Retains a resolved incident postmortem into Hindsight Cloud.
        Binds document_id to incident_id so recall results can be traced back.
        """
        client = self._get_client()
        meta = {
            "incident_id": incident_id,
            "service_name": service_name,
            "outcome": outcome,
            "type": "postmortem"
        }
        if metadata:
            meta.update(metadata)

        content = (
            f"Incident Postmortem for {incident_id} [{service_name}]:\n"
            f"{narrative_summary}\n"
            f"Outcome: {outcome}"
        )

        try:
            client = self._get_client()
            response = client.retain(
                bank_id=self.bank_id,
                content=content,
                context=f"incident_postmortem_{service_name}",
                document_id=incident_id,
                metadata=meta,
                retain_async=False
            )
            op_id = getattr(response, "operation_id", None)
            return {
                "success": getattr(response, "success", True),
                "operation_id": op_id,
                "bank_id": getattr(response, "bank_id", self.bank_id),
                "items_count": getattr(response, "items_count", 1)
            }
        except Exception as e:
            logger.error(f"Failed to retain postmortem in Hindsight: {e}")
            raise

    def recall_similar_postmortems(
        self,
        symptoms: str,
        service_name: Optional[str] = None,
        top_n: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Recalls similar incidents/postmortems from Hindsight using semantic TEMPR search.
        Top N results are returned (bounded by user slider or default 5).
        """
        query_parts = []
        if service_name:
            query_parts.append(f"Service: {service_name}")
        query_parts.append(f"Symptoms: {symptoms}")
        query = " | ".join(query_parts)

        client = self._get_client()
        response = client.recall(
            bank_id=self.bank_id,
            query=query,
            budget="low",
            max_tokens=2048,
            min_scores={"reranker": 0.3}
        )
        
        raw_results = getattr(response, "results", []) or []
        parsed_results: List[Dict[str, Any]] = []

        for r in raw_results:
            parsed_results.append({
                "id": getattr(r, "id", None),
                "text": getattr(r, "text", ""),
                "type": getattr(r, "type", "experience"),
                "document_id": getattr(r, "document_id", None),
                "metadata": getattr(r, "metadata", {}) or {},
                "scores": getattr(r, "scores", None),
                "context": getattr(r, "context", None)
            })

        return parsed_results[:top_n]

    def recall_similar_fixes(
        self,
        suggested_fix: str,
        top_n: int = 10,
        min_reranker_score: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        FR-5: Query Hindsight recall against the candidate fix-pattern text itself.
        Used to identify historical incidents that applied this or a similar fix.
        """
        query = f"Resolution fix applied: {suggested_fix}"

        client = self._get_client()
        response = client.recall(
            bank_id=self.bank_id,
            query=query,
            budget="low",
            max_tokens=2048,
            min_scores={"reranker": min_reranker_score}
        )
        raw_results = getattr(response, "results", []) or []
        parsed: List[Dict[str, Any]] = []
        for r in raw_results:
            parsed.append({
                "id": getattr(r, "id", None),
                "text": getattr(r, "text", ""),
                "document_id": getattr(r, "document_id", None),
                "metadata": getattr(r, "metadata", {}) or {},
                "scores": getattr(r, "scores", None)
            })
        return parsed[:top_n]

    def reflect(self, query: str, context: Optional[str] = None) -> str:
        """Calls Hindsight reflect operation to generate disposition-aware synthesis."""
        client = self._get_client()
        response = client.reflect(
            bank_id=self.bank_id,
            query=query,
            context=context,
            budget="low"
        )
        return getattr(response, "text", "")

    def reset_bank(self) -> bool:
        """
        Resets the demo memory bank using DELETE /banks/{bank_id} and recreating it.
        Ensures a clean state for testing and live demonstration rehearsals.
        """
        client = self._get_client()
        try:
            logger.info(f"Deleting Hindsight bank: {self.bank_id}")
            client.delete_bank(bank_id=self.bank_id)
        except Exception as e:
            logger.warning(f"Bank delete returned: {e} (may not exist yet)")

        try:
            logger.info(f"Recreating Hindsight bank: {self.bank_id}")
            client.create_bank(
                bank_id=self.bank_id,
                name="Continuum Demo Bank",
                mission="Institutional memory bank for Continuum incident response agent."
            )
            return True
        except Exception as e:
            logger.error(f"Failed to create Hindsight bank: {e}")
            return False


# Singleton convenience instance
default_memory_manager = HindsightMemoryManager()
