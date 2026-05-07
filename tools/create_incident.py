import logging

logger = logging.getLogger(__name__)

TOOL_DEFINITION = {
    "name": "create_incident",
    "description": "Crée un nouvel incident brut dans la base de données SQLite afin de simuler un cas réel avant qualification.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Titre court de l'incident"},
            "description": {"type": "string", "description": "Description détaillée"},
            "service": {"type": "string", "description": "Identifiant du service concerné"},
            "status": {"type": "string", "default": "open"},
            "priority": {"type": "string", "description": "P1, P2, P3 ou P4"},
            "category": {"type": "string"},
            "subcategory": {"type": "string"},
            "reported_by": {"type": "string", "description": "Email ou identifiant team-xxx"},
            "assigned_to": {"type": "string", "description": "Email ou identifiant team-xxx"},
            "sla_breach_at": {"type": "string", "description": "ISO 8601"},
        },
        "required": ["title", "description", "service"],
    },
}


class CreateIncident:
    def __init__(self, incident_db):
        self.db = incident_db

    def execute(self, **incident_data: dict) -> dict:
        """Persister un incident brut en base et retourner l'identifiant généré."""
        logger.info("tools.create_incident service=%s", incident_data.get("service"))
        try:
            created = self.db.create(incident_data)
            return {"success": True, "incident_id": created["id"], "incident": created}
        except Exception as exc:
            logger.error("tools.create_incident.failed error=%s", exc)
            return {"success": False, "error": str(exc)}
