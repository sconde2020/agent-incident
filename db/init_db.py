import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def init_db(db_path: str = "incidents.db", data_dir: str = "data/") -> None:
    """Créer le schéma SQLite et importer les données mock."""
    logger.info("init_db.start db_path=%s", db_path)

    schema_path = Path(__file__).parent / "schema.sql"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        conn.commit()
        logger.info("init_db.schema_applied")

        _load_incidents(conn, Path(data_dir) / "mock_incidents.json")
        _load_monitoring(conn, Path(data_dir) / "mock_monitoring.json")
        _load_cmdb(conn, Path(data_dir) / "mock_cmdb.json")

        conn.commit()
        logger.info("init_db.done")
    finally:
        conn.close()


def _load_incidents(conn: sqlite3.Connection, path: Path) -> None:
    if not path.exists():
        logger.warning("init_db.mock_not_found path=%s", path)
        return

    incidents = json.loads(path.read_text(encoding="utf-8"))
    now = datetime.utcnow().isoformat()

    for inc in incidents:
        conn.execute(
            """
            INSERT OR IGNORE INTO incidents
            (id, title, description, status, priority, category, subcategory,
             service, reported_by, assigned_to, created_at, updated_at,
             resolved_at, closed_at, resolution, sla_breach_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                inc.get("id"), inc.get("title"), inc.get("description"),
                inc.get("status", "open"), inc.get("priority"),
                inc.get("category"), inc.get("subcategory"),
                inc.get("service"), inc.get("reported_by"), inc.get("assigned_to"),
                inc.get("created_at", now), inc.get("updated_at", now),
                inc.get("resolved_at"), inc.get("closed_at"),
                inc.get("resolution"), inc.get("sla_breach_at"),
            ),
        )
        for h in inc.get("history", []):
            conn.execute(
                "INSERT OR IGNORE INTO incident_history (incident_id, at, action, by) VALUES (?,?,?,?)",
                (inc["id"], h["at"], h["action"], h["by"]),
            )

    logger.info("init_db.incidents_loaded count=%d", len(incidents))


def _insert_alert(conn: sqlite3.Connection, alert: dict) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO alerts
        (id, service, severity, name, message, triggered_at, status, runbook_url, labels)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            alert["id"], alert["service"], alert["severity"], alert["name"],
            alert["message"], alert["triggered_at"], alert["status"],
            alert.get("runbook_url"),
            json.dumps(alert["labels"]) if alert.get("labels") else None,
        ),
    )


def _insert_metric(conn: sqlite3.Connection, metric: dict) -> None:
    conn.execute(
        """
        INSERT INTO metrics
        (service, timestamp, cpu_percent, memory_percent, error_rate_percent,
         p50_latency_ms, p99_latency_ms, requests_per_second, custom_metrics)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            metric["service"], metric["timestamp"],
            metric.get("cpu_percent"), metric.get("memory_percent"),
            metric.get("error_rate_percent"), metric.get("p50_latency_ms"),
            metric.get("p99_latency_ms"), metric.get("requests_per_second"),
            json.dumps(metric["custom_metrics"]) if metric.get("custom_metrics") else None,
        ),
    )


def _load_monitoring(conn: sqlite3.Connection, path: Path) -> None:
    if not path.exists():
        logger.warning("init_db.mock_not_found path=%s", path)
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    for alert in data.get("alerts", []):
        _insert_alert(conn, alert)
    for metric in data.get("metrics", []):
        _insert_metric(conn, metric)
    logger.info(
        "init_db.monitoring_loaded alerts=%d metrics=%d",
        len(data.get("alerts", [])), len(data.get("metrics", [])),
    )


def _insert_service(conn: sqlite3.Connection, svc: dict) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO services
        (id, name, display_name, description, type, language, team, owner,
         business_criticality, sla_target_availability, tier, dependencies, dependents)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            svc["id"], svc["name"], svc.get("display_name"), svc.get("description"),
            svc.get("type"), svc.get("language"), svc["team"], svc.get("owner"),
            svc["business_criticality"], svc.get("sla_target_availability"), svc["tier"],
            json.dumps(svc.get("dependencies", [])), json.dumps(svc.get("dependents", [])),
        ),
    )


def _insert_team(conn: sqlite3.Connection, team: dict) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO teams (id, name, slack_channel, oncall_email, services) VALUES (?,?,?,?,?)",
        (team["id"], team["name"], team.get("slack_channel", ""), team.get("oncall_email", ""),
         json.dumps(team.get("services", []))),
    )


def _load_cmdb(conn: sqlite3.Connection, path: Path) -> None:
    if not path.exists():
        logger.warning("init_db.mock_not_found path=%s", path)
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    for svc in data.get("services", []):
        _insert_service(conn, svc)
    for team in data.get("teams", []):
        _insert_team(conn, team)
    logger.info(
        "init_db.cmdb_loaded services=%d teams=%d",
        len(data.get("services", [])), len(data.get("teams", [])),
    )
