"""Fixtures et génération du rapport qualité LLM-as-Judge."""
import io
import logging
import os
import sys
from pathlib import Path

import pytest

from agent import Agent
from config import Config
from db.init_db import init_db

from .judge import (
    JUDGE_BACKEND,
    JUDGE_MODEL,
    QUESTIONS,
    SCORE_GLOBAL_CIBLE,
    SCORE_MIN_PAR_QUESTION,
)

if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger(__name__)

_RAPPORT_FILE = Path(__file__).parent.parent / "reports" / "rapport_qualite.md"

# ─── Initialisation DB et RAG ─────────────────────────────────────────────────

def _ensure_db_initialized(db_path: str, data_dir: str) -> None:
    if not Path(db_path).exists():
        logger.info("init_db creating %s", db_path)
        init_db(db_path=db_path, data_dir=data_dir)


def _ensure_rag_initialized(config: Config) -> None:
    try:
        import chromadb
        client = chromadb.PersistentClient(path=config.chroma_path)
        existing = [c.name for c in client.list_collections()]
        if config.chroma_collection_name in existing:
            return
    except Exception:
        pass
    logger.info("rag.ingest starting chroma_path=%s", config.chroma_path)
    from rag.ingest import ingest_docs
    ingest_docs(
        docs_dir=config.docs_path,
        chroma_path=config.chroma_path,
        embedding_model=config.embedding_model,
        collection_name=config.chroma_collection_name,
        batch_size=config.rag_ingest_batch_size,
    )

# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def real_config() -> Config:
    cfg = Config(
        openai_api_key=os.environ.get("OPENAI_API_KEY", "no-key"),
        llm_model="gpt-4o-mini",
        llm_temperature=0.0,
        log_level="WARNING",
    )
    _ensure_db_initialized(cfg.db_path, cfg.data_path)
    _ensure_rag_initialized(cfg)
    return cfg


@pytest.fixture(scope="module")
def real_agent(real_config: Config) -> Agent:
    return Agent(real_config)


@pytest.fixture(scope="module")
def score_collector() -> list[dict]:
    """Accumulateur de scores LLM-as-Judge partagé entre tous les tests du module."""
    return []


@pytest.fixture(scope="module", autouse=True)
def generate_report_at_end(real_config: Config, score_collector: list[dict]):
    yield
    if score_collector:
        _RAPPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        _write_report(score_collector, real_config)

# ─── Génération du rapport ────────────────────────────────────────────────────

_ANALYSES: dict[str, str] = {
    "factuelle": (
        "L'agent a du mal à retrouver une information factuelle directe. "
        "Cause probable : corpus RAG non indexé pour ce service ou document peu pertinent retourné."
    ),
    "complexe": (
        "La synthèse multi-dimensions est difficile : l'agent se concentre sur un seul vecteur d'impact "
        "et manque la relation causale entre les deux services."
    ),
    "ambigue": (
        "Face à une description vague, l'agent sur-qualifie ou sous-qualifie. "
        "Une règle explicite dans le SYSTEM_PROMPT pour fixer un seuil de confidence minimal aiderait."
    ),
    "hors_sujet": (
        "L'agent essaie de qualifier un incident hors domaine. "
        "Le calibrage du confidence_score (< 0.3 pour hors-domaine) n'est pas appliqué."
    ),
    "securite": (
        "L'incident de sécurité n'est pas correctement catégorisé. "
        "Vérifier que runbook_security_incident.md est bien indexé dans ChromaDB."
    ),
    "piege": (
        "L'agent abonde dans la fausse prémisse P1 déclarée par le reporter. "
        "La pression émotionnelle du ticket influence le LLM malgré la règle anti-escalade."
    ),
    "format": (
        "La resolution_hint ne référence pas le post-mortem pourtant indexé dans le RAG. "
        "La requête RAG manque de termes discriminants."
    ),
    "memoire": (
        "La mémoire de session n'est pas exploitée pour signaler le pattern récurrent. "
        "Le prompt mémoire devrait être plus directif."
    ),
    "multi_tools": (
        "Le multi-tools nécessite CMDB + RAG cohérents. "
        "Si la FAQ paiements SWIFT n'est pas retournée par le RAG, l'agent manque les détails BIC."
    ),
    "bord": (
        "Service hors CMDB + domaine adjacent mal reconnu. "
        "L'agent donne un confidence_score trop élevé ou trop bas."
    ),
}

