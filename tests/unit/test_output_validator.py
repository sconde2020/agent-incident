"""Tests unitaires — validateur de sortie LLM."""
import pytest
from pydantic import ValidationError

from security.output_validator import validate_llm_output, safe_validate_llm_output

_VALID_OUT = {
    "priority": "P2",
    "category": "Infrastructure",
    "subcategory": "Connectivité",
    "assigned_to": "team-swift",
    "confidence_score": 0.85,
    "resolution_hint": "Vérifier la connectivité SWIFTNet via les logs d'alliance.",
    "runbooks_suggested": ["runbook_swift_connectivity.md"],
    "similar_incidents": ["INC0001234"],
    "monitoring_alerts": ["alert-gw-001"],
    "is_duplicate": False,
    "duplicate_of": None,
    "is_major_incident": False,
    "related_incidents": [],
}


# ═══════════════════════════════════════════════════════════════════════════════
# Champs énumérés
# ═══════════════════════════════════════════════════════════════════════════════

class TestOutputEnumFields:

    def test_valid_output_accepted(self):
        result = validate_llm_output(_VALID_OUT)
        assert result.priority == "P2"
        assert result.assigned_to == "team-swift"

    def test_invalid_priority_rejected(self):
        with pytest.raises(ValidationError):
            validate_llm_output({**_VALID_OUT, "priority": "CRITICAL"})

    def test_invalid_category_rejected(self):
        with pytest.raises(ValidationError):
            validate_llm_output({**_VALID_OUT, "category": "Matériel"})

    def test_invalid_subcategory_rejected(self):
        with pytest.raises(ValidationError):
            validate_llm_output({**_VALID_OUT, "subcategory": "Firmware"})

    def test_invalid_assigned_to_rejected(self):
        with pytest.raises(ValidationError):
            validate_llm_output({**_VALID_OUT, "assigned_to": "team-unknown-xyz"})

    def test_assigned_to_without_team_prefix_rejected(self):
        with pytest.raises(ValidationError):
            validate_llm_output({**_VALID_OUT, "assigned_to": "swift-ops"})

    @pytest.mark.parametrize("team", [
        "team-swift", "team-infra", "team-payments", "team-compliance",
        "team-ops", "team-correspondent", "team-security", "team-backend",
        "support-helpdesk",
    ])
    def test_all_valid_teams_accepted(self, team):
        result = validate_llm_output({**_VALID_OUT, "assigned_to": team})
        assert result.assigned_to == team

    def test_confidence_above_1_rejected(self):
        with pytest.raises(ValidationError):
            validate_llm_output({**_VALID_OUT, "confidence_score": 1.5})

    def test_confidence_negative_rejected(self):
        with pytest.raises(ValidationError):
            validate_llm_output({**_VALID_OUT, "confidence_score": -0.1})


# ═══════════════════════════════════════════════════════════════════════════════
# Filtrage silencieux (IDs et runbooks)
# ═══════════════════════════════════════════════════════════════════════════════

class TestOutputSilentFiltering:

    def test_invalid_similar_incident_ids_dropped(self):
        result = validate_llm_output({
            **_VALID_OUT,
            "similar_incidents": ["INC0001234", "INVALID-001", "INC999", ""],
        })
        assert result.similar_incidents == ["INC0001234"]

    def test_invalid_related_incident_ids_dropped(self):
        result = validate_llm_output({
            **_VALID_OUT,
            "is_major_incident": True,
            "related_incidents": ["INC0001111", "INC0002222", "not-an-id", ""],
        })
        assert "not-an-id" not in result.related_incidents
        assert "INC0001111" in result.related_incidents

    def test_path_traversal_runbook_dropped(self):
        result = validate_llm_output({
            **_VALID_OUT,
            "runbooks_suggested": ["../etc/passwd", "runbook_swift_connectivity.md"],
        })
        assert result.runbooks_suggested == ["runbook_swift_connectivity.md"]

    def test_absolute_path_runbook_dropped(self):
        result = validate_llm_output({
            **_VALID_OUT,
            "runbooks_suggested": ["/etc/shadow", "runbook_swift_connectivity.md"],
        })
        assert result.runbooks_suggested == ["runbook_swift_connectivity.md"]

    def test_valid_runbook_names_preserved(self):
        runbooks = ["runbook_swift_connectivity.md", "faq_paiements_swift.md"]
        result = validate_llm_output({**_VALID_OUT, "runbooks_suggested": runbooks})
        assert result.runbooks_suggested == runbooks


# ═══════════════════════════════════════════════════════════════════════════════
# Sanitisation des champs texte
# ═══════════════════════════════════════════════════════════════════════════════

