"""Unit tests for cdk_factory.introspection.drift_detector.

Tests cover drift detection between generated and manual service maps,
including no-drift, one-directional drift, bidirectional drift, and
empty map edge cases.
"""

import pytest

from cdk_factory.introspection.drift_detector import DriftReport, detect_drift


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service_map(*service_keys: str) -> dict:
    """Build a minimal service map dict with the given service keys."""
    return {
        "services": {key: {"description": f"Service {key}"} for key in service_keys},
    }


# ---------------------------------------------------------------------------
# Tests: no drift
# ---------------------------------------------------------------------------


class TestNoDrift:
    def test_identical_service_keys(self):
        generated = _make_service_map("admission", "orchestrator", "packaging")
        manual = _make_service_map("admission", "orchestrator", "packaging")

        report = detect_drift(generated, manual)

        assert report.has_drift is False
        assert report.in_generated_not_manual == []
        assert report.in_manual_not_generated == []

    def test_single_matching_service(self):
        generated = _make_service_map("admission")
        manual = _make_service_map("admission")

        report = detect_drift(generated, manual)

        assert report.has_drift is False
        assert report.in_generated_not_manual == []
        assert report.in_manual_not_generated == []


# ---------------------------------------------------------------------------
# Tests: generated has extra services
# ---------------------------------------------------------------------------


class TestGeneratedHasExtras:
    def test_one_extra_in_generated(self):
        generated = _make_service_map("admission", "orchestrator", "new_service")
        manual = _make_service_map("admission", "orchestrator")

        report = detect_drift(generated, manual)

        assert report.has_drift is True
        assert report.in_generated_not_manual == ["new_service"]
        assert report.in_manual_not_generated == []

    def test_multiple_extras_in_generated(self):
        generated = _make_service_map("admission", "orchestrator", "alpha", "beta")
        manual = _make_service_map("admission", "orchestrator")

        report = detect_drift(generated, manual)

        assert report.has_drift is True
        assert report.in_generated_not_manual == ["alpha", "beta"]
        assert report.in_manual_not_generated == []


# ---------------------------------------------------------------------------
# Tests: manual has extra services
# ---------------------------------------------------------------------------


class TestManualHasExtras:
    def test_one_extra_in_manual(self):
        generated = _make_service_map("admission", "orchestrator")
        manual = _make_service_map("admission", "orchestrator", "legacy_service")

        report = detect_drift(generated, manual)

        assert report.has_drift is True
        assert report.in_generated_not_manual == []
        assert report.in_manual_not_generated == ["legacy_service"]

    def test_multiple_extras_in_manual(self):
        generated = _make_service_map("admission")
        manual = _make_service_map("admission", "old_a", "old_b")

        report = detect_drift(generated, manual)

        assert report.has_drift is True
        assert report.in_generated_not_manual == []
        assert report.in_manual_not_generated == ["old_a", "old_b"]


# ---------------------------------------------------------------------------
# Tests: bidirectional drift
# ---------------------------------------------------------------------------


class TestBidirectionalDrift:
    def test_both_directions_simultaneously(self):
        generated = _make_service_map("admission", "new_gen_service")
        manual = _make_service_map("admission", "old_manual_service")

        report = detect_drift(generated, manual)

        assert report.has_drift is True
        assert report.in_generated_not_manual == ["new_gen_service"]
        assert report.in_manual_not_generated == ["old_manual_service"]

    def test_completely_disjoint_services(self):
        generated = _make_service_map("alpha", "beta")
        manual = _make_service_map("gamma", "delta")

        report = detect_drift(generated, manual)

        assert report.has_drift is True
        assert report.in_generated_not_manual == ["alpha", "beta"]
        assert report.in_manual_not_generated == ["delta", "gamma"]


# ---------------------------------------------------------------------------
# Tests: empty maps
# ---------------------------------------------------------------------------


class TestEmptyMaps:
    def test_both_empty(self):
        generated = _make_service_map()
        manual = _make_service_map()

        report = detect_drift(generated, manual)

        assert report.has_drift is False
        assert report.in_generated_not_manual == []
        assert report.in_manual_not_generated == []

    def test_generated_empty_manual_has_services(self):
        generated = _make_service_map()
        manual = _make_service_map("admission", "orchestrator")

        report = detect_drift(generated, manual)

        assert report.has_drift is True
        assert report.in_generated_not_manual == []
        assert report.in_manual_not_generated == ["admission", "orchestrator"]

    def test_manual_empty_generated_has_services(self):
        generated = _make_service_map("admission", "orchestrator")
        manual = _make_service_map()

        report = detect_drift(generated, manual)

        assert report.has_drift is True
        assert report.in_generated_not_manual == ["admission", "orchestrator"]
        assert report.in_manual_not_generated == []

    def test_missing_services_key_treated_as_empty(self):
        generated = {"description": "no services key"}
        manual = {"description": "no services key either"}

        report = detect_drift(generated, manual)

        assert report.has_drift is False
        assert report.in_generated_not_manual == []
        assert report.in_manual_not_generated == []

    def test_missing_services_key_in_one_map(self):
        generated = _make_service_map("admission")
        manual = {"description": "no services key"}

        report = detect_drift(generated, manual)

        assert report.has_drift is True
        assert report.in_generated_not_manual == ["admission"]
        assert report.in_manual_not_generated == []
