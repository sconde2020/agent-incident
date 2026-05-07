import json
import logging
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)


class CMDB:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_service(self, service_name: str) -> Optional[dict]:
        """Retourner les informations CMDB d'un service."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM services WHERE name = ?", (service_name,)
            ).fetchone()

        if not row:
            logger.warning("cmdb.service_not_found service=%s", service_name)
            return None

        svc = dict(row)
        for field in ("dependencies", "dependents"):
            if svc.get(field):
                try:
                    svc[field] = json.loads(svc[field])
                except (json.JSONDecodeError, TypeError):
                    svc[field] = []
        return svc

    def get_team(self, team_id: str) -> Optional[dict]:
        """Retourner les informations d'une équipe."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM teams WHERE id = ?", (team_id,)
            ).fetchone()

        if not row:
            return None

        team = dict(row)
        if team.get("services"):
            try:
                team["services"] = json.loads(team["services"])
            except (json.JSONDecodeError, TypeError):
                team["services"] = []
        return team

    def list_known_services(self) -> list[str]:
        """Liste des noms de services connus dans la CMDB."""
        with self._conn() as conn:
            rows = conn.execute("SELECT name FROM services").fetchall()
        return [r["name"] for r in rows]

    def list_known_teams(self) -> list[str]:
        """Liste des identifiants d'équipes connus."""
        with self._conn() as conn:
            rows = conn.execute("SELECT id FROM teams").fetchall()
        return [r["id"] for r in rows]
