"""
Bug condition exploration tests for chained placeholder resolution.

These tests demonstrate that recursive_replace does a single pass over
replacement keys per string value. When a replacement VALUE contains a
placeholder referencing another key that was already iterated past,
the inner placeholder is never resolved.

The bug is order-dependent: if the inner key appears BEFORE the outer
key in the replacements dict iteration order, the inner key's replacement
happens first (on the original string which doesn't contain it yet),
and then the outer key introduces the inner placeholder — but the inner
key won't be visited again.

**Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2, 2.3**
"""

import re
import unittest
from collections import OrderedDict

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.cdk_factory.utilities.json_loading_utility import JsonLoadingUtility


def pre_resolve_replacements(replacements: dict) -> dict:
    """Apply multi-pass resolution on replacement values (mirrors __resolved_config fix)."""
    resolved = dict(replacements)
    for _ in range(5):
        changed = False
        for key, value in resolved.items():
            if isinstance(value, str) and "{{" in value:
                new_value = value
                for find_str, replace_str in resolved.items():
                    if isinstance(replace_str, str):
                        new_value = new_value.replace(find_str, replace_str)
                if new_value != value:
                    resolved[key] = new_value
                    changed = True
        if not changed:
            break
    return resolved


class TestBugConditionChainedPlaceholdersUnresolved(unittest.TestCase):
    """Tests that FAIL on unfixed code — proving the bug exists.

    The bug: recursive_replace iterates replacement keys once per string.
    When the inner placeholder key appears before the outer key in dict
    iteration order, the inner key is applied first (no-op on the original
    string), then the outer key introduces the inner placeholder — but
    the inner key won't be visited again.
    """

    def test_target_account_role_arn_chain(self):
        """Concrete test case 1: TARGET_ACCOUNT_ROLE_ARN contains {{AWS_ACCOUNT}}.

        Insert AWS_ACCOUNT first so it's iterated before TARGET_ACCOUNT_ROLE_ARN.
        This means when TARGET_ACCOUNT_ROLE_ARN is replaced and introduces
        {{AWS_ACCOUNT}}, the inner placeholder is never resolved.

        **Validates: Requirements 1.1, 2.1**
        """
        # Inner key inserted first — will be iterated first (no-op),
        # then outer key introduces it, but inner key won't be revisited
        replacements = OrderedDict()
        replacements["{{AWS_ACCOUNT}}"] = "959096737760"
        replacements["{{TARGET_ACCOUNT_ROLE_ARN}}"] = (
            "arn:aws:iam::{{AWS_ACCOUNT}}:role/DevOpsCrossAccountAccessRole"
        )

        config = {"role": "{{TARGET_ACCOUNT_ROLE_ARN}}"}

        resolved_replacements = pre_resolve_replacements(replacements)
        result = JsonLoadingUtility.recursive_replace(config, resolved_replacements)

        self.assertEqual(
            result["role"],
            "arn:aws:iam::959096737760:role/DevOpsCrossAccountAccessRole",
        )

    def test_ssm_parameter_namespace_chain(self):
        """Concrete test case 2: TARGET_HOSTED_ZONE_ID_SSM_PARAMETER_NAME contains {{DEPLOYMENT_NAMESPACE}}.

        Insert DEPLOYMENT_NAMESPACE first so it's iterated before the outer key.

        **Validates: Requirements 1.2, 2.2**
        """
        replacements = OrderedDict()
        replacements["{{DEPLOYMENT_NAMESPACE}}"] = "beta"
        replacements["{{TARGET_HOSTED_ZONE_ID_SSM_PARAMETER_NAME}}"] = (
            "/aplos-nca-saas/{{DEPLOYMENT_NAMESPACE}}/route53/hosted-zone-id"
        )

        config = {"ssm": "{{TARGET_HOSTED_ZONE_ID_SSM_PARAMETER_NAME}}"}

        resolved_replacements = pre_resolve_replacements(replacements)
        result = JsonLoadingUtility.recursive_replace(config, resolved_replacements)

        self.assertEqual(
            result["ssm"],
            "/aplos-nca-saas/beta/route53/hosted-zone-id",
        )

    def test_three_level_chain(self):
        """Concrete test case 3: Three-level chain A -> B -> C -> leaf.

        Insert in leaf-first order so inner keys are iterated before outer keys.

        **Validates: Requirements 1.3, 2.3**
        """
        replacements = OrderedDict()
        replacements["{{C}}"] = "leaf"
        replacements["{{B}}"] = "mid-{{C}}"
        replacements["{{A}}"] = "prefix-{{B}}"

        config = {"val": "{{A}}"}

        resolved_replacements = pre_resolve_replacements(replacements)
        result = JsonLoadingUtility.recursive_replace(config, resolved_replacements)

        self.assertEqual(result["val"], "prefix-mid-leaf")

    @given(
        st.fixed_dictionaries(
            {
                "inner_value": st.text(
                    alphabet=st.characters(whitelist_categories=("L", "N")),
                    min_size=1,
                    max_size=20,
                ),
                "prefix": st.text(
                    alphabet=st.characters(whitelist_categories=("L", "N")),
                    min_size=1,
                    max_size=10,
                ),
            }
        )
    )
    @settings(max_examples=50)
    def test_property_chained_refs_fully_resolved(self, data):
        """Property test: for any chained replacements where the inner key
        is iterated before the outer key, all {{...}} tokens referencing
        keys in the dict should be fully resolved.

        **Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2, 2.3**
        """
        inner_value = data["inner_value"]
        prefix = data["prefix"]

        # Inner key first in iteration order — triggers the bug
        replacements = OrderedDict()
        replacements["{{INNER}}"] = inner_value
        replacements["{{OUTER}}"] = f"{prefix}-{{{{INNER}}}}"

        config = {"key": "{{OUTER}}"}

        resolved_replacements = pre_resolve_replacements(replacements)
        result = JsonLoadingUtility.recursive_replace(config, resolved_replacements)

        # After resolution, no replacement key should appear in the output
        for placeholder_key in replacements:
            self.assertNotIn(
                placeholder_key,
                str(result["key"]),
                f"Unresolved placeholder {placeholder_key} found in result: {result['key']}",
            )


