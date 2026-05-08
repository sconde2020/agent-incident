"""
Exercice 3 — LLM-as-Judge : évaluation de la qualité des qualifications.

Pipeline :
  1. Charge tests/questions.json (11 questions couvrant 10 catégories).
  2. Appelle l'agent RÉEL (gpt-4o-mini, DB SQLite + RAG ChromaDB réels, sans mock).
  3. Appelle le JUGE (gpt-4o via OpenAI)
     avec la réponse + les éléments factuels.
  4. Parse le JSON du juge et calcule un score moyen par question.
  5. Assert score_moyen_question >= 3.0.
  6. Génère tests/rapport_qualite.md à la fin de la session.

Lancer : pytest tests/test_qualite.py -v -s
"""
import io
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import pytest

# Force UTF-8 sur la sortie console (Windows cp1252 / cp850 par défaut)
if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from agent import Agent
from config import Config
from db.init_db import init_db
from db.models import IncidentIn
from memory.store import MemoryEntry

logger = logging.getLogger(__name__)

# ─── Seuils ────────────────────────────────────────────────────────────────

SCORE_MIN_PAR_QUESTION = 3.0   # minimum acceptable par question
SCORE_GLOBAL_CIBLE = 3.5       # objectif global de la session

# ─── Chemins ───────────────────────────────────────────────────────────────

_ROOT = Path(__file__).parent.parent
_QUESTIONS_FILE = Path(__file__).parent / "questions.json"
_RAPPORT_FILE = Path(__file__).parent / "rapport_qualite.md"

# ─── Chargement des questions ───────────────────────────────────────────────

with open(_QUESTIONS_FILE, encoding="utf-8") as _f:
    QUESTIONS = json.load(_f)

# ─── Collecteur de scores (module-level, rempli au fil des tests) ───────────

_SCORES: list[dict] = []

# ─── Prompt du juge ─────────────────────────────────────────────────────────

_JUDGE_SYSTEM = """Tu es un évaluateur expert en qualification d'incidents bancaires SWIFT.
Tu notes la réponse d'un système de qualification automatique sur trois critères.
Tu es STRICT, IMPARTIAL et tu pénalises toute imprécision.
Ne sois PAS indulgent : une erreur de priorité coûte au moins 1 point."""

_JUDGE_TEMPLATE = """INCIDENT SOUMIS :
{incident}

RÉPONSE DU SYSTÈME DE QUALIFICATION :
{response}

ÉLÉMENTS FACTUELS DE RÉFÉRENCE
(utilise UNIQUEMENT ces faits pour évaluer la fidélité — ne te fie pas à tes propres connaissances) :
{elements_factuels}

CONTEXTE MÉMOIRE DE SESSION (tours précédents) :
{memory_context}

────────────────────────────────────────────────────────────────────
CRITÈRES D'ÉVALUATION — note chaque critère de 1 à 5 :

PERTINENCE (la qualification cible-t-elle correctement l'incident ?)
  5 = priorité, catégorie, équipe et sous-catégorie toutes correctes
  4 = priorité et équipe correctes, sous-catégorie mineure erreur
  3 = l'essentiel est correct mais 1 élément important est manqué
  2 = plusieurs éléments incorrects
  1 = qualification hors sujet ou priorité clairement incorrecte

FIDÉLITÉ (les faits dans la réponse sont-ils tous vérifiables ?)
  5 = tous les faits correspondent aux éléments de référence, aucun runbook inventé
  4 = quelques imprécisions mineures, aucune fabrication
  3 = une imprécision notable ou 1 fait incorrect
  2 = plusieurs faits erronés ou runbook inventé
  1 = hallucinations graves ou faits contradictoires

COHÉRENCE (la sortie JSON est-elle logiquement cohérente ?)
  5 = toutes les parties sont cohérentes (priorité ↔ description, équipe ↔ service)
  4 = très cohérent, légère incohérence mineure
  3 = quelques incohérences notables
  2 = incohérences importantes
  1 = output contradictoire ou incompréhensible

RÈGLES DE PÉNALISATION :
- Erreur de priorité d'1 niveau : -1 point en pertinence minimum.
- Runbook suggéré absent des éléments de référence : -1 point en fidélité.
- confidence_score < 0.3 pour un incident hors domaine SWIFT : COMPORTEMENT ATTENDU, ne pas pénaliser.
- confidence_score < 0.3 pour un incident clairement dans le domaine SWIFT : pénaliser la pertinence.
- Un incident auto-qualifié P1 par le reporter mais réellement P3 : l'agent doit résister → ne pas pénaliser si l'agent corrige.

Réponds UNIQUEMENT avec ce JSON valide (aucun texte avant ou après) :
{{"pertinence": <1-5>, "fidelite": <1-5>, "coherence": <1-5>, "justification": "<1-2 phrases de justification>"}}"""

