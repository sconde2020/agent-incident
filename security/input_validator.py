import logging
import re
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator

logger = logging.getLogger(__name__)

VALID_STATUSES = {"open", "in_progress", "pending", "resolved", "closed"}
VALID_PRIORITIES = {"P1", "P2", "P3", "P4"}
VALID_CATEGORIES = {
    "Infrastructure", "Application", "Opérationnel", "Conformité", "Sécurité",
}
VALID_SUBCATEGORIES = {
    "Connectivité", "Performance", "Traitement", "Déploiement", "Configuration",
    "Intégration", "Réconciliation", "Correspondant", "Sanctions", "AML",
    "Certificats", "Réseau", "Accès",
}

# Patterns d'injection de prompt — vecteurs anglais et français
_PROMPT_INJECTION_RE = re.compile(
    # ── Anglais ──────────────────────────────────────────────────────────────
    r"ignore\s+(previous|all|above|prior)\s+instructions?"
    r"|\[INST\]"
    r"|<\|system\|>"
    r"|<\|im_start\|>"
    r"|<\|im_end\|>"
    r"|jailbreak"
    r"|DAN\s+mode"
    r"|act\s+as\s+(if|though)"
    r"|you\s+are\s+now\s+(a\s+)?(?:an?\s+)?\w+"       # "you are now a …"
    r"|pretend\s+(you\s+are|to\s+be)"
    r"|disregard\s+(all|any|previous)\s+instructions?"
    r"|new\s+instructions?\s*:"
    r"|system\s*prompt\s*:"
    # ── Français ─────────────────────────────────────────────────────────────
    r"|ignore\s+(les\s+)?(instructions?|consignes?)\s+(précédentes?|ci-dessus|antérieures?)"
    r"|oublie\s+(tout|les\s+instructions?|tes\s+instructions?)"
    r"|tu\s+es\s+maintenant\s+(un|une)?\s*\w+"         # "tu es maintenant un …"
    r"|fais\s+semblant\s+d['']être"
    r"|joue\s+le\s+r[oô]le\s+de"
    r"|nouvelles?\s+instructions?\s*:"
    r"|ignore\s+ce\s+qui\s+précède"
    r"|désactive\s+(les\s+)?(filtres?|restrictions?|règles?)"
    r"|contourne\s+(les\s+)?(règles?|restrictions?|sécurités?)"
    r"|réponds?\s+sans\s+(filtre|restriction|limite)",
    re.IGNORECASE,
)

# Patterns de données sensibles à détecter dans les descriptions
# re.IGNORECASE appliqué globalement – Python 3.14 interdit (?i) hors position 0
_SENSITIVE_RE = re.compile(
    r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7,19}\b"      # IBAN
    r"|\b(?:\d{4}[- ]){3}\d{4}\b"                  # Numéro de carte bancaire
    r"|password\s*="
    r"|mot\s*de\s*passe\s*="                        # mot de passe en français
    r"|api[_-]?key\s*="
    r"|cl[eé][_-]?api\s*="                         # clé API en français
    r"|Bearer\s+[A-Za-z0-9\-._~+/]+=*"
    r"|secret\s*=\s*['\"]?\w{8,}"                  # secret=<valeur>
    r"|\btoken\s*=\s*['\"]?[A-Za-z0-9\-._~+/]{16,}", # token=<valeur longue>
    re.IGNORECASE,
)

# Patterns d'injection SQL — protège les champs texte libres contre les attaques DB
_SQL_INJECTION_RE = re.compile(
    r"\b(UNION\s+(?:ALL\s+)?SELECT|SELECT\s+.+\s+FROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET"
    r"|DELETE\s+FROM|DROP\s+(?:TABLE|DATABASE|INDEX)|ALTER\s+TABLE|CREATE\s+TABLE"
    r"|TRUNCATE\s+TABLE|EXEC(?:UTE)?\s*\(|xp_cmdshell|sp_executesql"
    r"|CAST\s*\(|CONVERT\s*\(.*\bCHAR\b"
    r"|LOAD_FILE\s*\(|INTO\s+OUTFILE|INFORMATION_SCHEMA)\b"
    # Commentaires SQL inline souvent utilisés pour tronquer les requêtes
    r"|--\s*$"
    r"|;\s*(?:DROP|DELETE|INSERT|UPDATE|SELECT|EXEC)",
    re.IGNORECASE | re.MULTILINE,
)

