import logging
import random
import sqlite3
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class IncidentDB:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get(self, incident_id: str) -> Optional[dict]:
        """Retourner un incident avec son historique."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM incidents WHERE id = ?", (incident_id,)
            ).fetchone()
        if not row:
            return None

        inc = dict(row)
        with self._conn() as conn:
            history_rows = conn.execute(
                "SELECT at, action, by FROM incident_history WHERE incident_id = ? ORDER BY at",
                (incident_id,),
            ).fetchall()
        inc["history"] = [dict(h) for h in history_rows]
        return inc

    def search_similar(
        self,
        service: str,
        title: str = "",
        limit: int = 5,
        statuses: tuple = ("open", "in_progress", "resolved"),
    ) -> list[dict]:
        """
        Recherche d'incidents récents pour un service donné.
        Le tri par date décroissante favorise les incidents récents pour la détection de doublons.
        """
        status_placeholders = ",".join("?" * len(statuses))
        query = f"""
            SELECT id, title, service, status, priority, category, assigned_to, created_at
            FROM incidents
            WHERE service = ? AND status IN ({status_placeholders})
            ORDER BY created_at DESC
            LIMIT ?
        """
        with self._conn() as conn:
            rows = conn.execute(query, (service, *statuses, limit)).fetchall()

        logger.debug("incidents.search_similar service=%s found=%d", service, len(rows))
        return [dict(r) for r in rows]

    def update_qualification(self, incident_id: str, qualification: dict) -> None:
        """Persister la qualification produite par l'agent."""
        now = datetime.now(timezone.utc).isoformat()
        action = (
            f"Qualifié : {qualification.get('priority')} | "
            f"{qualification.get('category')} → {qualification.get('assigned_to')}"
        )
        with self._conn() as conn:
            self._execute_qualification_update(conn, incident_id, qualification, now)
            conn.execute(
                "INSERT INTO incident_history (incident_id, at, action, by) VALUES (?,?,?,?)",
                (incident_id, now, action, "agent-qualification"),
            )
            conn.commit()
        logger.info("incidents.qualification_saved incident_id=%s", incident_id)

    def _execute_qualification_update(
        self, conn: sqlite3.Connection, incident_id: str, qualification: dict, now: str
    ) -> None:
        conn.execute(
            """
            UPDATE incidents SET
                priority = ?, category = ?, subcategory = ?, assigned_to = ?,
                confidence_score = ?, is_duplicate = ?, duplicate_of = ?,
                is_major_incident = ?, qualification_failed = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                qualification.get("priority"), qualification.get("category"),
                qualification.get("subcategory"), qualification.get("assigned_to"),
                qualification.get("confidence_score"),
                1 if qualification.get("is_duplicate") else 0,
                qualification.get("duplicate_of"),
                1 if qualification.get("is_major_incident") else 0,
                1 if qualification.get("qualification_failed") else 0,
                now, incident_id,
            ),
        )

    def create(self, incident: dict) -> dict:
        """Insérer un nouvel incident brut en base et retourner la ligne créée."""
        now = datetime.now(timezone.utc).isoformat()
        inc_id = incident.get("id") or f"INC{random.randint(1000000, 9999999)}"
        created_at = incident.get("created_at") or now
        with self._conn() as conn:
            self._insert_incident_row(conn, inc_id, incident, created_at, now)
            conn.execute(
                "INSERT INTO incident_history (incident_id, at, action, by) VALUES (?,?,?,?)",
                (inc_id, now, "Incident créé via API", "api"),
            )
            conn.commit()
        logger.info("incidents.created incident_id=%s service=%s", inc_id, incident.get("service"))
        return {**incident, "id": inc_id, "created_at": created_at, "updated_at": now}

    def _insert_incident_row(
        self, conn: sqlite3.Connection, inc_id: str, incident: dict, created_at: str, now: str
    ) -> None:
        conn.execute(
            """
            INSERT INTO incidents
                (id, title, description, status, priority, category, subcategory,
                 service, reported_by, assigned_to, created_at, updated_at, sla_breach_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                inc_id, incident["title"], incident.get("description"),
                incident.get("status", "open"), incident.get("priority"),
                incident.get("category"), incident.get("subcategory"),
                incident["service"], incident.get("reported_by"),
                incident.get("assigned_to"), created_at, now,
                incident.get("sla_breach_at"),
            ),
        )