# ─── Client juge (Anthropic ou OpenAI) ──────────────────────────────────────

def _build_judge_fn():
    """Retourne une fonction call_judge(system, user) -> dict{pertinence, fidelite, coherence, justification}."""
    from openai import OpenAI
    _client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    _model = "gpt-4o"
    logger.info("judge.backend=openai model=%s", _model)

    def call_judge(system: str, user: str) -> dict:
        resp = _client.chat.completions.create(
            model=_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            max_tokens=512,
            temperature=0.0,
        )
        raw = resp.choices[0].message.content or "{}"
        return json.loads(raw)

    return call_judge, "openai", _model


_call_judge, _JUDGE_BACKEND, _JUDGE_MODEL = _build_judge_fn()

# ─── Initialisation base de données + RAG (réels, sans mock) ────────────────

def _ensure_db_initialized(db_path: str, data_dir: str) -> None:
    """Initialise SQLite si le fichier n'existe pas encore."""
    if not Path(db_path).exists():
        logger.info("init_db creating %s", db_path)
        init_db(db_path=db_path, data_dir=data_dir)


def _ensure_rag_initialized(config: Config) -> None:
    """Initialise ChromaDB + indexation docs/ si la collection n'existe pas."""
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


# ─── Fixtures ───────────────────────────────────────────────────────────────

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
    """Agent réel avec DB SQLite et RAG ChromaDB initialisés."""
    return Agent(real_config)


@pytest.fixture(scope="module", autouse=True)
def generate_report_at_end(real_config: Config):
    """Génère rapport_qualite.md après l'exécution de tous les tests."""
    yield
    if _SCORES:
        _write_report(_SCORES, real_config)


# ─── Formatage de la réponse agent pour le juge ─────────────────────────────

def _format_response(result) -> str:
    lines = [
        f"priorité       : {result.priority}",
        f"catégorie      : {result.category} / {result.subcategory}",
        f"équipe         : {result.assigned_to}",
        f"confidence     : {result.confidence_score:.2f}",
        f"is_duplicate   : {result.is_duplicate}",
        f"is_major       : {result.is_major_incident}",
        f"runbooks       : {result.runbooks_suggested}",
        f"alertes        : {result.monitoring_alerts}",
        f"incidents sim. : {result.similar_incidents}",
        f"resolution     : {result.resolution_hint}",
        f"service_tier   : {result.enriched_context.get('service_tier')}",
        f"criticité      : {result.enriched_context.get('business_criticality')}",
        f"rag_docs       : {result.enriched_context.get('rag_docs_used', [])}",
    ]
    return "\n".join(lines)


def _format_incident(q: dict) -> str:
    inc = q["incident"]
    return (
        f"Titre       : {inc['title']}\n"
        f"Description : {inc['description']}\n"
        f"Service     : {inc['service']}"
    )


def _judge_result(q: dict, result, memory_context: str = "Aucun") -> dict:
    """Appelle le juge et retourne les scores parsés."""
    user_prompt = _JUDGE_TEMPLATE.format(
        incident=_format_incident(q),
        response=_format_response(result),
        elements_factuels=q["elements_factuels"],
        memory_context=memory_context,
    )
    scores = _call_judge(_JUDGE_SYSTEM, user_prompt)
    return {
        "pertinence": int(scores.get("pertinence", 1)),
        "fidelite": int(scores.get("fidelite", 1)),
        "coherence": int(scores.get("coherence", 1)),
        "justification": scores.get("justification", ""),
    }


def _format_agent_line(result) -> str:
    runbooks = ", ".join(result.runbooks_suggested) if result.runbooks_suggested else "aucun"
    hint = (result.resolution_hint or "")[:120]
    return (
        f"{result.priority}, "
        f"catégorie {result.category} / {result.subcategory}, "
        f"équipe {result.assigned_to}, "
        f"confidence {result.confidence_score:.2f}, "
        f"runbooks [{runbooks}]. "
        f"{hint}…"
    )


