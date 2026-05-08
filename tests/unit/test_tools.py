"""Tests unitaires — outils de l'agent (function calling)."""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from tools.search_cmdb import SearchCMDB
from tools.search_monitoring import SearchMonitoring
from tools.search_incidents import SearchIncidents
from tools.detect_duplicate import DetectDuplicate
from tools.detect_major_incident import DetectMajorIncident
from tools.update_incident import UpdateIncident
from tools.classify import Classify
from tools.route import Route
from tools.create_incident import CreateIncident


def _iso_ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


# ═══════════════════════════════════════════════════════════════════════════════
# SearchCMDB
# ═══════════════════════════════════════════════════════════════════════════════

class TestSearchCMDB:

    def _tool(self, service_data=None) -> SearchCMDB:
        cmdb = MagicMock()
        cmdb.get_service.return_value = service_data
        return SearchCMDB(cmdb)

    def test_nominal_returns_service_data(self):
        tool = self._tool({"name": "swift-gateway", "tier": 1, "team": "team-swift"})
        result = tool.execute("swift-gateway")
        assert result["name"] == "swift-gateway"

    def test_service_not_found_returns_error_dict(self):
        result = self._tool(None).execute("unknown-service")
        assert "error" in result
        assert result["service"] == "unknown-service"

    def test_empty_name_no_crash(self):
        result = self._tool(None).execute("")
        assert "error" in result


# ═══════════════════════════════════════════════════════════════════════════════
# SearchMonitoring
# ═══════════════════════════════════════════════════════════════════════════════

