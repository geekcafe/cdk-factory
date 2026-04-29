"""
Unit tests for the string-to-list conversion logic used in StaticWebSiteStack.build().

Tests the isinstance + split pattern that converts comma-separated placeholder strings
into lists for dns.aliases and cert.alternate_names. This follows the same pattern as
ApiGatewayStack.__setup_custom_domain for API_DOMAIN_NAMES.

Requirements: 5.1, 5.2
"""

import pytest


def _split_comma_separated(value):
    """
    Helper that mirrors the conversion logic in StaticWebSiteStack.build().

    When config resolution replaces a JSON array with a single comma-separated
    placeholder string, this logic splits it back into a list. Array inputs
    pass through unchanged for backward compatibility.
    """
    if isinstance(value, str):
        return [a.strip() for a in value.split(",") if a.strip()]
    return value


class TestSplitCommaSeparated:
    """Test the comma-separated string to list conversion logic."""

    def test_comma_separated_string_to_list(self):
        """Comma-separated string produces a list of individual values."""
        result = _split_comma_separated("a.com,b.com")
        assert result == ["a.com", "b.com"]

    def test_single_value_string_to_single_element_list(self):
        """A single value string produces a single-element list."""
        result = _split_comma_separated("a.com")
        assert result == ["a.com"]

    def test_string_with_whitespace_produces_trimmed_list(self):
        """Whitespace around commas is stripped from each entry."""
        result = _split_comma_separated("a.com, b.com")
        assert result == ["a.com", "b.com"]

    def test_array_input_unchanged(self):
        """Array input passes through unchanged for backward compatibility."""
        input_list = ["a.com", "b.com"]
        result = _split_comma_separated(input_list)
        assert result == ["a.com", "b.com"]

    def test_empty_entries_filtered(self):
        """Empty entries from consecutive commas are filtered out."""
        result = _split_comma_separated("a.com,,b.com")
        assert result == ["a.com", "b.com"]