_IMPROVEMENTS: dict[str, str] = {
    "factuelle": (
        "Vérifier que le runbook est bien indexé dans ChromaDB (relancer `python main.py init`) "
        "et que la requête RAG contient suffisamment de termes discriminants."
    ),
    "complexe": (
        "Enrichir le SYSTEM_PROMPT : 'Pour les incidents multi-services, analyse les dépendances CMDB "
        "et identifie le service racine.' Passer `cmdb.dependencies` dans le contexte LLM."
    ),
    "ambigue": (
        "Ajouter dans SYSTEM_PROMPT : 'Si impact non chiffré et service inconnu, assigner P3 maximum "
        "et fixer confidence ≤ 0.4.'"
    ),
    "hors_sujet": (
        "Ajouter une règle hors-domaine : 'Si le ticket ne mentionne aucun terme bancaire SWIFT, "
        "assigner P4 et confidence ≤ 0.15.'"
    ),
    "securite": (
        "Vérifier que runbook_security_incident.md est indexé. Relancer `python main.py init`."
    ),
    "piege": (
        "Renforcer la PROCÉDURE OBLIGATOIRE dans le SYSTEM_PROMPT : compter paiements et contreparties "
        "avant d'assigner la priorité."
    ),
    "format": (
        "Améliorer la construction de la requête RAG dans `agent._gather_rag()` : "
        "inclure les codes d'erreur extraits de la description."
    ),
    "memoire": (
        "Renforcer le CLASSIFY_PROMPT section mémoire : signaler la récurrence dans resolution_hint "
        "si un incident similaire est déjà en mémoire."
    ),
    "multi_tools": (
        "Augmenter `rag_top_k` à 6 pour les questions factuelles avec corpus dense. "
        "Ajouter `rag_docs_used` dans les logs pour diagnostiquer les documents non pertinents."
    ),
    "bord": (
        "Ajouter dans SYSTEM_PROMPT : 'Si le service est absent de la CMDB mais la description contient "
        "des termes SWIFT/bancaires, fixer confidence entre 0.3 et 0.5.'"
    ),
}


def _build_score_table(scores: list[dict]) -> list[str]:
    lines = [
        "## Tableau des scores", "",
        "| ID | Catégorie | Pertinence | Fidélité | Cohérence | **Moyenne** |",
        "|----|-----------|:----------:|:--------:|:---------:|:-----------:|",
    ]
    for e in scores:
        flag = "" if e["avg"] >= SCORE_MIN_PAR_QUESTION else "⚠️ "
        lines.append(
            f"| {e['id']} | {e['categorie']} "
            f"| {e['pertinence']} | {e['fidelite']} | {e['coherence']} "
            f"| {flag}**{e['avg']:.2f}** |"
        )
    return lines


def _build_justifications(scores: list[dict]) -> list[str]:
    lines = ["## Justifications du juge", ""]
    for e in scores:
        lines.append(f"**{e['id']} ({e['categorie']})** — *{e['justification']}*  ")
        lines.append("")
    return lines


def _build_worst_section(worst: dict) -> list[str]:
    cat = worst["categorie"]
    default = f"Revoir le SYSTEM_PROMPT pour mieux couvrir les incidents de type '{cat}'."
    return [
        "---", "",
        "## Analyse de la pire question", "",
        f"**{worst['id']} — {worst['categorie']} (score : {worst['avg']:.2f})**", "",
        f"> {next(q['question'] for q in QUESTIONS if q['id'] == worst['id'])}", "",
        f"**Scores :** P={worst['pertinence']} F={worst['fidelite']} C={worst['coherence']}", "",
        f"**Juge :** {worst['justification']}", "",
        "### Analyse", "", _ANALYSES.get(cat, default), "",
        "### Piste d'amélioration", "", _IMPROVEMENTS.get(cat, default), "",
    ]


def _build_footer(global_avg: float, count: int) -> list[str]:
    status = "✅ Objectif atteint" if global_avg >= SCORE_GLOBAL_CIBLE else "⚠️ Objectif non atteint"
    return [
        "---", "",
        "## Score global", "",
        f"**{global_avg:.2f} / 5.0** ({count} questions évaluées)  ", "",
        f"{status} (cible : ≥ {SCORE_GLOBAL_CIBLE})",
    ]


def _write_report(scores: list[dict], config: Config) -> None:
    if not scores:
        return
    global_avg = round(sum(e["avg"] for e in scores) / len(scores), 2)
    worst = min(scores, key=lambda e: e["avg"])
    from datetime import date
    header = [
        "# Rapport de qualité — LLM-as-Judge", "",
        f"**Date :** {date.today()}  ",
        f"**Agent :** `{config.llm_model}` (OpenAI)  ",
        f"**Juge :** `{JUDGE_MODEL}` ({JUDGE_BACKEND})  ",
        f"**Seuil par question :** ≥ {SCORE_MIN_PAR_QUESTION}  ",
        f"**Cible globale :** ≥ {SCORE_GLOBAL_CIBLE}  ",
        "", "---", "",
    ]
    global_summary = ["", f"**Score global moyen : {global_avg:.2f} / 5.0**", "", "---", ""]
    lines = (
        header
        + _build_score_table(scores)
        + global_summary
        + _build_justifications(scores)
        + _build_worst_section(worst)
        + _build_footer(global_avg, len(scores))
    )
    _RAPPORT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nRapport genere : {_RAPPORT_FILE}")
