import json
import logging
from typing import Optional

from openai import OpenAI, OpenAIError

from config import Config
from prompts import SYSTEM_PROMPT, CLASSIFY_PROMPT

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Erreur lors d'un appel à l'API OpenAI."""


class LLMClient:
    """Encapsule tous les appels à l'API OpenAI. Un seul appel par qualification."""

    def __init__(self, config: Config):
        self.config = config
        self.client = OpenAI(api_key=config.openai_api_key)

    def classify(self, incident: dict, context: dict) -> dict:
        """
        Appel principal : classification + routing + suggestion de résolution.
        Retourne un dict brut (à valider par output_validator).
        """
        incident_id = incident.get("id", "?")
        logger.info("llm.classify.start incident_id=%s model=%s", incident_id, self.config.llm_model)
        prompt = self._build_prompt(incident, context)
        response = self._call_api(prompt, incident_id)
        result = self._parse_json(response.choices[0].message.content or "{}", incident_id)
        self._log_classify_done(incident_id, result, response.usage)
        return result

    def _build_prompt(self, incident: dict, context: dict) -> str:
        cfg = self.config
        return CLASSIFY_PROMPT.format(
            incident_json=json.dumps(incident, ensure_ascii=False, indent=2),
            cmdb_context=_fmt_cmdb(context.get("cmdb")),
            monitoring_context=_fmt_monitoring(context.get("monitoring"), cfg.llm_context_alerts_limit),
            rag_context=_fmt_rag(context.get("rag_docs", []), cfg.llm_context_rag_docs_limit, cfg.llm_rag_doc_truncate_chars),
            similar_incidents=_fmt_similar(context.get("similar_incidents", []), cfg.llm_context_similar_incidents_limit),
            duplicate_info=_fmt_duplicate(context.get("duplicate")),
            major_incident_info=_fmt_major(context.get("major_incident")),
            memory_context=_fmt_memory(context.get("memory", [])),
        )

    def _call_api(self, prompt: str, incident_id: str):
        try:
            return self.client.chat.completions.create(
                model=self.config.llm_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=self.config.llm_max_tokens,
                temperature=self.config.llm_temperature,
                # Garantit que la réponse est du JSON valide
                response_format={"type": "json_object"},
            )
        except OpenAIError as exc:
            logger.error("llm.classify.api_error incident_id=%s error=%s", incident_id, exc)
            raise LLMError(f"Erreur API OpenAI : {exc}") from exc

    def _parse_json(self, raw: str, incident_id: str) -> dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("llm.classify.json_error incident_id=%s content=%.200s", incident_id, raw)
            raise LLMError(f"Réponse LLM non parseable en JSON : {exc}") from exc

    def _log_classify_done(self, incident_id: str, result: dict, usage) -> None:
        logger.info(
            "llm.classify.done incident_id=%s priority=%s confidence=%s "
            "prompt_tokens=%d completion_tokens=%d",
            incident_id, result.get("priority"), result.get("confidence_score"),
            usage.prompt_tokens if usage else 0,
            usage.completion_tokens if usage else 0,
        )


# ─── Fonctions de formatage du contexte ──────────────────────────────────────

def _fmt_cmdb(cmdb: Optional[dict]) -> str:
    if not cmdb or cmdb.get("error"):
        return "Non disponible"
    return (
        f"Service : {cmdb.get('display_name', cmdb.get('name'))}\n"
        f"Criticité : {cmdb.get('business_criticality')} | Tier : {cmdb.get('tier')}\n"
        f"Équipe : {cmdb.get('team')}\n"
        f"Dépendances : {', '.join(cmdb.get('dependencies', []))}\n"
        f"Dépendants : {', '.join(cmdb.get('dependents', []))}"
    )


def _fmt_monitoring(monitoring: Optional[dict], limit: int = 5) -> str:
    if not monitoring:
        return "Aucune alerte"
    alerts = monitoring.get("alerts", [])
    if not alerts:
        return "Aucune alerte active"
    lines = [
        f"[{a['severity'].upper()}] {a['name']} – {a['message']}"
        for a in alerts[:limit]
    ]
    return "\n".join(lines)


def _fmt_rag(docs: list, limit: int = 4, truncate: int = 600) -> str:
    if not docs:
        return "Aucune documentation pertinente trouvée"
    parts = [
        f"--- {doc['source_file']} ({doc['doc_type']}) ---\n{doc['text'][:truncate]}"
        for doc in docs[:limit]
    ]
    return "\n\n".join(parts)


def _fmt_similar(incidents: list, limit: int = 5) -> str:
    if not incidents:
        return "Aucun incident similaire récent"
    lines = [
        f"• {inc['id']} [{inc.get('priority', '?')}] {inc.get('title', '')[:80]} ({inc.get('status')})"
        for inc in incidents[:limit]
    ]
    return "\n".join(lines)


def _fmt_duplicate(dup: Optional[dict]) -> str:
    if not dup or not dup.get("is_duplicate"):
        return "Non (aucun doublon détecté)"
    return f"OUI – doublon probable de {dup['duplicate_of']}"


def _fmt_major(major: Optional[dict]) -> str:
    if not major or not major.get("is_major_incident"):
        return "Non"
    svcs = ", ".join(major.get("affected_services", []))
    return f"OUI – {len(major.get('affected_services', []))} services affectés : {svcs}"


def _fmt_memory(entries: list) -> str:
    if not entries:
        return "Aucune qualification dans la session courante."
    lines = [
        f"• {e['incident_id']} [{e['priority']}] {e['service']} → {e['assigned_to']}"
        f" ({e['category']}, conf={e['confidence_score']:.2f})"
        for e in entries
    ]
    return "\n".join(lines)
