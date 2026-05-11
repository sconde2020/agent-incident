import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

TOOL_DEFINITION = {
    "name": "check_duplicate",
    "description": "Vérifie si un incident similaire est déjà ouvert sur le même service dans la fenêtre de temps configurée.",
    "input_schema": {
        "type": "object",
        "properties": {
            "service": {"type": "string"},
            "title": {"type": "string"},
            "window_hours": {"type": "integer", "default": 2},
        },
        "required": ["service", "title"],
    },
}


class DetectDuplicate:
    def __init__(self, incident_db, window_hours: int = 2, search_limit: int = 10):
        self.db = incident_db
        self.window_hours = window_hours
        self.search_limit = search_limit

    def execute(self, service: str, title: str, exclude_id: Optional[str] = None) -> dict:
        """
        Détecter un doublon : incident ouvert sur le même service
        créé dans la fenêtre temporelle configurée.
        """
        logger.info("tools.detect_duplicate service=%s window_hours=%d", service, self.window_hours)
        recent = self.db.search_similar(service=service, title=title, limit=self.search_limit, statuses=("open", "in_progress"))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.window_hours)
        candidates = self._filter_candidates(recent, cutoff, exclude_id)
        is_duplicate = len(candidates) > 0
        duplicate_of = candidates[0]["id"] if is_duplicate else None
        if is_duplicate:
            logger.info("tools.detect_duplicate.found duplicate_of=%s", duplicate_of)
        return {
            "is_duplicate": is_duplicate,
            "duplicate_of": duplicate_of,
            "candidates": [c["id"] for c in candidates],
        }

    def _filter_candidates(
        self, recent: list, cutoff: datetime, exclude_id: Optional[str] = None
    ) -> list:
        candidates = []
        for inc in recent:
            if exclude_id and inc.get("id") == exclude_id:
                continue
            created_str = inc.get("created_at", "")
            try:
                # Normaliser les formats ISO-8601 avec ou sans timezone
                created_str = created_str.replace("Z", "+00:00")
                inc_dt = datetime.fromisoformat(created_str)
                if inc_dt.tzinfo is None:
                    inc_dt = inc_dt.replace(tzinfo=timezone.utc)
                if inc_dt >= cutoff:
                    candidates.append(inc)
            except (ValueError, AttributeError):
                # Date malformée : on ignore prudemment plutôt que de crasher
                logger.warning("detect_duplicate.invalid_date incident_id=%s", inc.get("id"))
        return candidates
