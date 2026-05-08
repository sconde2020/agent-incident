"""
Tests d'intégration — mécaniques du pipeline de qualification.

Objectif : vérifier que le bon outil est appelé au bon moment et que les données
remontent correctement dans IncidentOut. Le LLM réel est appelé mais la qualité
de la réponse n'est pas évaluée — uniquement la mécanique.
"""
import os
import time

import pytest

from db.models import IncidentIn

pytestmark = pytest.mark.integration

SKIP_NO_KEY = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY non définie — test LLM réel ignoré",
)

_INC_SWIFT_GW = {
    "title": "Connexion SWIFTNet interrompue sur swift-gateway",
    "description": (
        "Le composant swift-gateway ne peut plus établir de connexion avec SWIFTNet. "
        "Les transactions MT103 échouent depuis 14h00 UTC. "
        "Code erreur SWIFT-001 observé dans les logs applicatifs."
    ),
    "service": "swift-gateway",
}

_INC_PAYMENT_HUB = {
    "title": "Payment-hub inaccessible — timeout sur toutes les routes HTTP",
    "description": (
        "Le service payment-hub retourne HTTP 503 sur l'ensemble des routes. "
        "Les paiements SEPA et SWIFT sont bloqués depuis 10 minutes. "
        "Environ 200 paiements en file d'attente non traités."
    ),
    "service": "payment-hub",
}

_INC_UNKNOWN_SVC = {
    "title": "Anomalie de traitement sur service non référencé",
    "description": (
        "Le composant legacy-processor rencontre des erreurs de traitement "
        "non documentées. Ce service est absent de la CMDB."
    ),
    "service": "legacy-processor",
}

_INC_OUT_OF_DOMAIN = {
    "title": "Imprimante du bureau hors service depuis ce matin",
    "description": (
        "L'imprimante HP LaserJet du bureau des ressources humaines ne fonctionne plus. "
        "Le bac papier est vide et le toner est épuisé. "
        "Aucun lien avec les systèmes de paiement SWIFT."
    ),
    "service": "support-desk",
}


class TestPipelineMechanics:
    """
    Vérifie que chaque outil du pipeline est appelé au bon moment et que
    ses données remontent correctement dans IncidentOut.
    """

    @SKIP_NO_KEY
    def test_full_pipeline_returns_valid_structured_output(self, live_agent):
        result = live_agent.qualify(IncidentIn(**_INC_SWIFT_GW))
        assert result.priority in {"P1", "P2", "P3", "P4"}
        assert result.category in {"Infrastructure", "Application", "Opérationnel", "Conformité", "Sécurité"}
        assert result.assigned_to.startswith("team-")
        assert 0.0 <= result.confidence_score <= 1.0

    @SKIP_NO_KEY
    def test_cmdb_tool_enriches_output_with_service_tier(self, live_agent):
        result = live_agent.qualify(IncidentIn(**_INC_SWIFT_GW))
        assert result.enriched_context["service_tier"] == 1
        assert result.enriched_context["business_criticality"] == "critical"

    @SKIP_NO_KEY
    def test_monitoring_tool_populates_alerts_in_output(self, live_agent):
        result = live_agent.qualify(IncidentIn(**_INC_SWIFT_GW))
        assert result.enriched_context["has_critical_alerts"] is True
        assert result.enriched_context["active_alerts"] >= 1
        assert len(result.monitoring_alerts) > 0

    def test_duplicate_shortcut_sets_is_duplicate_true(self, dup_agent):
        """Doublon détecté → shortcut pris, is_duplicate=True, duplicate_of renseigné. Aucun appel LLM."""
        result = dup_agent.qualify(IncidentIn(**_INC_SWIFT_GW))
        assert result.is_duplicate is True
        assert result.duplicate_of == "INC9990001"

    def test_duplicate_shortcut_skips_llm_classify(self, dup_agent):
        """Le chemin doublon n'appelle PAS llm.classify : runbooks vides et confidence fixée."""
        result = dup_agent.qualify(IncidentIn(**_INC_SWIFT_GW))
        assert result.is_duplicate is True
        assert result.runbooks_suggested == []
        assert result.confidence_score == pytest.approx(0.95)

    def test_duplicate_inherits_priority_and_team_from_original(self, dup_agent):
        result = dup_agent.qualify(IncidentIn(**_INC_SWIFT_GW))
        assert result.priority == "P2"
        assert result.assigned_to == "team-swift"

    @SKIP_NO_KEY
    def test_unknown_service_routes_to_team_ops_and_no_cmdb_tier(self, live_agent):
        result = live_agent.qualify(IncidentIn(**_INC_UNKNOWN_SVC))
        assert result.assigned_to == "team-ops"
        assert result.enriched_context["service_tier"] is None

    @SKIP_NO_KEY
    def test_payment_service_routed_to_team_payments(self, live_agent):
        result = live_agent.qualify(IncidentIn(**_INC_PAYMENT_HUB))
        assert result.assigned_to == "team-payments"

    @SKIP_NO_KEY
    def test_out_of_domain_incident_has_low_confidence_and_no_runbooks(self, live_agent):
        result = live_agent.qualify(IncidentIn(**_INC_OUT_OF_DOMAIN))
        assert result.confidence_score < 0.5
        assert result.runbooks_suggested == []

    @SKIP_NO_KEY
    def test_pipeline_response_time_under_30_seconds(self, live_agent):
        t0 = time.monotonic()
        live_agent.qualify(IncidentIn(**_INC_SWIFT_GW))
        assert time.monotonic() - t0 < 30.0
