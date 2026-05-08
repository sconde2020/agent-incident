"""Tests unitaires — mémoire conversationnelle."""
import pytest
from memory.store import ConversationMemory, MemoryEntry


@pytest.fixture
def memory():
    return ConversationMemory(max_size=3)


def _make_entry(incident_id: str = "INC0001234", **kwargs) -> MemoryEntry:
    defaults = dict(
        service="swift-gateway",
        title="Paiements bloqués",
        priority="P2",
        category="Application",
        assigned_to="team-swift",
        confidence_score=0.85,
    )
    return MemoryEntry(incident_id=incident_id, **{**defaults, **kwargs})


class TestConversationMemory:

    def test_add_and_recall_basic(self, memory):
        memory.add(_make_entry("INC0001234"))
        assert memory.get_recent()[0].incident_id == "INC0001234"

    def test_len_tracks_size(self, memory):
        memory.add(_make_entry())
        assert len(memory) == 1

    def test_to_context_contains_required_fields(self, memory):
        memory.add(_make_entry())
        ctx = memory.to_context()[0]
        for field in ("incident_id", "service", "priority", "category", "assigned_to", "confidence_score"):
            assert field in ctx

    def test_get_recent_with_k_limits_results(self, memory):
        for i in range(3):
            memory.add(_make_entry(f"INC000000{i}"))
        assert len(memory.get_recent(k=2)) == 2

    def test_max_memory_not_exceeded(self, memory):
        for i in range(5):
            memory.add(_make_entry(f"INC000000{i}"))
        assert len(memory) == 3

    def test_eviction_is_fifo_oldest_dropped(self, memory):
        for i in range(4):
            memory.add(_make_entry(f"INC000000{i}"))
        ids = [e.incident_id for e in memory.get_recent()]
        assert "INC0000000" not in ids

    def test_newest_entry_always_present(self, memory):
        for i in range(5):
            memory.add(_make_entry(f"INC000000{i}"))
        assert memory.get_recent()[-1].incident_id == "INC0000004"

    def test_clear_empties_memory(self, memory):
        memory.add(_make_entry())
        memory.clear()
        assert len(memory) == 0

    def test_clear_then_add_works(self, memory):
        memory.add(_make_entry("INC0001111"))
        memory.clear()
        memory.add(_make_entry("INC0002222"))
        assert memory.get_recent()[0].incident_id == "INC0002222"

    def test_empty_memory_to_context_returns_empty_list(self, memory):
        assert memory.to_context() == []

    def test_empty_get_recent_returns_empty_list(self, memory):
        assert memory.get_recent() == []