class TestSearchMonitoring:

    def _tool(self, alerts=None, metrics=None) -> SearchMonitoring:
        monitoring = MagicMock()
        monitoring.get_active_alerts.return_value = alerts or []
        monitoring.get_latest_metrics.return_value = metrics
        return SearchMonitoring(monitoring)

    def test_nominal_returns_counts_and_alerts(self):
        tool = self._tool(alerts=[{"id": "a1", "severity": "warning"}])
        result = tool.execute("swift-gateway")
        assert result["alert_count"] == 1
        assert result["has_critical_alerts"] is False

    def test_no_alerts_returns_zero_count(self):
        result = self._tool().execute("unknown-svc")
        assert result["alert_count"] == 0

    def test_critical_alert_sets_flag_to_true(self):
        tool = self._tool(alerts=[{"id": "a1", "severity": "critical"}])
        result = tool.execute("payment-hub")
        assert result["has_critical_alerts"] is True

    def test_mixed_severities_critical_wins(self):
        alerts = [{"id": "a1", "severity": "warning"}, {"id": "a2", "severity": "critical"}]
        result = self._tool(alerts=alerts).execute("svc")
        assert result["has_critical_alerts"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# SearchIncidents
# ═══════════════════════════════════════════════════════════════════════════════

class TestSearchIncidents:

    def test_nominal_returns_list(self):
        db = MagicMock()
        db.search_similar.return_value = [{"id": "INC0001000", "title": "test"}]
        result = SearchIncidents(db, search_limit=5).execute("swift-gateway", "paiements bloqués")
        assert len(result) == 1

    def test_empty_result_no_crash(self):
        db = MagicMock()
        db.search_similar.return_value = []
        assert SearchIncidents(db).execute("unknown-svc", "incident") == []

    def test_search_limit_forwarded_to_db(self):
        db = MagicMock()
        db.search_similar.return_value = []
        SearchIncidents(db, search_limit=7).execute("svc", "title")
        db.search_similar.assert_called_once_with(service="svc", title="title", limit=7)


# ═══════════════════════════════════════════════════════════════════════════════
# DetectDuplicate
# ═══════════════════════════════════════════════════════════════════════════════

class TestDetectDuplicate:

    def test_duplicate_detected_within_window(self):
        db = MagicMock()
        db.search_similar.return_value = [{"id": "INC0001000", "created_at": _iso_ago(0.5)}]
        result = DetectDuplicate(db, window_hours=2).execute("swift-gateway", "paiements bloqués")
        assert result["is_duplicate"] is True
        assert result["duplicate_of"] == "INC0001000"

    def test_no_duplicate_when_incident_too_old(self):
        db = MagicMock()
        db.search_similar.return_value = [{"id": "INC0001000", "created_at": _iso_ago(3)}]
        result = DetectDuplicate(db, window_hours=2).execute("swift-gateway", "test")
        assert result["is_duplicate"] is False

    def test_empty_db_returns_no_duplicate(self):
        db = MagicMock()
        db.search_similar.return_value = []
        result = DetectDuplicate(db, window_hours=2).execute("svc", "title")
        assert result["is_duplicate"] is False
        assert result["candidates"] == []

    def test_invalid_date_excluded_no_crash(self):
        db = MagicMock()
        db.search_similar.return_value = [{"id": "INC0001000", "created_at": "NOT_A_DATE"}]
        result = DetectDuplicate(db, window_hours=2).execute("svc", "title")
        assert result["is_duplicate"] is False

    def test_candidates_list_populated(self):
        db = MagicMock()
        db.search_similar.return_value = [
            {"id": "INC0001000", "created_at": _iso_ago(0.5)},
            {"id": "INC0001001", "created_at": _iso_ago(1.0)},
        ]
        result = DetectDuplicate(db, window_hours=2).execute("svc", "title")
        assert set(result["candidates"]) == {"INC0001000", "INC0001001"}


# ═══════════════════════════════════════════════════════════════════════════════
# DetectMajorIncident
# ═══════════════════════════════════════════════════════════════════════════════

class TestDetectMajorIncident:

    def test_not_major_when_below_threshold(self):
        db = MagicMock()
        db.search_similar.return_value = [{"id": "INC0001000"}]
        result = DetectMajorIncident(db, threshold=3).execute("swift-gateway", [])
        assert result["is_major_incident"] is False

    def test_major_detected_when_threshold_reached(self):
        db = MagicMock()
        db.search_similar.return_value = [{"id": "INC0001000"}]
        result = DetectMajorIncident(db, threshold=2).execute("payment-hub", ["payment-router"])
        assert result["is_major_incident"] is True

    def test_no_dependencies_only_one_db_call(self):
        db = MagicMock()
        db.search_similar.return_value = [{"id": "INC0001000"}]
        DetectMajorIncident(db, threshold=3).execute("swift-gateway", [])
        assert db.search_similar.call_count == 1

    def test_related_incidents_are_deduplicated(self):
        db = MagicMock()
        db.search_similar.return_value = [{"id": "INC0001000"}]
        result = DetectMajorIncident(db, threshold=2).execute("svc-a", ["svc-b"])
        ids = result["related_incidents"]
        assert len(ids) == len(set(ids))

    def test_empty_db_returns_not_major(self):
        db = MagicMock()
        db.search_similar.return_value = []
        result = DetectMajorIncident(db, threshold=2).execute("swift-gateway", ["fin-processor"])
        assert result["is_major_incident"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# UpdateIncident
# ═══════════════════════════════════════════════════════════════════════════════

class TestUpdateIncident:

    def test_nominal_returns_success(self):
        db = MagicMock()
        result = UpdateIncident(db).execute("INC0001234", {"priority": "P2"})
        assert result["success"] is True
        assert result["incident_id"] == "INC0001234"

    def test_db_called_with_correct_args(self):
        db = MagicMock()
        qualification = {"priority": "P1", "category": "Infrastructure"}
        UpdateIncident(db).execute("INC0001234", qualification)
        db.update_qualification.assert_called_once_with("INC0001234", qualification)

    def test_db_error_returns_failure_dict(self):
        db = MagicMock()
        db.update_qualification.side_effect = Exception("disk full")
        result = UpdateIncident(db).execute("INC0001234", {"priority": "P2"})
        assert result["success"] is False
        assert "disk full" in result["error"]


# ═══════════════════════════════════════════════════════════════════════════════
# Classify
# ═══════════════════════════════════════════════════════════════════════════════

class TestClassify:

    def test_nominal_returns_all_fields(self):
        result = Classify().execute(
            priority="P2", category="Application",
            subcategory="Traitement", confidence_score=0.8,
        )
        assert result == {
            "priority": "P2",
            "category": "Application",
            "subcategory": "Traitement",
            "confidence_score": 0.8,
        }

    @pytest.mark.parametrize("priority", ["P1", "P2", "P3", "P4"])
    def test_all_priorities_accepted(self, priority):
        result = Classify().execute(
            priority=priority, category="Infrastructure",
            subcategory="Connectivité", confidence_score=0.9,
        )
        assert result["priority"] == priority

    def test_confidence_score_preserved(self):
        result = Classify().execute(
            priority="P3", category="Opérationnel",
            subcategory="Réconciliation", confidence_score=0.42,
        )
        assert result["confidence_score"] == pytest.approx(0.42)


# ═══════════════════════════════════════════════════════════════════════════════
# Route
# ═══════════════════════════════════════════════════════════════════════════════

class TestRoute:

    def test_llm_suggestion_preferred_over_matrix(self):
        assert Route().execute("swift-gateway", llm_assigned_to="team-payments") == "team-payments"

    def test_matrix_used_when_no_llm_suggestion(self):
        assert Route().execute("swift-gateway") == "team-swift"

    def test_unknown_service_defaults_to_team_ops(self):
        assert Route().execute("unknown-service-xyz") == "team-ops"

    def test_llm_suggestion_without_team_prefix_falls_back(self):
        assert Route().execute("swift-gateway", llm_assigned_to="some-group") == "team-swift"

    def test_known_payment_service_routes_correctly(self):
        assert Route().execute("payment-hub") == "team-payments"


# ═══════════════════════════════════════════════════════════════════════════════
# CreateIncident
# ═══════════════════════════════════════════════════════════════════════════════

class TestCreateIncident:

    def test_nominal_returns_success_with_id(self):
        db = MagicMock()
        db.create.return_value = {"id": "INC0001234", "title": "test", "service": "svc"}
        result = CreateIncident(db).execute(title="test", description="desc", service="svc")
        assert result["success"] is True
        assert result["incident_id"] == "INC0001234"

    def test_db_called_with_incident_data(self):
        db = MagicMock()
        db.create.return_value = {"id": "INC0001234"}
        CreateIncident(db).execute(title="t", description="d", service="svc")
        db.create.assert_called_once()

    def test_db_error_returns_failure_dict(self):
        db = MagicMock()
        db.create.side_effect = Exception("constraint violation")
        result = CreateIncident(db).execute(title="t", description="d", service="s")
        assert result["success"] is False
        assert "constraint violation" in result["error"]
