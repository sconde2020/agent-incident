import logging

logger = logging.getLogger(__name__)

TOOL_DEFINITION = {
    "name": "get_monitoring_alerts",
    "description": "Récupère les alertes actives et les dernières métriques pour un service donné.",
    "input_schema": {
        "type": "object",
        "properties": {
            "service_name": {"type": "string", "description": "Nom du service"},
        },
        "required": ["service_name"],
    },
}


class SearchMonitoring:
    def __init__(self, monitoring_db):
        self.monitoring = monitoring_db

    def execute(self, service_name: str) -> dict:
        """Retourner alertes actives + métriques pour un service."""
        logger.info("tools.search_monitoring service=%s", service_name)
        alerts = self.monitoring.get_active_alerts(service_name)
        metrics = self.monitoring.get_latest_metrics(service_name)
        return {
            "alerts": alerts,
            "metrics": metrics,
            "alert_count": len(alerts),
            "has_critical_alerts": any(a.get("severity") == "critical" for a in alerts),
        }