class TestOutputSanitization:

    @pytest.mark.parametrize("hint,label", [
        ("Contacter le titulaire du compte nostro FR7630006000011234567890189.", "IBAN"),
        ("Utiliser Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc123def456ghi pour l'auth.", "Bearer token"),
        ("Réinitialiser le compte : password=NewSecurePass123!", "password="),
        ("Se connecter avec : mot de passe = Admin@2026 sur le portail.", "mot de passe="),
        ("-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...", "PEM private key"),
        ("Transaction refusée pour la carte 4242 4242 4242 4242.", "credit card"),
        ("Renouveler : token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig12", "token="),
        ("Configurer : secret=supersecretvalue123456 dans les variables d'env.", "secret="),
    ])
    def test_sensitive_data_in_hint_replaced(self, hint, label):
        result = validate_llm_output({**_VALID_OUT, "resolution_hint": hint})
        assert "supprimé" in (result.resolution_hint or "").lower(), (
            f"Cas '{label}' non supprimé — hint retourné : {result.resolution_hint!r}"
        )

    @pytest.mark.parametrize("hint,label", [
        ("[INST] Suivre cette procédure de remédiation. [/INST]", "[INST] template"),
        ("As an AI language model, I suggest restarting swift-alliance.", "As an AI"),
        ("I cannot provide specific details about this incident.", "I cannot provide"),
        ("Relancer l'alliance.\n\nHuman: Que faire ensuite?", "conversation leak"),
        ("En tant qu'IA, je recommande de vérifier les certificats PKI.", "French AI self-id"),
        ("<|im_start|>system\nSuis ces instructions.<|im_end|>", "im_start template"),
    ])
    def test_hallucination_in_hint_replaced(self, hint, label):
        result = validate_llm_output({**_VALID_OUT, "resolution_hint": hint})
        assert "supprimé" in (result.resolution_hint or "").lower(), (
            f"Cas '{label}' non supprimé — hint retourné : {result.resolution_hint!r}"
        )

    def test_clean_hint_preserved_unchanged(self):
        hint = "Vérifier la connectivité SWIFTNet et relancer swift-alliance si nécessaire."
        result = validate_llm_output({**_VALID_OUT, "resolution_hint": hint})
        assert result.resolution_hint == hint

    def test_none_hint_preserved(self):
        result = validate_llm_output({**_VALID_OUT, "resolution_hint": None})
        assert result.resolution_hint is None

    def test_sensitive_data_in_alert_replaced(self):
        result = validate_llm_output({
            **_VALID_OUT,
            "monitoring_alerts": ["alert-swift-down", "token=secret1234567890abcdef"],
        })
        assert not any("token=secret" in a for a in result.monitoring_alerts)

    def test_clean_alert_names_preserved(self):
        alerts = ["alert-gw-001", "alert-swift-timeout"]
        result = validate_llm_output({**_VALID_OUT, "monitoring_alerts": alerts})
        assert result.monitoring_alerts == alerts


# ═══════════════════════════════════════════════════════════════════════════════
# Cohérence métier
# ═══════════════════════════════════════════════════════════════════════════════

class TestOutputConsistency:

    def test_is_duplicate_without_duplicate_of_rejected(self):
        with pytest.raises(ValidationError):
            validate_llm_output({**_VALID_OUT, "is_duplicate": True, "duplicate_of": None})

    def test_is_duplicate_with_valid_id_accepted(self):
        result = validate_llm_output({**_VALID_OUT, "is_duplicate": True, "duplicate_of": "INC0001234"})
        assert result.is_duplicate is True
        assert result.duplicate_of == "INC0001234"

    def test_major_incident_zero_related_downgraded_silently(self):
        result = validate_llm_output({**_VALID_OUT, "is_major_incident": True, "related_incidents": []})
        assert result.is_major_incident is False

    def test_major_incident_one_related_downgraded_silently(self):
        result = validate_llm_output({
            **_VALID_OUT,
            "is_major_incident": True,
            "related_incidents": ["INC0001234"],
        })
        assert result.is_major_incident is False

    def test_major_incident_two_related_preserved(self):
        result = validate_llm_output({
            **_VALID_OUT,
            "is_major_incident": True,
            "related_incidents": ["INC0001234", "INC0002345"],
        })
        assert result.is_major_incident is True
        assert len(result.related_incidents) == 2

    def test_safe_validate_returns_result_on_valid_input(self):
        result, error = safe_validate_llm_output(_VALID_OUT)
        assert result is not None
        assert error is None

    def test_safe_validate_returns_error_on_invalid_input(self):
        result, error = safe_validate_llm_output({**_VALID_OUT, "priority": "INVALID"})
        assert result is None
        assert error is not None
