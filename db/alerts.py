import json
import logging
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)


class MonitoringDB:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_active_alerts(self, service: str) -> list[dict]:
        """Alertes en état 'firing' pour un service donné, triées par sévérité."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM alerts
                WHERE service = ? AND status = 'firing'
                ORDER BY
                    CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
                    triggered_at DESC
                """,
                (service,),
            ).fetchall()

        alerts = []
        for row in rows:
            a = dict(row)
            if a.get("labels"):
                try:
                    a["labels"] = json.loads(a["labels"])
                except (json.JSONDecodeError, TypeError):
                    pass
            alerts.append(a)

        logger.debug("monitoring.alerts_fetched service=%s count=%d", service, len(alerts))
        return alerts

    def get_latest_metrics(self, service: str) -> Optional[dict]:
        """Dernières métriques connues pour un service."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM metrics WHERE service = ? ORDER BY timestamp DESC LIMIT 1",
                (service,),
            ).fetchone()

        if not row:
            return None

        m = dict(row)
        if m.get("custom_metrics"):
            try:
                m["custom_metrics"] = json.loads(m["custom_metrics"])
            except (json.JSONDecodeError, TypeError):
                pass
        return m
