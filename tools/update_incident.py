import logging

logger = logging.getLogger(__name__)

TOOL_DEFINITION = {
    "name": "update_incident",
    "description": "Met à jour le ticket d'incident dans la base de données SQLite avec la qualification complète.",
    "input_schema": {
        "type": "object",
        "properties": {
            "incident_id": {"type": "string"},
            "qualification": {"type": "object"},
        },
        "required": ["incident_id", "qualification"],
    },
}


class UpdateIncident:
    def __init__(self, incident_db):
        self.db = incident_db

    def execute(self, incident_id: str, qualification: dict) -> dict:
        """Persister la qualification dans SQLite."""
        logger.info("tools.update_incident incident_id=%s", incident_id)
        try:
            self.db.update_qualification(incident_id, qualification)
            return {"success": True, "incident_id": incident_id}
        except Exception as exc:
            logger.error("tools.update_incident.failed incident_id=%s error=%s", incident_id, exc)
            return {"success": False, "error": str(exc)}
