import logging

logger = logging.getLogger(__name__)

TOOL_DEFINITION = {
    "name": "search_similar_incidents",
    "description": "Recherche des incidents similaires dans l'historique ITSM par service.",
    "input_schema": {
        "type": "object",
        "properties": {
            "service": {"type": "string"},
            "title": {"type": "string", "description": "Titre de l'incident à rechercher"},
            "limit": {"type": "integer", "default": 5},
        },
        "required": ["service", "title"],
    },
}


class SearchIncidents:
    def __init__(self, incident_db):
        self.db = incident_db

    def execute(self, service: str, title: str, limit: int = 5) -> list[dict]:
        """Retourner les incidents récents pour un service donné."""
        logger.info("tools.search_incidents service=%s", service)
        return self.db.search_similar(service=service, title=title, limit=limit)
