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

# Patterns d'hallucinations LLM : artefacts de template, refus inattendus, échos d'injection
_HALLUCINATION_RE = re.compile(
    r"example\.com"
    r"|I am an AI|As an AI language model|I cannot fulfill|I cannot provide"
    r"|<tool_call>|TOOL_NAME|\[INST\]|<\|system\|>|<\|im_start\|>|<\|im_end\|>"
    r"|\n\nHuman\s*:|\n\nAssistant\s*:"
    r"|je suis un assistant IA|en tant qu'IA"
    # Détection des échos d'injection de prompt dans la sortie LLM
    r"|\bSYSTEM\s*:\s+\w"                          # SYSTEM: <directive> recopiée
    r"|\binclude\s+the\s+(literal\s+)?word\b"      # echo d'instruction injectée
    r"|\brepeat\s+the\s+(following|word)\b"
    r"|\bact\s+as\s+(if|though|a)\b",
    re.IGNORECASE,
)

# Données sensibles : patterns avec valeur effective (pas les seuls noms de champs)
_SENSITIVE_OUTPUT_RE = re.compile(
    # Identifiants financiers
    r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7,19}\b"           # IBAN
    r"|(?:\d{4}[- ]){3}\d{4}"                            # carte bancaire
    # Credentials avec signe = (valeur présente)
    r"|password\s*=\s*['\"]?\S"
    r"|mot\s*de\s*passe\s*=\s*['\"]?\S"                  # français
    r"|api[_-]?key\s*=\s*['\"]?\S"
    r"|cl[eé][_-]?(?:api|secr[eè]te?)\s*=\s*['\"]?\S"   # clé API/secrète
    r"|secret\s*=\s*['\"]?\w{8,}"
    r"|token\s*=\s*['\"]?[A-Za-z0-9\-._~+/]{16,}"
    r"|jeton\s*=\s*['\"]?\S{8,}"                         # français
    # En-têtes d'authentification portant leur valeur
    r"|Bearer\s+[A-Za-z0-9\-._~+/]{10,}=*"
    # Matériel cryptographique (PEM blocks)
    r"|-----BEGIN\s+(?:RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE\s+KEY"
    r"|-----BEGIN\s+CERTIFICATE",
    re.IGNORECASE,
)

VALID_TEAMS = {
    "team-swift", "team-infra", "team-payments", "team-compliance",
    "team-ops", "team-correspondent", "team-security", "team-backend",
    "support-helpdesk",
}


def _sanitize_text(text: str, field: str) -> str:
    if _SENSITIVE_OUTPUT_RE.search(text):
        logger.warning("output_validator.sensitive_data field=%s", field)
        return "[Contenu supprimé : données sensibles détectées]"
    if _HALLUCINATION_RE.search(text):
        logger.warning("output_validator.hallucination_detected field=%s", field)
        return "[Contenu supprimé : artefact LLM détecté]"
    return text


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

    @field_validator("assigned_to")
    @classmethod
    def check_assigned_to(cls, v):
        if v not in VALID_TEAMS:
            raise ValueError(f"assigned_to '{v}' hors liste autorisée")
        return v

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

    @field_validator("monitoring_alerts", mode="before")
    @classmethod
    def sanitize_alerts(cls, v):
        return [_sanitize_text(a, "monitoring_alert") for a in (v or []) if a]

    @field_validator("resolution_hint")
    @classmethod
    def sanitize_resolution_hint(cls, v):
        if v is None:
            return v
        return _sanitize_text(v, "resolution_hint")

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
