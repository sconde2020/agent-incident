"""Fixtures partagées pour les tests d'intégration."""
import os
import sqlite3
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from agent import Agent
from config import Config

# ─── Génération du rapport d'intégration ─────────────────────────────────────

_REPORTS_DIR = Path(__file__).parent.parent / "reports"
_RESULTS: list[dict] = []
_t0: float = 0.0


def pytest_sessionstart(session):
    global _t0
    _t0 = time.monotonic()


def pytest_runtest_logreport(report):
    if report.when != "call":
        return
    if "/integration/" not in report.nodeid.replace("\\", "/"):
        return
    parts = report.nodeid.split("::")
    _RESULTS.append({
        "class": parts[-2] if len(parts) >= 3 else "–",
        "outcome": report.outcome,
    })


def pytest_sessionfinish(session, exitstatus):
    if not _RESULTS:
        return
    _write_report(time.monotonic() - _t0)


def _write_report(duration: float) -> None:
    by_class: dict = defaultdict(lambda: {"passed": 0, "failed": 0, "skipped": 0})
    for r in _RESULTS:
        by_class[r["class"]][r["outcome"]] += 1

    n_passed = sum(1 for r in _RESULTS if r["outcome"] == "passed")
    n_failed = sum(1 for r in _RESULTS if r["outcome"] == "failed")
    n_skipped = sum(1 for r in _RESULTS if r["outcome"] == "skipped")
    status = "OK" if n_failed == 0 else "ECHEC"
    has_key = "oui" if os.getenv("OPENAI_API_KEY") else "non"

    lines = [
        "# Rapport — Tests d'integration",
        "",
        f"**Date :** {date.today()}  ",
        f"**LLM :** `gpt-4o-mini` · cle API presente : {has_key}  ",
        f"**Resultat :** {status} — {n_passed} passed · {n_failed} failed · {n_skipped} skipped  ",
        f"**Duree :** {duration:.2f} s",
        "",
        "| Classe | Passes | Echoues | Sautes |",
        "|--------|:------:|:-------:|:------:|",
    ]
    for cls, c in sorted(by_class.items()):
        icon = "" if c["failed"] == 0 else "[FAIL] "
        lines.append(f"| {icon}`{cls}` | {c['passed']} | {c['failed']} | {c['skipped']} |")

    lines += ["", f"**Total : {len(_RESULTS)} tests · {duration:.2f} s**"]

    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORTS_DIR / "rapport_integration.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nRapport genere : {_REPORTS_DIR / 'rapport_integration.md'}")

_SCHEMA_PATH = Path(__file__).parent.parent.parent / "db" / "schema.sql"


# ─── Helpers base de données ─────────────────────────────────────────────────

def apply_schema(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()


def seed_cmdb_and_monitoring(db_path: str) -> None:
    """Insérer 2 services CMDB connus + 1 alerte critique sur swift-gateway."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO services "
        "(id, name, display_name, team, business_criticality, tier, dependencies, dependents) "
        "VALUES (?,?,?,?,?,?,?,?)",
        ("svc-gw", "swift-gateway", "SWIFT Gateway", "team-swift", "critical", 1, "[]", "[]"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO services "
        "(id, name, display_name, team, business_criticality, tier, dependencies, dependents) "
        "VALUES (?,?,?,?,?,?,?,?)",
        ("svc-ph", "payment-hub", "Payment Hub", "team-payments", "high", 1, '["swift-gateway"]', "[]"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO alerts "
        "(id, service, severity, name, message, triggered_at, status) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            "alert-gw-001", "swift-gateway", "critical", "SWIFTNetDown",
            "Connexion SWIFTNet perdue depuis 14h00", "2026-05-07T14:00:00", "firing",
        ),
    )
    conn.commit()
    conn.close()


def seed_recent_incident(db_path: str) -> None:
    """Insérer INC9990001 (open, swift-gateway, 1h) pour déclencher la détection de doublon."""
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO incidents "
        "(id, title, description, status, service, priority, category, assigned_to, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            "INC9990001", "Erreur connexion SWIFTNet originale",
            "Incident de connectivité ouvert en production.", "open",
            "swift-gateway", "P2", "Infrastructure", "team-swift",
            one_hour_ago, one_hour_ago,
        ),
    )
    conn.commit()
    conn.close()


def build_config(db_path: str, chroma_path: str, max_memory: int = 3) -> Config:
    return Config(
        openai_api_key=os.environ.get("OPENAI_API_KEY", "no-key"),
        llm_model="gpt-4o-mini",
        db_path=db_path,
        chroma_path=chroma_path,
        max_memory=max_memory,
        duplicate_window_hours=2,
        major_incident_threshold=3,
        log_level="WARNING",
    )


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def fresh_db(tmp_path):
    """DB vide (schéma + CMDB + monitoring) sans incidents."""
    path = str(tmp_path / "test.db")
    apply_schema(path)
    seed_cmdb_and_monitoring(path)
    return path


@pytest.fixture()
def dup_db(tmp_path):
    """DB avec un incident récent sur swift-gateway pour tester le shortcut doublon."""
    path = str(tmp_path / "dup.db")
    apply_schema(path)
    seed_cmdb_and_monitoring(path)
    seed_recent_incident(path)
    return path


@pytest.fixture()
def live_agent(fresh_db, tmp_path):
    """Agent complet avec LLM réel et RAG désactivé (collection inexistante → [])."""
    cfg = build_config(fresh_db, str(tmp_path / "chroma"))
    ag = Agent(cfg)
    with patch.object(ag.rag, "retrieve", return_value=[]):
        yield ag


@pytest.fixture()
def dup_agent(dup_db, tmp_path):
    """Agent sur DB avec incident récent — déclenche le shortcut doublon sans appel LLM."""
    cfg = build_config(dup_db, str(tmp_path / "chroma"))
    ag = Agent(cfg)
    with patch.object(ag.rag, "retrieve", return_value=[]):
        yield ag