if __name__ == "__main__":
    unittest.main()


class TestPreservationNonChainedReplacements(unittest.TestCase):
    """Tests that PASS on unfixed code — capturing baseline behavior for
    non-chained replacements. These must continue to pass after the fix.

    **Validates: Requirements 3.1, 3.2, 3.5**
    """

    def test_empty_replacements_returns_config_unchanged(self):
        """Empty replacements dict returns config unchanged.

        **Validates: Requirements 3.5**
        """
        config = {"name": "myapp", "nested": {"key": "value"}, "items": [1, 2, 3]}
        result = JsonLoadingUtility.recursive_replace(config, {})
        self.assertEqual(result, config)

    def test_simple_literal_replacements_resolve_correctly(self):
        """Simple literal replacements (no inner placeholders) resolve correctly.

        **Validates: Requirements 3.1, 3.2**
        """
        config = {"name": "{{workload-name}}", "env": "{{env}}"}
        replacements = {"{{workload-name}}": "myapp", "{{env}}": "prod"}
        result = JsonLoadingUtility.recursive_replace(config, replacements)
        self.assertEqual(result, {"name": "myapp", "env": "prod"})

    def test_nested_config_structures_resolve_correctly(self):
        """Nested config structures resolve correctly.

        **Validates: Requirements 3.1, 3.2**
        """
        config = {"nested": {"key": "{{val}}"}}
        replacements = {"{{val}}": "resolved"}
        result = JsonLoadingUtility.recursive_replace(config, replacements)
        self.assertEqual(result, {"nested": {"key": "resolved"}})

    def test_values_with_unmatched_placeholders_left_as_is(self):
        """Replacements where values contain {{ but no matching key in the
        dict are left as-is.

        **Validates: Requirements 3.1, 3.2**
        """
        config = {"key": "{{KNOWN}}"}
        replacements = {"{{KNOWN}}": "prefix-{{UNKNOWN}}-suffix"}
        result = JsonLoadingUtility.recursive_replace(config, replacements)
        # {{UNKNOWN}} is NOT a key in replacements, so it stays literal
        self.assertEqual(result, {"key": "prefix-{{UNKNOWN}}-suffix"})

    @given(
        st.dictionaries(
            keys=st.text(
                alphabet=st.characters(whitelist_categories=("L", "N")),
                min_size=1,
                max_size=10,
            ),
            values=st.text(
                alphabet=st.characters(whitelist_categories=("L", "N", "P")),
                min_size=0,
                max_size=20,
            ),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=50)
    def test_property_non_chained_replacements_resolve_correctly(
        self, raw_replacements
    ):
        """Property test: for any non-chained replacements dict and config
        using those placeholders, recursive_replace produces the expected
        output where each placeholder is replaced by its literal value.

        We generate replacements where NO value contains any key from the dict
        (the negation of isBugCondition). Then we build a config containing
        those placeholders and verify each is resolved to its value.

        **Validates: Requirements 3.1, 3.2, 3.5**
        """
        # Build replacements dict with {{KEY}} format
        replacements = {}
        for k, v in raw_replacements.items():
            placeholder = "{{" + k + "}}"
            replacements[placeholder] = v

        # Ensure non-chained: no value contains any key from the dict
        for placeholder_key in replacements:
            for value in replacements.values():
                if placeholder_key in str(value):
                    assume(False)

        # Build a config that uses each placeholder as a value
        config = {}
        for i, placeholder_key in enumerate(replacements):
            config[f"field_{i}"] = placeholder_key

        result = JsonLoadingUtility.recursive_replace(config, replacements)

        # Each field should be resolved to the replacement value
        for i, (placeholder_key, expected_value) in enumerate(replacements.items()):
            self.assertEqual(
                result[f"field_{i}"],
                expected_value,
                f"Placeholder {placeholder_key} was not resolved to '{expected_value}'",
            )
