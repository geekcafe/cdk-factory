"""
Property-based tests for app name derivation.

Feature: cdk-pipeline-commands, Property 3: App name derivation is underscore-to-hyphen replacement only
Validates: Requirements 2.9, 9.1, 9.2
"""

import string

from hypothesis import given, settings
from hypothesis.strategies import text

from cdk_factory.pipeline.commands.unified_pipeline_cli import derive_app_name

# Strategy for generating random strings with underscores, hyphens, digits, letters
_app_name_alphabet = string.ascii_letters + string.digits + "_-"
_app_name_strategy = text(min_size=0, max_size=50, alphabet=_app_name_alphabet)


class TestDeriveAppNameProperties:
    """Property tests for derive_app_name().

    Feature: cdk-pipeline-commands, Property 3: App name derivation is underscore-to-hyphen replacement only
    """

    @given(s=_app_name_strategy)
    @settings(max_examples=100)
    def test_underscores_replaced_with_hyphens(self, s: str):
        """Every underscore in the input is replaced with a hyphen in the output.

        Validates: Requirements 2.9, 9.1, 9.2
        """
        result = derive_app_name(s)
        assert "_" not in result

    @given(s=_app_name_strategy)
    @settings(max_examples=100)
    def test_non_underscore_characters_unchanged(self, s: str):
        """All non-underscore characters remain unchanged in their original positions.

        Validates: Requirements 2.9, 9.1, 9.2
        """
        result = derive_app_name(s)
        for i, char in enumerate(s):
            if char != "_":
                assert result[i] == char

    @given(s=_app_name_strategy)
    @settings(max_examples=100)
    def test_output_length_equals_input_length(self, s: str):
        """The length of the output equals the length of the input.

        Validates: Requirements 2.9, 9.1, 9.2
        """
        result = derive_app_name(s)
        assert len(result) == len(s)

    @given(s=_app_name_strategy)
    @settings(max_examples=100)
    def test_underscore_positions_become_hyphens(self, s: str):
        """Every position that was an underscore in the input is a hyphen in the output.

        Validates: Requirements 2.9, 9.1, 9.2
        """
        result = derive_app_name(s)
        for i, char in enumerate(s):
            if char == "_":
                assert result[i] == "-"
