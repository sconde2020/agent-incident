import logging
import time
import uuid
from datetime import datetime
from typing import Optional

from config import Config
from db.incidents import IncidentDB
from db.monitoring import MonitoringDB
from db.cmdb import CMDB
from db.models import IncidentIn, IncidentOut
from llm import LLMClient, LLMError
from rag.retriever import RAGRetriever
from security.audit import AuditLogger
from security.output_validator import safe_validate_llm_output
from tools.search_cmdb import SearchCMDB
from tools.search_monitoring import SearchMonitoring
from tools.search_incidents import SearchIncidents
from tools.detect_duplicate import DetectDuplicate
from tools.detect_major_incident import DetectMajorIncident
from tools.update_incident import UpdateIncident

logger = logging.getLogger(__name__)


class AgentError(Exception):
    """Erreur non récupérable lors de la qualification d'un incident."""


class Agent:
    """
    Orchestrateur principal du pipeline de qualification des incidents SWIFT.
    Pipeline déterministe en 9 étapes – pas d'agentic loop pour garantir
    la traçabilité et la reproductibilité en contexte bancaire.
    """

    def __init__(self, config: Config):
        self.config = config
        # Couches données
        self.incident_db = IncidentDB(config.db_path)
        self.monitoring_db = MonitoringDB(config.db_path)
        self.cmdb = CMDB(config.db_path)
        # LLM
        self.llm = LLMClient(config)
        # RAG
        self.rag = RAGRetriever(config.chroma_path, top_k=config.rag_top_k)
        # Outils
        self.tool_cmdb = SearchCMDB(self.cmdb)
        self.tool_monitoring = SearchMonitoring(self.monitoring_db)
        self.tool_incidents = SearchIncidents(self.incident_db)
        self.tool_duplicate = DetectDuplicate(self.incident_db, config.duplicate_window_hours)
        self.tool_major = DetectMajorIncident(self.incident_db, config.major_incident_threshold)
        self.tool_update = UpdateIncident(self.incident_db)
        # Audit
        self.audit = AuditLogger(config.db_path)

    def qualify(self, incident: IncidentIn) -> IncidentOut:
        """
        Point d'entrée public.
        Retourne un IncidentOut enrichi ou lève AgentError.
        """
        request_id = str(uuid.uuid4())[:8]
        start_time = time.monotonic()

        # Générer un ID si l'incident n'en a pas (cas payload JSON inline)
        incident_id = incident.id or f"INC{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        logger.info(
            "agent.qualify.start incident_id=%s service=%s request_id=%s",
            incident_id, incident.service, request_id,
        )

        try:
            result = self._run_pipeline(incident, incident_id, request_id)
        except Exception as exc:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.error(
                "agent.qualify.error incident_id=%s error=%s request_id=%s",
                incident_id, exc, request_id,
            )
            self.audit.log(
                incident_id=incident_id,
                action="qualify",
                error=str(exc),
                duration_ms=duration_ms,
                model=self.config.llm_model,
            )
            raise AgentError(f"Qualification échouée pour {incident_id}: {exc}") from exc

        duration_ms = int((time.monotonic() - start_time) * 1000)
        self.audit.log(
            incident_id=incident_id,
            action="qualify",
            result={
                "priority": result.priority,
                "category": result.category,
                "assigned_to": result.assigned_to,
            },
            duration_ms=duration_ms,
            model=self.config.llm_model,
            confidence=result.confidence_score,
        )

        logger.info(
            "agent.qualify.done incident_id=%s priority=%s assigned_to=%s "
            "confidence=%.2f duration_ms=%d request_id=%s",
            incident_id, result.priority, result.assigned_to,
            result.confidence_score, duration_ms, request_id,
        )
        return result

    # ─── Pipeline privé ───────────────────────────────────────────────────────

    def _run_pipeline(
        self, incident: IncidentIn, incident_id: str, request_id: str
    ) -> IncidentOut:
        inc_dict = incident.model_dump()
        inc_dict["id"] = incident_id

        # ── Étape 1 : CMDB ──────────────────────────────────────────────────
        cmdb_info = self.tool_cmdb.execute(incident.service)
        logger.debug("agent.step1_cmdb service=%s request_id=%s", incident.service, request_id)

        # ── Étape 2 : Monitoring ────────────────────────────────────────────
        monitoring_info = self.tool_monitoring.execute(incident.service)
        logger.debug(
            "agent.step2_monitoring alerts=%d request_id=%s",
            monitoring_info.get("alert_count", 0), request_id,
        )

        # ── Étape 3 : Détection doublon ─────────────────────────────────────
        duplicate_info = self.tool_duplicate.execute(incident.service, incident.title)
        logger.debug(
            "agent.step3_duplicate is_duplicate=%s request_id=%s",
            duplicate_info.get("is_duplicate"), request_id,
        )

        # ── Étape 4 : Détection incident majeur ─────────────────────────────
        dependencies = (
            cmdb_info.get("dependencies", [])
            if isinstance(cmdb_info, dict) and not cmdb_info.get("error")
            else []
        )
        major_info = self.tool_major.execute(incident.service, dependencies)
        logger.debug(
            "agent.step4_major is_major=%s request_id=%s",
            major_info.get("is_major_incident"), request_id,
        )

        # Court-circuit doublon : pas besoin d'appeler le LLM
        if duplicate_info.get("is_duplicate"):
            logger.info(
                "agent.duplicate_shortcut incident_id=%s duplicate_of=%s",
                incident_id, duplicate_info.get("duplicate_of"),
            )
            return self._qualify_as_duplicate(
                inc_dict, duplicate_info, monitoring_info, major_info
            )

        # ── Étape 5 : RAG ────────────────────────────────────────────────────
        rag_query = f"{incident.title} {incident.description[:300]} {incident.service}"
        rag_docs = self.rag.retrieve(rag_query)
        logger.debug(
            "agent.step5_rag docs_retrieved=%d request_id=%s", len(rag_docs), request_id
        )

        # ── Étape 6 : Incidents similaires ──────────────────────────────────
        similar = self.tool_incidents.execute(incident.service, incident.title)
        logger.debug(
            "agent.step6_similar found=%d request_id=%s", len(similar), request_id
        )

        # ── Étape 7 : Appel LLM ─────────────────────────────────────────────
        context = {
            "cmdb": cmdb_info,
            "monitoring": monitoring_info,
            "rag_docs": rag_docs,
            "similar_incidents": similar,
            "duplicate": duplicate_info,
            "major_incident": major_info,
        }
        raw_output = self.llm.classify(inc_dict, context)

        # Réconcilier la sortie LLM avec les données de détection locale.
        # Le LLM déclare parfois is_major_incident=True sans peupler related_incidents
        # (il n'a pas accès direct aux IDs détectés par l'outil). On comble ce vide
        # pour éviter un rejet du validateur sur une incohérence évitable.
        if raw_output.get("is_major_incident") and not raw_output.get("related_incidents"):
            raw_output["related_incidents"] = major_info.get("related_incidents", [])
        # Même logique pour is_duplicate / duplicate_of
        if raw_output.get("is_duplicate") and not raw_output.get("duplicate_of"):
            raw_output["duplicate_of"] = duplicate_info.get("duplicate_of")

        # ── Étape 7b : Validation sortie LLM ────────────────────────────────
        result, validation_error = safe_validate_llm_output(raw_output)

        if result is None:
            logger.error(
                "agent.llm_output_invalid incident_id=%s error=%s request_id=%s",
                incident_id, validation_error, request_id,
            )
            return self._qualify_fallback(inc_dict, validation_error, monitoring_info, major_info)

        # Compléter les alertes monitoring si le LLM ne les a pas listées
        if not result.monitoring_alerts:
            result.monitoring_alerts = [a["id"] for a in monitoring_info.get("alerts", [])]

        # ── Étape 8 : Mise à jour SQLite ─────────────────────────────────────
        self.tool_update.execute(incident_id, result.model_dump())

        # ── Étape 9 : Construction IncidentOut ───────────────────────────────
        cmdb = cmdb_info if isinstance(cmdb_info, dict) and not cmdb_info.get("error") else {}
        return IncidentOut(
            id=incident_id,
            title=incident.title,
            service=incident.service,
            priority=result.priority,
            category=result.category,
            subcategory=result.subcategory,
            assigned_to=result.assigned_to,
            confidence_score=result.confidence_score,
            runbooks_suggested=result.runbooks_suggested,
            similar_incidents=result.similar_incidents,
            monitoring_alerts=result.monitoring_alerts,
            is_duplicate=result.is_duplicate,
            duplicate_of=result.duplicate_of,
            is_major_incident=result.is_major_incident,
            related_incidents=result.related_incidents,
            resolution_hint=result.resolution_hint,
            enriched_context={
                "service_tier": cmdb.get("tier"),
                "business_criticality": cmdb.get("business_criticality"),
                "active_alerts": monitoring_info.get("alert_count", 0),
                "has_critical_alerts": monitoring_info.get("has_critical_alerts", False),
                "rag_docs_used": [d["source_file"] for d in rag_docs],
            },
        )

    def _qualify_as_duplicate(
        self,
        inc_dict: dict,
        duplicate_info: dict,
        monitoring_info: dict,
        major_info: dict,
    ) -> IncidentOut:
        """
        Qualification minimale pour un doublon confirmé.
        Hérite la priorité et l'équipe de l'incident original pour rester cohérent.
        """
        original_id = duplicate_info.get("duplicate_of")
        original = self.incident_db.get(original_id) if original_id else None

        priority = (original.get("priority") or "P3") if original else "P3"
        category = (original.get("category") or "Application") if original else "Application"
        subcategory = (original.get("subcategory") or "Traitement") if original else "Traitement"
        assigned_to = (original.get("assigned_to") or "team-ops") if original else "team-ops"

        qualification = {
            "priority": priority, "category": category, "subcategory": subcategory,
            "assigned_to": assigned_to, "confidence_score": 0.95,
            "is_duplicate": True, "duplicate_of": original_id,
            "is_major_incident": major_info.get("is_major_incident", False),
        }
        self.tool_update.execute(inc_dict["id"], qualification)

        return IncidentOut(
            id=inc_dict["id"],
            title=inc_dict.get("title", ""),
            service=inc_dict.get("service", ""),
            priority=priority,
            category=category,
            subcategory=subcategory,
            assigned_to=assigned_to,
            confidence_score=0.95,
            runbooks_suggested=[],
            similar_incidents=[original_id] if original_id else [],
            monitoring_alerts=[a["id"] for a in monitoring_info.get("alerts", [])],
            is_duplicate=True,
            duplicate_of=original_id,
            is_major_incident=major_info.get("is_major_incident", False),
            related_incidents=major_info.get("related_incidents", []),
            resolution_hint=f"Doublon de {original_id} – suivre l'incident original.",
            enriched_context={"is_duplicate": True, "duplicate_of": original_id},
        )

    def _qualify_fallback(
        self,
        inc_dict: dict,
        error: Optional[str],
        monitoring_info: dict,
        major_info: dict,
    ) -> IncidentOut:
        """
        Fallback conservateur quand la sortie LLM est invalide.
        Marque l'incident qualification_failed=True pour révision humaine.
        """
        self.tool_update.execute(
            inc_dict["id"],
            {"qualification_failed": True, "priority": None, "category": None, "assigned_to": "team-ops"},
        )
        return IncidentOut(
            id=inc_dict["id"],
            title=inc_dict.get("title", ""),
            service=inc_dict.get("service", ""),
            priority="P3",  # Priorité conservative par défaut
            category="Application",
            subcategory="Traitement",
            assigned_to="team-ops",
            confidence_score=0.0,
            runbooks_suggested=[],
            similar_incidents=[],
            monitoring_alerts=[a["id"] for a in monitoring_info.get("alerts", [])],
            is_duplicate=False,
            is_major_incident=major_info.get("is_major_incident", False),
            related_incidents=major_info.get("related_incidents", []),
            resolution_hint="Qualification automatique échouée – révision manuelle requise.",
            enriched_context={"qualification_failed": True, "error": error},
        )
