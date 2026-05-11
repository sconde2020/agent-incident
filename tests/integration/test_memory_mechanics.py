"""Tests d'intégration — mémoire conversationnelle de session."""
import os

import pytest

from db.models import IncidentIn

pytestmark = pytest.mark.integration
from memory.store import MemoryEntry
from tests.integration.conftest import build_config
from agent import Agent

SKIP_NO_KEY = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY non définie — test LLM réel ignoré",
)

_INC_SWIFT_GW = {
    "id": "INC0001001",
    "title": "Connexion SWIFTNet interrompue sur swift-gateway",
    "description": (
        "Le composant swift-gateway ne peut plus établir de connexion avec SWIFTNet. "
        "Les transactions MT103 échouent depuis 14h00 UTC. "
        "Code erreur SWIFT-001 observé dans les logs applicatifs."
    ),
    "service": "swift-gateway",
}

_INC_PAYMENT_HUB = {
    "id": "INC0001002",
    "title": "Payment-hub inaccessible — timeout sur toutes les routes HTTP",
    "description": (
        "Le service payment-hub retourne HTTP 503 sur l'ensemble des routes. "
        "Les paiements SEPA et SWIFT sont bloqués depuis 10 minutes. "
        "Environ 200 paiements en file d'attente non traités."
    ),
    "service": "payment-hub",
}


class TestMemoryMechanics:
    """
    Vérifie que la mémoire de session est correctement alimentée, transmise
    au LLM au tour suivant, tronquée et isolée entre instances.
    """

    def test_memory_empty_at_agent_creation(self, live_agent):
        assert len(live_agent.memory) == 0

    @SKIP_NO_KEY
    def test_memory_grows_after_qualification(self, live_agent):
        live_agent.qualify(IncidentIn(**_INC_SWIFT_GW))
        assert len(live_agent.memory) == 1

    @SKIP_NO_KEY
    def test_memory_contains_correct_qualified_incident_data(self, live_agent):
        result = live_agent.qualify(IncidentIn(**_INC_SWIFT_GW))
        entries = live_agent.memory.to_context()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["service"] == "swift-gateway"
        assert entry["priority"] == result.priority
        assert entry["assigned_to"] == result.assigned_to
        assert 0.0 <= entry["confidence_score"] <= 1.0

    @SKIP_NO_KEY
    def test_memory_context_injected_into_next_llm_prompt(self, live_agent):
        """La mémoire du tour N est bien transmise dans context['memory'] au tour N+1."""
        live_agent.qualify(IncidentIn(**_INC_SWIFT_GW))
        original_build = live_agent.llm._build_prompt
        captured: dict = {}

        def spy(incident, context):
            captured["memory"] = context.get("memory", [])
            return original_build(incident, context)

        live_agent.llm._build_prompt = spy
        live_agent.qualify(IncidentIn(**_INC_PAYMENT_HUB))

        assert len(captured.get("memory", [])) == 1
        assert captured["memory"][0]["service"] == "swift-gateway"

    @SKIP_NO_KEY
    def test_memory_truncated_when_max_size_reached(self, live_agent):
        live_agent.qualify(IncidentIn(**_INC_SWIFT_GW))
        for i in range(3):
            live_agent.memory.add(MemoryEntry(
                incident_id=f"INC000000{i}",
                service="payment-hub",
                title=f"Incident overflow {i}",
                priority="P3",
                category="Application",
                assigned_to="team-ops",
                confidence_score=0.7,
            ))
        assert len(live_agent.memory) == 3

    @SKIP_NO_KEY
    def test_oldest_entry_evicted_first_on_overflow(self, live_agent):
        result = live_agent.qualify(IncidentIn(**_INC_SWIFT_GW))
        first_id = result.id
        for i in range(3):
            live_agent.memory.add(MemoryEntry(
                incident_id=f"INC000000{i}",
                service="payment-hub",
                title=f"Incident overflow {i}",
                priority="P3",
                category="Application",
                assigned_to="team-ops",
                confidence_score=0.7,
            ))
        ids_in_memory = [e["incident_id"] for e in live_agent.memory.to_context()]
        assert first_id not in ids_in_memory

    def test_memory_independent_between_two_agent_instances(self, fresh_db, tmp_path):
        cfg = build_config(fresh_db, str(tmp_path / "chroma"))
        ag1 = Agent(cfg)
        ag2 = Agent(cfg)
        ag1.memory.add(MemoryEntry(
            incident_id="INC0000001",
            service="swift-gateway",
            title="Test isolation",
            priority="P2",
            category="Infrastructure",
            assigned_to="team-swift",
            confidence_score=0.9,
        ))
        assert len(ag1.memory) == 1
        assert len(ag2.memory) == 0

    @SKIP_NO_KEY
    def test_memory_clear_resets_state_to_zero(self, live_agent):
        live_agent.qualify(IncidentIn(**_INC_SWIFT_GW))
        assert len(live_agent.memory) == 1
        live_agent.memory.clear()
        assert len(live_agent.memory) == 0
