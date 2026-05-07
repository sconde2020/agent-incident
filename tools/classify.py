import logging

logger = logging.getLogger(__name__)

TOOL_DEFINITION = {
    "name": "classify_incident",
    "description": "Assigne la priorité, la catégorie et la sous-catégorie à un incident.",
    "input_schema": {
        "type": "object",
        "properties": {
            "priority": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
            "category": {"type": "string"},
            "subcategory": {"type": "string"},
            "confidence_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "required": ["priority", "category", "subcategory", "confidence_score"],
    },
}


class Classify:
    """Applique la classification retournée par le LLM à l'incident."""

    def execute(
        self, priority: str, category: str, subcategory: str, confidence_score: float
    ) -> dict:
        logger.info(
            "tools.classify priority=%s category=%s confidence=%.2f",
            priority, category, confidence_score,
        )
        return {
            "priority": priority,
            "category": category,
            "subcategory": subcategory,
            "confidence_score": confidence_score,
        }
