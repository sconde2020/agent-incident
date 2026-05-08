"""Client juge gpt-4o et utilitaires de formatage pour le LLM-as-Judge."""
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

SCORE_MIN_PAR_QUESTION = 3.0
SCORE_GLOBAL_CIBLE = 3.5

_QUESTIONS_FILE = Path(__file__).parent / "questions.json"
with open(_QUESTIONS_FILE, encoding="utf-8") as _f:
    QUESTIONS: list[dict] = json.load(_f)

# ─── Prompts du juge ──────────────────────────────────────────────────────────

JUDGE_SYSTEM = """Tu es un évaluateur expert en qualification d'incidents bancaires SWIFT.
Tu notes la réponse d'un système de qualification automatique sur trois critères.
Tu es STRICT, IMPARTIAL et tu pénalises toute imprécision.
Ne sois PAS indulgent : une erreur de priorité coûte au moins 1 point."""

JUDGE_TEMPLATE = """INCIDENT SOUMIS :
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

# ─── Client juge ─────────────────────────────────────────────────────────────

def _build_judge_fn():
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    model = "gpt-4o"
    logger.info("judge.backend=openai model=%s", model)

    def call_judge(system: str, user: str) -> dict:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            max_tokens=512,
            temperature=0.0,
        )
        return json.loads(resp.choices[0].message.content or "{}")

    return call_judge, "openai", model


call_judge, JUDGE_BACKEND, JUDGE_MODEL = _build_judge_fn()

# ─── Formatage ────────────────────────────────────────────────────────────────

def format_incident(q: dict) -> str:
    inc = q["incident"]
    return (
        f"Titre       : {inc['title']}\n"
        f"Description : {inc['description']}\n"
        f"Service     : {inc['service']}"
    )


def format_response(result) -> str:
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


def format_agent_line(result) -> str:
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


def judge_result(q: dict, result, memory_context: str = "Aucun") -> dict:
    user_prompt = JUDGE_TEMPLATE.format(
        incident=format_incident(q),
        response=format_response(result),
        elements_factuels=q["elements_factuels"],
        memory_context=memory_context,
    )
    scores = call_judge(JUDGE_SYSTEM, user_prompt)
    return {
        "pertinence": int(scores.get("pertinence", 1)),
        "fidelite": int(scores.get("fidelite", 1)),
        "coherence": int(scores.get("coherence", 1)),
        "justification": scores.get("justification", ""),
    }
