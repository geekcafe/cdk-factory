"""
Property-based tests for template rendering utility.

Feature: cdk-pipeline-commands, Property 7: Template renderer substitutes all matched placeholders
Validates: Requirements 11.5
"""

import re
import string

from hypothesis import assume, given, settings
from hypothesis.strategies import (
    dictionaries,
    fixed_dictionaries,
    just,
    lists,
    text,
)

from cdk_factory.pipeline.conventions.template_render import render_template

# Strategy for generating valid placeholder keys (non-empty, no braces)
_key_alphabet = string.ascii_letters + string.digits + "_"
_key_strategy = text(min_size=1, max_size=20, alphabet=_key_alphabet)

# Strategy for generating replacement values
_value_strategy = text(min_size=0, max_size=50)

# Strategy for generating context dictionaries
_context_strategy = dictionaries(
    keys=_key_strategy,
    values=_value_strategy,
    min_size=0,
    max_size=5,
)


class TestTemplateRendererProperties:
    """Property tests for render_template().

    Feature: cdk-pipeline-commands, Property 7: Template renderer substitutes all matched placeholders
    """

    @given(
        keys=lists(_key_strategy, min_size=1, max_size=5, unique=True),
        values=lists(_value_strategy, min_size=1, max_size=5),
        prefix=text(min_size=0, max_size=10, alphabet=string.ascii_letters + " "),
        suffix=text(min_size=0, max_size=10, alphabet=string.ascii_letters + " "),
    )
    @settings(max_examples=100)
    def test_matched_placeholders_are_replaced(
        self, keys: list, values: list, prefix: str, suffix: str
    ):
        """Every {{KEY}} whose KEY exists in context is replaced with the value.

        Validates: Requirements 11.5
        """
        # Ensure values list matches keys list length
        values = values[: len(keys)]
        if len(values) < len(keys):
            values.extend([""] * (len(keys) - len(values)))

        # Build context and template
        context = dict(zip(keys, values))
        # Build a template with all keys as placeholders
        template = prefix + "".join(f"{{{{{k}}}}}" for k in keys) + suffix

        result = render_template(template, context)

        # Verify each key's placeholder was replaced with its value
        expected = prefix + "".join(str(context[k]) for k in keys) + suffix
        assert result == expected

    @given(
        keys=lists(_key_strategy, min_size=1, max_size=5, unique=True),
        prefix=text(min_size=0, max_size=10, alphabet=string.ascii_letters + " "),
        suffix=text(min_size=0, max_size=10, alphabet=string.ascii_letters + " "),
    )
    @settings(max_examples=100)
    def test_unmatched_placeholders_remain_unchanged(
        self, keys: list, prefix: str, suffix: str
    ):
        """Every {{KEY}} whose KEY is NOT in context remains unchanged in output.

        Validates: Requirements 11.5
        """
        # Build template with placeholders but provide empty context
        template = prefix + "".join(f"{{{{{k}}}}}" for k in keys) + suffix
        context: dict = {}

        result = render_template(template, context)

        # Template should be unchanged since no keys match
        assert result == template

    @given(
        present_keys=lists(_key_strategy, min_size=1, max_size=3, unique=True),
        absent_keys=lists(_key_strategy, min_size=1, max_size=3, unique=True),
        values=lists(_value_strategy, min_size=1, max_size=3),
    )
    @settings(max_examples=100)
    def test_mixed_matched_and_unmatched_placeholders(
        self, present_keys: list, absent_keys: list, values: list
    ):
        """Matched placeholders are replaced; unmatched ones stay intact.

        Validates: Requirements 11.5
        """
        # Ensure absent keys don't overlap with present keys
        absent_keys = [k for k in absent_keys if k not in present_keys]
        assume(len(absent_keys) > 0)

        # Build context only for present_keys
        values = values[: len(present_keys)]
        if len(values) < len(present_keys):
            values.extend([""] * (len(present_keys) - len(values)))
        context = dict(zip(present_keys, values))

        # Build template with both present and absent placeholders
        template = "".join(f"{{{{{k}}}}}" for k in present_keys) + "".join(
            f"{{{{{k}}}}}" for k in absent_keys
        )

        result = render_template(template, context)

        # Present keys should be replaced, absent keys should remain as placeholders
        expected = "".join(str(context[k]) for k in present_keys) + "".join(
            f"{{{{{k}}}}}" for k in absent_keys
        )
        assert result == expected

    @given(template=text(min_size=0, max_size=100), context=_context_strategy)
    @settings(max_examples=100)
    def test_no_placeholder_pattern_means_no_change(self, template: str, context: dict):
        """If template contains no {{KEY}} patterns matching context keys, non-placeholder text is preserved.

        Validates: Requirements 11.5
        """
        # Filter template to not contain any {{ patterns
        assume("{{" not in template)

        result = render_template(template, context)
        assert result == template
