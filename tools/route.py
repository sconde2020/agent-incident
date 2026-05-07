import logging
from typing import Optional

logger = logging.getLogger(__name__)

TOOL_DEFINITION = {
    "name": "route_to_team",
    "description": "Détermine l'équipe assignée selon le service et la catégorie de l'incident.",
    "input_schema": {
        "type": "object",
        "properties": {
            "assigned_to": {"type": "string", "description": "Identifiant de l'équipe (ex: team-swift)"},
        },
        "required": ["assigned_to"],
    },
}

# Matrice de routage statique – utilisée en fallback si le LLM ne fournit pas d'équipe valide
_ROUTING_MATRIX: dict[str, str] = {
    "swift-gateway": "team-swift",
    "fin-processor": "team-swift",
    "bic-validator": "team-swift",
    "gpi-tracker": "team-swift",
    "mt-parser": "team-swift",
    "swift-alliance": "team-infra",
    "payment-hub": "team-payments",
    "payment-router": "team-payments",
    "payments-api": "team-payments",
    "sanctions-screening": "team-compliance",
    "nostro-reconciliation": "team-ops",
    "liquidity-manager": "team-ops",
    "cut-off-manager": "team-ops",
    "correspondent-service": "team-correspondent",
    "auth-service": "team-security",
    "orders-api": "team-backend",
    "catalog-service": "team-catalog",
    "notification-service": "team-backend",
}


class Route:
    def execute(self, service: str, llm_assigned_to: Optional[str] = None) -> str:
        """
        Retourner l'équipe cible.
        Priorité : suggestion LLM → matrice statique → fallback team-ops.
        """
        if llm_assigned_to and llm_assigned_to.startswith("team-"):
            logger.info("tools.route.llm team=%s", llm_assigned_to)
            return llm_assigned_to

        team = _ROUTING_MATRIX.get(service, "team-ops")
        logger.info("tools.route.matrix service=%s team=%s", service, team)
        return team
