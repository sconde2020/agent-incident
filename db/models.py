from typing import Optional
from pydantic import BaseModel


class IncidentIn(BaseModel):
    """Payload d'entrée pour la qualification d'un incident."""
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


class IncidentOut(BaseModel):
    """Résultat enrichi retourné après qualification par l'agent."""
    id: str
    title: str
    service: str
    priority: str
    category: str
    subcategory: str
    assigned_to: str
    confidence_score: float
    runbooks_suggested: list[str]
    similar_incidents: list[str]
    monitoring_alerts: list[str]
    is_duplicate: bool
    duplicate_of: Optional[str] = None
    is_major_incident: bool
    related_incidents: list[str]
    resolution_hint: Optional[str] = None
    enriched_context: dict


class IncidentCreated(BaseModel):
    """Incident brut retourné après création, avant qualification par l'agent."""
    id: str
    title: str
    description: str
    service: str
    status: str
    priority: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    reported_by: Optional[str] = None
    assigned_to: Optional[str] = None
    created_at: str
    sla_breach_at: Optional[str] = None


class Alert(BaseModel):
    id: str
    service: str
    severity: str
    name: str
    message: str
    triggered_at: str
    status: str
    runbook_url: Optional[str] = None
    labels: Optional[dict] = None


class ServiceInfo(BaseModel):
    id: str
    name: str
    display_name: str
    description: Optional[str] = None
    type: Optional[str] = None
    team: str
    owner: Optional[str] = None
    business_criticality: str
    sla_target_availability: Optional[float] = None
    tier: int
    dependencies: list[str]
    dependents: list[str]


class TeamInfo(BaseModel):
    id: str
    name: str
    slack_channel: str
    oncall_email: str
    services: list[str]
