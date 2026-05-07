import json
import logging
import sqlite3
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class AuditLogger:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def log(
        self,
        incident_id: str,
        action: str,
        result: Optional[dict] = None,
        duration_ms: int = 0,
        model: str = "",
        confidence: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        """Enregistrer une action de l'agent dans audit_log.
        L'audit ne doit jamais bloquer le traitement principal.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                """
                INSERT INTO audit_log
                (incident_id, action, result, duration_ms, model, confidence, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident_id, action,
                    json.dumps(result) if result else None,
                    duration_ms, model, confidence, error,
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error("audit.write_failed error=%s", exc)
