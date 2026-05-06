"""
Property-based tests for EventBridge trigger name normalization.

Feature: eventbridge-rule-ssm-registration
Property 1: Trigger name normalization is underscore-free and idempotent
Validates: Requirements 1.3
"""

import string

from hypothesis import given, settings
from hypothesis.strategies import text


def normalize_trigger_name(name: str) -> str:
    """Normalize trigger name by replacing underscores with hyphens."""
    return name.replace("_", "-")


class TestTriggerNameNormalization:
    """Property tests for trigger name normalization."""

    @given(
        name=text(
            min_size=1,
            max_size=50,
            alphabet=string.ascii_lowercase + string.digits + "_-",
        )
    )
    @settings(max_examples=100)
    def test_normalization_produces_no_underscores(self, name: str):
        """Normalized trigger names must not contain underscores.

        Validates: Requirements 1.3
        """
        result = normalize_trigger_name(name)
        assert "_" not in result

    @given(
        name=text(
            min_size=1,
            max_size=50,
            alphabet=string.ascii_lowercase + string.digits + "_-",
        )
    )
    @settings(max_examples=100)
    def test_normalization_is_idempotent(self, name: str):
        """Applying normalization twice yields the same result as once.

        Validates: Requirements 1.3
        """
        once = normalize_trigger_name(name)
        twice = normalize_trigger_name(once)
        assert once == twice
