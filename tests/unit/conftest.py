import time
from collections import defaultdict
from datetime import date
from pathlib import Path

_REPORTS_DIR = Path(__file__).parent.parent / "reports"
_RESULTS: list[dict] = []
_t0: float = 0.0


def pytest_sessionstart(session):
    global _t0
    _t0 = time.monotonic()


def pytest_runtest_logreport(report):
    if report.when != "call":
        return
    if "/unit/" not in report.nodeid.replace("\\", "/"):
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

    lines = [
        "# Rapport — Tests unitaires",
        "",
        f"**Date :** {date.today()}  ",
        f"**Resultat :** {status} — {n_passed} passed · {n_failed} failed · {n_skipped} skipped  ",
        f"**Duree :** {duration:.2f} s",
        "",
        "| Classe | Passes | Echoues | Sautes |",
        "|--------|:------:|:-------:|:------:|",
    ]
    for cls, c in sorted(by_class.items()):
        icon = "" if c["failed"] == 0 else "[FAIL]"
        lines.append(f"| {icon}`{cls}` | {c['passed']} | {c['failed']} | {c['skipped']} |")

    lines += ["", f"**Total : {len(_RESULTS)} tests**"]

    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORTS_DIR / "rapport_unitaires.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nRapport genere : {_REPORTS_DIR / 'rapport_unitaires.md'}")