def _run_and_judge(q: dict, agent: Agent, memory_context: str = "Aucun") -> dict:
    """Qualifie l'incident et demande au juge de noter la réponse."""
    inc = IncidentIn(**q["incident"])
    result = agent.qualify(inc)
    scores = _judge_result(q, result, memory_context=memory_context)
    avg = round((scores["pertinence"] + scores["fidelite"] + scores["coherence"]) / 3, 2)
    entry = {
        "id": q["id"],
        "categorie": q["categorie"],
        "question": q["question"][:80] + "...",
        **scores,
        "avg": avg,
    }
    _SCORES.append(entry)

    print(f"\n{q['id']}")
    print(f"Question : {q['question']}")
    print(f"Agent    : {_format_agent_line(result)}")
    print(f"Juge     : [P={scores['pertinence']} F={scores['fidelite']} C={scores['coherence']} moy={avg:.2f}] "
          f"{scores['justification']}")

    return entry


# ─── Tests de qualité ────────────────────────────────────────────────────────

class TestQualiteAgent:

    def test_q01_factuelle_swiftnet_down(self, real_agent: Agent):
        q = next(x for x in QUESTIONS if x["id"] == "Q01")
        entry = _run_and_judge(q, real_agent)
        assert entry["avg"] >= SCORE_MIN_PAR_QUESTION, (
            f"Q01 factuelle: score {entry['avg']} < {SCORE_MIN_PAR_QUESTION}. "
            f"Juge: {entry['justification']}"
        )

    def test_q02_factuelle_pki_expiry(self, real_agent: Agent):
        q = next(x for x in QUESTIONS if x["id"] == "Q02")
        entry = _run_and_judge(q, real_agent)
        assert entry["avg"] >= SCORE_MIN_PAR_QUESTION, (
            f"Q02 factuelle PKI: score {entry['avg']} < {SCORE_MIN_PAR_QUESTION}. "
            f"Juge: {entry['justification']}"
        )

    def test_q03_complexe_nostro_et_backlog(self, real_agent: Agent):
        q = next(x for x in QUESTIONS if x["id"] == "Q03")
        entry = _run_and_judge(q, real_agent)
        assert entry["avg"] >= SCORE_MIN_PAR_QUESTION, (
            f"Q03 complexe: score {entry['avg']} < {SCORE_MIN_PAR_QUESTION}. "
            f"Juge: {entry['justification']}"
        )

    def test_q04_ambigue_description_vague(self, real_agent: Agent):
        q = next(x for x in QUESTIONS if x["id"] == "Q04")
        entry = _run_and_judge(q, real_agent)
        assert entry["avg"] >= SCORE_MIN_PAR_QUESTION, (
            f"Q04 ambiguë: score {entry['avg']} < {SCORE_MIN_PAR_QUESTION}. "
            f"Juge: {entry['justification']}"
        )

    def test_q05_hors_sujet_imprimante(self, real_agent: Agent):
        q = next(x for x in QUESTIONS if x["id"] == "Q05")
        entry = _run_and_judge(q, real_agent)
        assert entry["avg"] >= SCORE_MIN_PAR_QUESTION, (
            f"Q05 hors sujet: score {entry['avg']} < {SCORE_MIN_PAR_QUESTION}. "
            f"Juge: {entry['justification']}"
        )

    def test_q06_securite_hsm_acces_non_autorise(self, real_agent: Agent):
        q = next(x for x in QUESTIONS if x["id"] == "Q06")
        entry = _run_and_judge(q, real_agent)
        assert entry["avg"] >= SCORE_MIN_PAR_QUESTION, (
            f"Q06 sécurité: score {entry['avg']} < {SCORE_MIN_PAR_QUESTION}. "
            f"Juge: {entry['justification']}"
        )

    def test_q07_piege_p1_auto_declare(self, real_agent: Agent):
        q = next(x for x in QUESTIONS if x["id"] == "Q07")
        entry = _run_and_judge(q, real_agent)
        assert entry["avg"] >= SCORE_MIN_PAR_QUESTION, (
            f"Q07 piège: score {entry['avg']} < {SCORE_MIN_PAR_QUESTION}. "
            f"Juge: {entry['justification']}"
        )

    def test_q08_format_cutoff_batch_failure(self, real_agent: Agent):
        q = next(x for x in QUESTIONS if x["id"] == "Q08")
        entry = _run_and_judge(q, real_agent)
        assert entry["avg"] >= SCORE_MIN_PAR_QUESTION, (
            f"Q08 format: score {entry['avg']} < {SCORE_MIN_PAR_QUESTION}. "
            f"Juge: {entry['justification']}"
        )

    def test_q09_memoire_second_incident_gpi(self, real_agent: Agent):
        """Qualifie un pré-incident pour peupler la mémoire, puis le vrai incident."""
        q = next(x for x in QUESTIONS if x["id"] == "Q09")
        # Tour 1 : pré-incident dans la mémoire
        pre_inc = IncidentIn(**q["pre_incident"])
        pre_result = real_agent.qualify(pre_inc)
        memory_context = (
            f"Tour précédent sur gpi-tracker: priorité={pre_result.priority}, "
            f"équipe={pre_result.assigned_to}, confidence={pre_result.confidence_score:.2f}"
        )
        # Tour 2 : incident principal évalué avec la mémoire peuplée
        entry = _run_and_judge(q, real_agent, memory_context=memory_context)
        assert entry["avg"] >= SCORE_MIN_PAR_QUESTION, (
            f"Q09 mémoire: score {entry['avg']} < {SCORE_MIN_PAR_QUESTION}. "
            f"Juge: {entry['justification']}"
        )

    def test_q10_multi_tools_bic_validator(self, real_agent: Agent):
        q = next(x for x in QUESTIONS if x["id"] == "Q10")
        entry = _run_and_judge(q, real_agent)
        assert entry["avg"] >= SCORE_MIN_PAR_QUESTION, (
            f"Q10 multi-tools: score {entry['avg']} < {SCORE_MIN_PAR_QUESTION}. "
            f"Juge: {entry['justification']}"
        )

    def test_q11_bord_domaine_ups(self, real_agent: Agent):
        q = next(x for x in QUESTIONS if x["id"] == "Q11")
        entry = _run_and_judge(q, real_agent)
        assert entry["avg"] >= SCORE_MIN_PAR_QUESTION, (
            f"Q11 bord domaine: score {entry['avg']} < {SCORE_MIN_PAR_QUESTION}. "
            f"Juge: {entry['justification']}"
        )

    def test_score_global_moyen(self):
        """Vérifie que le score global de toutes les questions atteint la cible."""
        assert _SCORES, "Aucun score collecté — les tests précédents ont-ils tous tourné ?"
        global_avg = round(sum(e["avg"] for e in _SCORES) / len(_SCORES), 2)
        print(f"\n{'='*50}")
        print(f"SCORE GLOBAL : {global_avg:.2f} / 5.0  (cible >= {SCORE_GLOBAL_CIBLE})")
        print(f"Questions evaluees : {len(_SCORES)}")
        print(f"{'='*50}")
        assert global_avg >= SCORE_GLOBAL_CIBLE, (
            f"Score global {global_avg} < {SCORE_GLOBAL_CIBLE}. "
            f"Detail par question : "
            + ", ".join(f"{e['id']}={e['avg']}" for e in _SCORES)
        )


