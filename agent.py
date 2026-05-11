import logging
import time
import uuid
from typing import Optional

from config import Config
from monitoring import RequestMonitor
from db.incidents import IncidentDB
from memory.store import ConversationMemory, MemoryEntry
from db.alerts import MonitoringDB
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

    def __init__(self, config: Config, monitor: Optional[RequestMonitor] = None):
        self.config = config
        self.monitor = monitor
        # Couches données
        self.incident_db = IncidentDB(config.db_path)
        self.monitoring_db = MonitoringDB(config.db_path)
        self.cmdb = CMDB(config.db_path)
        # LLM
        self.llm = LLMClient(config)
        # RAG
        self.rag = RAGRetriever(
            config.chroma_path,
            top_k=config.rag_top_k,
            embedding_model=config.embedding_model,
            collection_name=config.chroma_collection_name,
        )
        # Outils
        self.tool_cmdb = SearchCMDB(self.cmdb)
        self.tool_monitoring = SearchMonitoring(self.monitoring_db)
        self.tool_incidents = SearchIncidents(self.incident_db, search_limit=config.search_incidents_limit)
        self.tool_duplicate = DetectDuplicate(self.incident_db, config.duplicate_window_hours, search_limit=config.detect_duplicate_search_limit)
        self.tool_major = DetectMajorIncident(
            self.incident_db,
            config.major_incident_threshold,
            main_search_limit=config.detect_major_incident_main_limit,
            deps_max=config.detect_major_incident_deps_max,
            dep_search_limit=config.detect_major_incident_dep_limit,
        )
        self.tool_update = UpdateIncident(self.incident_db)
        # Audit
        self.audit = AuditLogger(config.db_path)
        self.memory = ConversationMemory(config.max_memory)
        self._last_rag_ms: int = 0

    def qualify(self, incident: IncidentIn) -> IncidentOut:
        """Point d'entrée public. Retourne un IncidentOut enrichi ou lève AgentError."""
        request_id = str(uuid.uuid4())[:8]
        start_time = time.monotonic()
        self.llm.last_llm_ms = 0
        self.llm.last_usage = {}
        incident_id = incident.id
        assert incident_id
        logger.info(
            "agent.qualify.start incident_id=%s service=%s request_id=%s",
            incident_id, incident.service, request_id,
        )
        try:
            result = self._run_pipeline(incident, incident_id, request_id)
        except Exception as exc:
            self._audit_qualify_failure(incident_id, exc, start_time, request_id)
            self._record_to_monitor(incident_id, start_time, error=str(exc))
            raise AgentError(f"Qualification échouée pour {incident_id}: {exc}") from exc
        self._audit_qualify_success(incident_id, result, start_time, request_id)
        self._add_to_memory(result, incident_id)
        self._record_to_monitor(incident_id, start_time)
        return result

    def _audit_qualify_failure(
        self, incident_id: str, exc: Exception, start_time: float, request_id: str
    ) -> None:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        logger.error(
            "agent.qualify.error incident_id=%s error=%s request_id=%s",
            incident_id, exc, request_id,
        )
        self.audit.log(
            incident_id=incident_id, action="qualify", error=str(exc),
            duration_ms=duration_ms, model=self.config.llm_model,
        )

    def _audit_qualify_success(
        self, incident_id: str, result: IncidentOut, start_time: float, request_id: str
    ) -> None:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        self.audit.log(
            incident_id=incident_id, action="qualify",
            result={"priority": result.priority, "category": result.category, "assigned_to": result.assigned_to},
            duration_ms=duration_ms, model=self.config.llm_model, confidence=result.confidence_score,
        )
        logger.info(
            "agent.qualify.done incident_id=%s priority=%s assigned_to=%s "
            "confidence=%.2f duration_ms=%d request_id=%s",
            incident_id, result.priority, result.assigned_to,
            result.confidence_score, duration_ms, request_id,
        )

    def _record_to_monitor(
        self, incident_id: str, start_time: float, error: Optional[str] = None
    ) -> None:
        if not self.monitor:
            return
        duration_ms = int((time.monotonic() - start_time) * 1000)
        usage = self.llm.last_usage
        self.monitor.record(
            incident_id=incident_id,
            duration_ms=duration_ms,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            error=error,
            rag_ms=self._last_rag_ms,
            llm_ms=self.llm.last_llm_ms,
        )

    def _add_to_memory(self, result: IncidentOut, incident_id: str) -> None:
        self.memory.add(MemoryEntry(
            incident_id=incident_id,
            service=result.service,
            title=result.title,
            priority=result.priority,
            category=result.category,
            assigned_to=result.assigned_to,
            confidence_score=result.confidence_score,
            is_duplicate=result.is_duplicate,
            is_major_incident=result.is_major_incident,
        ))

    # ─── Pipeline privé ───────────────────────────────────────────────────────

    def _run_pipeline(
        self, incident: IncidentIn, incident_id: str, request_id: str
    ) -> IncidentOut:
        inc_dict = {**incident.model_dump(), "id": incident_id}
        cmdb_info, monitoring_info, duplicate_info, major_info = self._run_detection(incident, request_id)

        if duplicate_info.get("is_duplicate"):
            logger.info(
                "agent.duplicate_shortcut incident_id=%s duplicate_of=%s",
                incident_id, duplicate_info.get("duplicate_of"),
            )
            return self._qualify_as_duplicate(inc_dict, duplicate_info, monitoring_info, major_info)

        rag_docs, similar = self._gather_rag(incident, request_id)
        context = {
            "cmdb": cmdb_info, "monitoring": monitoring_info,
            "rag_docs": rag_docs, "similar_incidents": similar,
            "duplicate": duplicate_info, "major_incident": major_info,
            "memory": self.memory.to_context(),
        }
        raw_output = self.llm.classify(inc_dict, context)
        self._reconcile_llm_output(raw_output, duplicate_info, major_info)

        result, validation_error = safe_validate_llm_output(raw_output)
        if result is None:
            logger.error(
                "agent.llm_output_invalid incident_id=%s error=%s request_id=%s",
                incident_id, validation_error, request_id,
            )
            return self._qualify_fallback(inc_dict, validation_error, monitoring_info, major_info)

        if not result.monitoring_alerts:
            result.monitoring_alerts = [a["id"] for a in monitoring_info.get("alerts", [])]
        self.tool_update.execute(incident_id, result.model_dump())
        return self._build_out(incident_id, incident, result, cmdb_info, monitoring_info, rag_docs)

    def _run_detection(
        self, incident: IncidentIn, request_id: str
    ) -> tuple[dict, dict, dict, dict]:
        cmdb_info = self.tool_cmdb.execute(incident.service)
        monitoring_info = self.tool_monitoring.execute(incident.service)
        duplicate_info = self.tool_duplicate.execute(incident.service, incident.title, exclude_id=incident.id)
        dependencies = (
            cmdb_info.get("dependencies", [])
            if isinstance(cmdb_info, dict) and not cmdb_info.get("error")
            else []
        )
        major_info = self.tool_major.execute(incident.service, dependencies)
        logger.debug("agent.step1_cmdb service=%s request_id=%s", incident.service, request_id)
        logger.debug("agent.step2_monitoring alerts=%d request_id=%s", monitoring_info.get("alert_count", 0), request_id)
        logger.debug("agent.step3_duplicate is_duplicate=%s request_id=%s", duplicate_info.get("is_duplicate"), request_id)
        logger.debug("agent.step4_major is_major=%s request_id=%s", major_info.get("is_major_incident"), request_id)
        return cmdb_info, monitoring_info, duplicate_info, major_info

    def _gather_rag(self, incident: IncidentIn, request_id: str) -> tuple[list, list]:
        t0 = time.monotonic()
        max_chars = self.config.rag_query_description_max_chars
        rag_query = f"{incident.title} {incident.description[:max_chars]} {incident.service}"
        rag_docs = self.rag.retrieve(rag_query)
        similar = self.tool_incidents.execute(incident.service, incident.title)
        self._last_rag_ms = int((time.monotonic() - t0) * 1000)
        logger.debug("agent.step5_rag docs_retrieved=%d request_id=%s", len(rag_docs), request_id)
        logger.debug("agent.step6_similar found=%d request_id=%s", len(similar), request_id)
        return rag_docs, similar

    def _reconcile_llm_output(
        self, raw_output: dict, duplicate_info: dict, major_info: dict
    ) -> None:
        # Le LLM ne voit pas les IDs détectés localement — on comble ce vide
        # pour éviter un rejet du validateur sur une incohérence évitable.
        if raw_output.get("is_major_incident") and not raw_output.get("related_incidents"):
            raw_output["related_incidents"] = major_info.get("related_incidents", [])
        if raw_output.get("is_duplicate") and not raw_output.get("duplicate_of"):
            raw_output["duplicate_of"] = duplicate_info.get("duplicate_of")

    def _build_out(
        self,
        incident_id: str,
        incident: IncidentIn,
        result,
        cmdb_info: dict,
        monitoring_info: dict,
        rag_docs: list,
    ) -> IncidentOut:
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
        """Qualification minimale pour un doublon confirmé. Hérite la qualification de l'original."""
        original_id = duplicate_info.get("duplicate_of")
        original = self.incident_db.get(original_id) if original_id else None
        priority, category, subcategory, assigned_to = self._inherit_from_original(original)
        self.tool_update.execute(inc_dict["id"], {
            "priority": priority, "category": category, "subcategory": subcategory,
            "assigned_to": assigned_to, "confidence_score": self.config.duplicate_confidence_score,
            "is_duplicate": True, "duplicate_of": original_id,
            "is_major_incident": major_info.get("is_major_incident", False),
        })
        return self._build_duplicate_out(
            inc_dict, priority, category, subcategory, assigned_to,
            original_id, monitoring_info, major_info,
        )

    def _inherit_from_original(self, original: Optional[dict]) -> tuple[str, str, str, str]:
        fb = self.config
        priority = (original.get("priority") or fb.fallback_priority) if original else fb.fallback_priority
        category = (original.get("category") or fb.fallback_category) if original else fb.fallback_category
        subcategory = (original.get("subcategory") or fb.fallback_subcategory) if original else fb.fallback_subcategory
        assigned_to = (original.get("assigned_to") or fb.fallback_assigned_to) if original else fb.fallback_assigned_to
        return priority, category, subcategory, assigned_to

    def _build_duplicate_out(
        self,
        inc_dict: dict,
        priority: str, category: str, subcategory: str, assigned_to: str,
        original_id: Optional[str],
        monitoring_info: dict,
        major_info: dict,
    ) -> IncidentOut:
        return IncidentOut(
            id=inc_dict["id"],
            title=inc_dict.get("title", ""),
            service=inc_dict.get("service", ""),
            priority=priority, category=category, subcategory=subcategory, assigned_to=assigned_to,
            confidence_score=self.config.duplicate_confidence_score, runbooks_suggested=[],
            similar_incidents=[original_id] if original_id else [],
            monitoring_alerts=[a["id"] for a in monitoring_info.get("alerts", [])],
            is_duplicate=True, duplicate_of=original_id,
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
            {"qualification_failed": True, "priority": None, "category": None, "assigned_to": self.config.fallback_assigned_to},
        )
        return IncidentOut(
            id=inc_dict["id"],
            title=inc_dict.get("title", ""),
            service=inc_dict.get("service", ""),
            priority=self.config.fallback_priority,
            category=self.config.fallback_category,
            subcategory=self.config.fallback_subcategory,
            assigned_to=self.config.fallback_assigned_to,
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
