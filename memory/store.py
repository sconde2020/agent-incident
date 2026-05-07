import logging
from collections import deque
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    incident_id: str
    service: str
    title: str
    priority: str
    category: str
    assigned_to: str
    confidence_score: float
    is_duplicate: bool = False
    is_major_incident: bool = False


class ConversationMemory:
    """
    Fenêtre glissante des dernières qualifications de la session courante.
    Taille bornée par MAX_MEMORY pour éviter une croissance non contrôlée du contexte LLM.
    """

    def __init__(self, max_size: int = 10):
        self.max_size = max_size
        self._entries: deque[MemoryEntry] = deque(maxlen=max_size)

    def add(self, entry: MemoryEntry) -> None:
        logger.info(
            "memory.add incident_id=%s size=%d/%d",
            entry.incident_id, len(self._entries) + 1, self.max_size,
        )
        self._entries.append(entry)

    def get_recent(self, k: Optional[int] = None) -> list[MemoryEntry]:
        entries = list(self._entries)
        return entries[-k:] if k else entries

    def to_context(self) -> list[dict]:
        return [
            {
                "incident_id": e.incident_id,
                "service": e.service,
                "title": e.title,
                "priority": e.priority,
                "category": e.category,
                "assigned_to": e.assigned_to,
                "confidence_score": e.confidence_score,
                "is_duplicate": e.is_duplicate,
                "is_major_incident": e.is_major_incident,
            }
            for e in self._entries
        ]

    def clear(self) -> None:
        logger.info("memory.clear size=%d", len(self._entries))
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)