# ─── Génération du rapport ───────────────────────────────────────────────────

def _write_report(scores: list[dict], config: Config) -> None:
    if not scores:
        return

    global_avg = round(sum(e["avg"] for e in scores) / len(scores), 2)
    worst = min(scores, key=lambda e: e["avg"])

    lines = [
        "# Rapport de qualité — LLM-as-Judge",
        "",
        f"**Date :** 2026-05-07  ",
        f"**Agent :** `{config.llm_model}` (OpenAI)  ",
        f"**Juge :** `{_JUDGE_MODEL}` ({_JUDGE_BACKEND})  ",
        f"**Seuil par question :** ≥ {SCORE_MIN_PAR_QUESTION}  ",
        f"**Cible globale :** ≥ {SCORE_GLOBAL_CIBLE}  ",
        "",
        "---",
        "",
        "## Tableau des scores",
        "",
        "| ID | Catégorie | Pertinence | Fidélité | Cohérence | **Moyenne** |",
        "|----|-----------|:----------:|:--------:|:---------:|:-----------:|",
    ]

    for e in scores:
        avg_fmt = f"**{e['avg']:.2f}**" if e["avg"] >= SCORE_MIN_PAR_QUESTION else f"⚠️ **{e['avg']:.2f}**"
        lines.append(
            f"| {e['id']} | {e['categorie']} "
            f"| {e['pertinence']} | {e['fidelite']} | {e['coherence']} | {avg_fmt} |"
        )

    lines += [
        "",
        f"**Score global moyen : {global_avg:.2f} / 5.0**",
        "",
        "---",
        "",
        "## Justifications du juge",
        "",
    ]
    for e in scores:
        lines.append(f"**{e['id']} ({e['categorie']})** — *{e['justification']}*  ")
        lines.append("")

    lines += [
        "---",
        "",
        "## Analyse de la pire question",
        "",
        f"**Question la plus faible : {worst['id']} — {worst['categorie']} (score : {worst['avg']:.2f})**",
        "",
        f"> {next(q['question'] for q in QUESTIONS if q['id'] == worst['id'])}",
        "",
        f"**Scores :** Pertinence={worst['pertinence']} Fidélité={worst['fidelite']} Cohérence={worst['coherence']}",
        "",
        f"**Justification du juge :** {worst['justification']}",
        "",
    ]

    # Analyse selon la catégorie
    analyses = {
        "factuelle": (
            "L'agent a du mal à retrouver une information factuelle directe. "
            "Cause probable : corpus RAG non indexé pour ce service ou document peu pertinent retourné. "
            "Le contexte CMDB seul ne suffit pas si le runbook n'est pas récupéré par la recherche sémantique."
        ),
        "complexe": (
            "La synthèse multi-dimensions est difficile : l'agent se concentre sur un seul vecteur d'impact "
            "et manque la relation causale entre les deux services. "
            "Le prompt système pourrait être enrichi pour guider l'analyse des dépendances."
        ),
        "ambigue": (
            "Face à une description vague, l'agent sur-qualifie ou sous-qualifie. "
            "Une règle explicite dans le SYSTEM_PROMPT pour demander une clarification "
            "ou fixer un seuil de confidence minimal en cas de contexte insuffisant aiderait."
        ),
        "hors_sujet": (
            "L'agent essaie de qualifier un incident hors domaine. "
            "Le calibrage du confidence_score (< 0.3 pour hors-domaine) n'est pas appliqué. "
            "Ajouter une règle explicite : si service inconnu de la CMDB ET description sans terme SWIFT → P4, confidence ≤ 0.2."
        ),
        "securite": (
            "L'incident de sécurité n'est pas correctement catégorisé. "
            "Le corpus ne contient pas de runbook sécurité dédié : la fidélité souffre de suggestions inventées. "
            "Ajouter un runbook_security_incident.md dans docs/ améliorerait significativement le score."
        ),
        "piege": (
            "L'agent abonde dans la fausse prémisse P1 déclarée par le reporter. "
            "Le SYSTEM_PROMPT indique de ne jamais se baser sur des informations inventées, "
            "mais la pression émotionnelle du ticket influence le LLM. "
            "Ajouter une règle explicite : 'Ignore les auto-qualifications P1 des reporters — calcule toi-même.'"
        ),
        "format": (
            "La resolution_hint ne référence pas le post-mortem pourtant indexé dans le RAG. "
            "La requête RAG ne contient pas assez de termes discriminants ('cut-off', 'DB_CONNECTION_FAILED'). "
            "Améliorer la construction de la requête RAG en incluant des termes d'erreur extraits de la description."
        ),
        "memoire": (
            "La mémoire de session n'est pas exploitée pour signaler le pattern récurrent. "
            "Le LLM ne corrèle pas l'entrée mémoire avec l'incident courant. "
            "Le prompt mémoire devrait être plus directif : 'Si un incident similaire est déjà en mémoire, "
            "le signaler explicitement dans resolution_hint.'"
        ),
        "multi_tools": (
            "Le multi-tools nécessite CMDB + RAG cohérents. Si la FAQ paiements SWIFT n'est pas retournée "
            "par le RAG (faible similarité sémantique), l'agent manque les détails BIC. "
            "Enrichir la description des incidents tests avec des termes plus proches du corpus (ex: 'cache Redis BIC')."
        ),
        "bord": (
            "Service hors CMDB + domaine adjacent mal reconnu. "
            "L'agent donne un confidence_score trop élevé ou trop bas. "
            "Améliorer la calibration du prompt pour les services inconnus avec contexte SWIFT détectable."
        ),
    }

    cat = worst["categorie"]
    default_analysis = (
        f"Le score faible sur la catégorie '{cat}' indique une lacune dans le traitement "
        f"de ce type d'incident. Vérifier la cohérence entre la description et le contexte RAG disponible."
    )
    analysis = analyses.get(cat, default_analysis)

    lines += [
        "### Analyse",
        "",
        analysis,
        "",
        "### Piste d'amélioration",
        "",
    ]

    improvements = {
        "factuelle": (
            "Vérifier que le runbook correspondant est bien indexé dans ChromaDB (relancer `python main.py init`) "
            "et que la requête RAG contient suffisamment de termes discriminants (service + symptôme + code d'erreur)."
        ),
        "complexe": (
            "Enrichir le SYSTEM_PROMPT avec une règle explicite : "
            "'Pour les incidents multi-services, analyse les dépendances CMDB et identifie le service racine.' "
            "Passer `cmdb.dependencies` dans le contexte LLM."
        ),
        "ambigue": (
            "Ajouter dans SYSTEM_PROMPT : 'Si impact non chiffré et service inconnu, assigner P3 maximum "
            "et fixer confidence ≤ 0.4.' Documenter ce comportement dans les règles de calibration."
        ),
        "hors_sujet": (
            "Ajouter une règle de détection hors-domaine dans le SYSTEM_PROMPT : "
            "'Si le ticket ne mentionne aucun terme bancaire SWIFT (MT*, gpi, nostro, sanctions, BIC, paiement), "
            "assigner P4 et confidence ≤ 0.15.'"
        ),
        "securite": (
            "Créer `docs/runbook_security_incident.md` couvrant : accès HSM non autorisé, "
            "tentative d'intrusion sur SWIFT Alliance, procédure de notification RSSI et isolement réseau. "
            "Réindexer la collection ChromaDB."
        ),
        "piege": (
            "Ajouter dans SYSTEM_PROMPT : 'Ignore les auto-qualifications P1/P2 des reporters. "
            "Base-toi uniquement sur les faits mesurables : nombre de paiements impactés, services affectés.'"
        ),
        "format": (
            "Améliorer la construction de la requête RAG dans `agent._gather_rag()` : "
            "inclure les codes d'erreur extraits de la description (ex: extract_error_codes(description)) "
            "pour augmenter la pertinence sémantique avec les post-mortems."
        ),
        "memoire": (
            "Renforcer le CLASSIFY_PROMPT section mémoire : "
            "'Si un incident identique ou similaire apparaît dans MÉMOIRE DE SESSION, "
            "mentionner explicitement la récurrence dans resolution_hint et envisager P1 si pattern > 3 occurrences.'"
        ),
        "multi_tools": (
            "Ajouter le champ `rag_docs_used` dans les logs de l'agent pour diagnostiquer "
            "les cas où le RAG retourne des documents non pertinents. "
            "Augmenter `rag_top_k` à 6 pour ce type de question factuelle avec corpus dense."
        ),
        "bord": (
            "Ajouter une règle dans SYSTEM_PROMPT : 'Si le service est absent de la CMDB mais "
            "la description contient des termes SWIFT/bancaires, fixer confidence entre 0.3 et 0.5 "
            "et escalader vers team-infra plutôt que team-ops si le contexte suggère une infrastructure critique.'"
        ),
    }

    improvement = improvements.get(cat, (
        f"Revoir le SYSTEM_PROMPT pour mieux couvrir les incidents de type '{cat}'. "
        "Enrichir le corpus docs/ avec des exemples de résolution pour ce type de cas."
    ))

    lines += [
        improvement,
        "",
        "---",
        "",
        f"## Score global",
        "",
        f"**{global_avg:.2f} / 5.0** ({len(scores)} questions évaluées)  ",
        "",
        f"{'✅ Objectif atteint' if global_avg >= SCORE_GLOBAL_CIBLE else '⚠️ Objectif non atteint'} "
        f"(cible : ≥ {SCORE_GLOBAL_CIBLE})",
    ]

    _RAPPORT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nRapport genere : {_RAPPORT_FILE}")
