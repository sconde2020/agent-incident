import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Coût en USD par token (prompt, completion) selon le modèle
_TOKEN_COST: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15e-6, 0.60e-6),
    "gpt-4o": (5.00e-6, 15.00e-6),
    "gpt-4-turbo": (10.00e-6, 30.00e-6),
    "gpt-4": (30.00e-6, 60.00e-6),
}
_DEFAULT_COST = (1.00e-6, 3.00e-6)


@dataclass
class RequestRecord:
    incident_id: str
    duration_ms: int
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    error: Optional[str]
    rag_ms: int = 0
    llm_ms: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class RequestMonitor:
    """Enregistre chaque requête de qualification et agrège les KPIs."""

    def __init__(self, model: str = "gpt-4o-mini"):
        self._model = model
        self._records: list[RequestRecord] = []
        self._lock = threading.Lock()

    def record(
        self,
        incident_id: str,
        duration_ms: int,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        error: Optional[str] = None,
        rag_ms: int = 0,
        llm_ms: int = 0,
    ) -> None:
        cost_in, cost_out = _TOKEN_COST.get(self._model, _DEFAULT_COST)
        cost = prompt_tokens * cost_in + completion_tokens * cost_out
        rec = RequestRecord(
            incident_id=incident_id,
            duration_ms=duration_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated_cost_usd=round(cost, 8),
            error=error,
            rag_ms=rag_ms,
            llm_ms=llm_ms,
        )
        with self._lock:
            self._records.append(rec)
        logger.info(
            "monitor.record incident_id=%s duration_ms=%d tokens=%d+%d cost_usd=%.6f error=%s",
            incident_id, duration_ms, prompt_tokens, completion_tokens, cost, error,
        )

    def get_stats(self) -> dict:
        with self._lock:
            records = list(self._records)
        total = len(records)
        errors = sum(1 for r in records if r.error)
        total_ms = sum(r.duration_ms for r in records)
        prompt = sum(r.prompt_tokens for r in records)
        completion = sum(r.completion_tokens for r in records)
        cost = sum(r.estimated_cost_usd for r in records)
        avg_rag = sum(r.rag_ms for r in records) // total if total else 0
        avg_llm = sum(r.llm_ms for r in records) // total if total else 0
        return {
            "qualifications_total": total,
            "qualifications_success": total - errors,
            "errors_total": errors,
            "avg_latency_ms": total_ms // total if total else 0,
            "latency_breakdown": {"avg_rag_ms": avg_rag, "avg_llm_ms": avg_llm},
            "tokens": {
                "prompt_total": prompt,
                "completion_total": completion,
                "total": prompt + completion,
            },
            "estimated_cost_usd": round(cost, 6),
            "model": self._model,
        }
