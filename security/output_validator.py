import logging
import re
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator

logger = logging.getLogger(__name__)

VALID_PRIORITIES = {"P1", "P2", "P3", "P4"}
VALID_CATEGORIES = {
    "Infrastructure", "Application", "Opérationnel", "Conformité", "Sécurité",
}
VALID_SUBCATEGORIES = {
    "Connectivité", "Performance", "Traitement", "Déploiement", "Configuration",
    "Intégration", "Réconciliation", "Correspondant", "Sanctions", "AML",
    "Certificats", "Réseau", "Accès",
}

_INC_RE = re.compile(r"^INC\d{7}$")

# Patterns d'hallucinations LLM connus
_HALLUCINATION_RE = re.compile(
    r"example\.com|I am an AI|As an AI|<tool_call>|TOOL_NAME",
    re.IGNORECASE,
)

# Données sensibles qui ne doivent jamais apparaître dans une suggestion de résolution
_SENSITIVE_OUTPUT_RE = re.compile(
    r"api[_-]?key|bearer\s+[A-Za-z0-9]+|password\s*=|[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7,19}",
    re.IGNORECASE,
)


class QualificationResult(BaseModel):
    """Sortie attendue du LLM après validation et nettoyage."""

    priority: str
    category: str
    subcategory: str
    assigned_to: str
    confidence_score: float
    resolution_hint: Optional[str] = None
    runbooks_suggested: list[str] = []
    similar_incidents: list[str] = []
    monitoring_alerts: list[str] = []
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None
    is_major_incident: bool = False
    related_incidents: list[str] = []

    @field_validator("priority")
    @classmethod
    def check_priority(cls, v):
        if v not in VALID_PRIORITIES:
            raise ValueError(f"priority '{v}' hors liste autorisée")
        return v

    @field_validator("category")
    @classmethod
    def check_category(cls, v):
        if v not in VALID_CATEGORIES:
            raise ValueError(f"category '{v}' hors liste autorisée")
        return v

    @field_validator("subcategory")
    @classmethod
    def check_subcategory(cls, v):
        if v not in VALID_SUBCATEGORIES:
            raise ValueError(f"subcategory '{v}' hors liste autorisée")
        return v

    @field_validator("confidence_score")
    @classmethod
    def check_confidence(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence_score {v} hors [0.0, 1.0]")
        if v < 0.5:
            logger.warning("output_validator.low_confidence score=%.2f", v)
        return v

    @field_validator("similar_incidents", "related_incidents", mode="before")
    @classmethod
    def filter_incident_ids(cls, v):
        # Rejeter silencieusement tout ID qui ne respecte pas le format INCxxxxxxx
        return [x for x in (v or []) if _INC_RE.match(str(x))]

    @field_validator("runbooks_suggested", mode="before")
    @classmethod
    def filter_runbooks(cls, v):
        safe = []
        for rb in (v or []):
            # Bloquer les path traversal – le LLM ne devrait jamais suggérer ../
            if ".." in str(rb) or str(rb).startswith("/"):
                logger.warning("output_validator.path_traversal_blocked runbook=%s", rb)
                continue
            safe.append(rb)
        return safe

    @field_validator("resolution_hint")
    @classmethod
    def sanitize_resolution_hint(cls, v):
        if v is None:
            return v
        if _SENSITIVE_OUTPUT_RE.search(v):
            logger.warning("output_validator.sensitive_data_in_hint")
            return "[Suggestion supprimée : données sensibles détectées]"
        if _HALLUCINATION_RE.search(v):
            logger.warning("output_validator.hallucination_detected")
            return "[Suggestion supprimée : contenu suspect]"
        return v

    @model_validator(mode="after")
    def check_consistency(self):
        if self.is_duplicate and not self.duplicate_of:
            raise ValueError("is_duplicate=True mais duplicate_of est absent")
        if self.is_major_incident and len(self.related_incidents) < 2:
            # Le LLM n'a pas accès aux IDs réels — downgrade silencieux plutôt que rejet total
            self.is_major_incident = False
            self.related_incidents = []
            logger.warning("output_validator.major_incident_downgraded no_related_incidents")
        return self


def validate_llm_output(raw: dict) -> QualificationResult:
    """Valider – lève ValidationError si invalide."""
    return QualificationResult(**raw)


def safe_validate_llm_output(raw: dict) -> tuple[Optional[QualificationResult], Optional[str]]:
    """Variante tolérante – retourne (result, None) ou (None, message_erreur)."""
    try:
        return validate_llm_output(raw), None
    except Exception as exc:
        logger.error("output_validator.validation_failed error=%s", exc)
        return None, str(exc)