_INC_RE = re.compile(r"^INC\d{7}$")
_SERVICE_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]*[a-z0-9]$")
_EMAIL_RE = re.compile(r"^[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}$")
_TEAM_RE = re.compile(r"^team-[a-z][a-z0-9\-]*$")


class IncidentInput(BaseModel):
    """Modèle de validation stricte des incidents entrants avant traitement par l'agent."""

    id: Optional[str] = None
    title: str
    description: str
    service: str
    status: Optional[str] = "open"
    priority: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    reported_by: Optional[str] = None
    assigned_to: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    sla_breach_at: Optional[str] = None

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, v):
        if v is not None and not _INC_RE.match(str(v)):
            raise ValueError(f"Format invalide : attendu INC + 7 chiffres, reçu '{v}'")
        return v

    @field_validator("title")
    @classmethod
    def validate_title(cls, v):
        if len(v) < 5 or len(v) > 200:
            raise ValueError("title : entre 5 et 200 caractères requis")
        _check_injection(v, "title")
        _check_sql_injection(v, "title")
        return v.strip()

    @field_validator("description")
    @classmethod
    def validate_description(cls, v):
        if len(v) < 10 or len(v) > 5000:
            raise ValueError("description : entre 10 et 5000 caractères requis")
        _check_injection(v, "description")
        _check_sql_injection(v, "description")
        _check_sensitive_data(v)
        return v.strip()

    @field_validator("service")
    @classmethod
    def validate_service(cls, v):
        v = v.lower().strip()
        if not _SERVICE_RE.match(v):
            raise ValueError(f"Format de service invalide : '{v}'")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v is not None and v not in VALID_STATUSES:
            raise ValueError(f"status '{v}' inconnu. Valeurs admises : {VALID_STATUSES}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v):
        if v is not None and v not in VALID_PRIORITIES:
            raise ValueError(f"priority '{v}' invalide")
        return v

    @field_validator("reported_by", "assigned_to")
    @classmethod
    def validate_actor(cls, v):
        if v is not None and not (_EMAIL_RE.match(v) or _TEAM_RE.match(v)):
            raise ValueError(f"'{v}' doit être un email valide ou un identifiant team-xxx")
        return v

    @model_validator(mode="after")
    def subcategory_requires_category(self):
        if self.subcategory and not self.category:
            raise ValueError("subcategory nécessite que category soit renseigné")
        return self


def _check_injection(text: str, field: str) -> None:
    if _PROMPT_INJECTION_RE.search(text):
        logger.critical("input_validator.prompt_injection field=%s", field)
        raise ValueError(f"Contenu suspect détecté dans '{field}'")


def _check_sql_injection(text: str, field: str) -> None:
    if _SQL_INJECTION_RE.search(text):
        logger.critical("input_validator.sql_injection field=%s", field)
        raise ValueError(f"Contenu SQL suspect détecté dans '{field}'")


def _check_sensitive_data(text: str) -> None:
    if _SENSITIVE_RE.search(text):
        logger.warning("input_validator.sensitive_data_detected")
        raise ValueError("La description contient des données potentiellement sensibles")


def validate_bic(bic: str) -> bool:
    """Format BIC SWIFT : 8 ou 11 caractères [A-Z0-9]."""
    return bool(re.match(r"^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$", bic))


def validate_uetr(uetr: str) -> bool:
    """Format UETR gpi : UUID v4."""
    return bool(re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        uetr.lower(),
    ))


def validate_incident_input(data: dict) -> IncidentInput:
    """Valider un incident – lève ValidationError si invalide."""
    return IncidentInput(**data)
