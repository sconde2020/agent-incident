import logging

logger = logging.getLogger(__name__)

TOOL_DEFINITION = {
    "name": "get_service_info",
    "description": "Retourne les informations CMDB d'un service : criticité, tier, dépendances, équipe responsable.",
    "input_schema": {
        "type": "object",
        "properties": {
            "service_name": {"type": "string", "description": "Nom du service (ex: swift-gateway)"},
        },
        "required": ["service_name"],
    },
}


class SearchCMDB:
    def __init__(self, cmdb):
        self.cmdb = cmdb

    def execute(self, service_name: str) -> dict:
        """Retourner les infos CMDB d'un service."""
        logger.info("tools.search_cmdb service=%s", service_name)
        result = self.cmdb.get_service(service_name)
        if not result:
            return {"error": f"Service '{service_name}' non trouvé dans la CMDB", "service": service_name}
        return result
