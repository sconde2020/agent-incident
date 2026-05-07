import logging

logger = logging.getLogger(__name__)

TOOL_DEFINITION = {
    "name": "check_major_incident",
    "description": "Détecte si plusieurs incidents ouverts sur des services liés constituent un incident majeur.",
    "input_schema": {
        "type": "object",
        "properties": {
            "service": {"type": "string"},
            "dependencies": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Services dépendants ou dépendances du service impacté",
            },
            "threshold": {"type": "integer", "default": 3},
        },
        "required": ["service", "dependencies"],
    },
}


class DetectMajorIncident:
    def __init__(self, incident_db, threshold: int = 3):
        self.db = incident_db
        self.threshold = threshold

    def execute(self, service: str, dependencies: list) -> dict:
        """
        Corréler les incidents ouverts sur le service et ses dépendances.
        Si >= threshold services sont simultanément impactés → incident majeur.
        """
        logger.info("tools.detect_major_incident service=%s threshold=%d", service, self.threshold)

        affected_services = []
        related_ids = []

        # Vérifier le service principal
        main_incidents = self.db.search_similar(
            service=service, title="", limit=5, statuses=("open", "in_progress")
        )
        if main_incidents:
            affected_services.append(service)
            related_ids.extend(i["id"] for i in main_incidents[:3])

        # Vérifier les dépendances – limiter à 10 pour éviter des requêtes trop larges
        for dep in list(dependencies)[:10]:
            dep_incidents = self.db.search_similar(
                service=dep, title="", limit=3, statuses=("open", "in_progress")
            )
            if dep_incidents:
                affected_services.append(dep)
                related_ids.extend(i["id"] for i in dep_incidents[:2])

        is_major = len(affected_services) >= self.threshold

        if is_major:
            logger.warning(
                "tools.detect_major_incident.found services=%s", affected_services
            )

        return {
            "is_major_incident": is_major,
            "affected_services": affected_services,
            # dict.fromkeys préserve l'ordre et dédoublonne sans set
            "related_incidents": list(dict.fromkeys(related_ids)),
        }
