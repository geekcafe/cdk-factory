"""Unit tests for the wizard connection flow (design §2.5, OPEN-FINDINGS 2 & 4)."""

from unittest.mock import MagicMock

from cdk_factory.wizard.aws_inspectors import AwsInspectorError, ConnectionSummary
from cdk_factory.wizard.connection_flow import (
    PASTE_ARN_CHOICE,
    is_valid_connection_arn,
    resolve_usable_connection,
)
from cdk_factory.wizard.prompts import ScriptedPrompter


ARN_CC = "arn:aws:codeconnections:us-east-1:123456789012:connection/1111aaaa-2222-3333-4444-555566667777"
ARN_CSC = "arn:aws:codestar-connections:us-east-1:123456789012:connection/8888bbbb-9999-0000-1111-222233334444"
ARN_ZERO = "arn:aws:codeconnections:us-east-1:123456789012:connection/00000000-0000-0000-0000-000000000000"


# ---------------------------------------------------------------------------
# The NEW validator (NOT _validate_arn)
# ---------------------------------------------------------------------------


def test_validator_accepts_both_partitions():
    assert is_valid_connection_arn(ARN_CC) is True
    assert is_valid_connection_arn(ARN_CSC) is True


def test_validator_rejects_all_zeros_placeholder():
    assert is_valid_connection_arn(ARN_ZERO) is False


def test_validator_rejects_garbage_and_none():
    assert is_valid_connection_arn("not-an-arn") is False
    assert is_valid_connection_arn("") is False
    assert is_valid_connection_arn(None) is False
    # Right prefix, no connection id.
    assert (
        is_valid_connection_arn(
            "arn:aws:codeconnections:us-east-1:123456789012:connection/"
        )
        is False
    )


def _inspector_returning(connections):
    inspector = MagicMock()
    inspector.list_connections.return_value = connections
    return inspector


# ---------------------------------------------------------------------------
# Auto-select single AVAILABLE repo-owner match
# ---------------------------------------------------------------------------


def test_single_available_repo_match_auto_selects():
    conn = ConnectionSummary(
        name="geekcafe-github", arn=ARN_CC, status="AVAILABLE", provider_type="GitHub"
    )
    inspector = _inspector_returning([conn])
    prompt = ScriptedPrompter([])  # no prompts should be needed
    result = resolve_usable_connection(
        inspector, prompt, repo_owner="geekcafe", provider_hint="GitHub"
    )
    assert result.source == "auto"
    assert result.arn == ARN_CC
    assert prompt.calls == []  # auto-selected, no interaction


# ---------------------------------------------------------------------------
# Multiple AVAILABLE -> recommended default + always-present paste override
# ---------------------------------------------------------------------------


def test_multiple_available_recommended_default_and_paste_override():
    match = ConnectionSummary(
        name="geekcafe-gh", arn=ARN_CC, status="AVAILABLE", provider_type="GitHub"
    )
    other = ConnectionSummary(
        name="someone-else", arn=ARN_CSC, status="AVAILABLE", provider_type="Bitbucket"
    )
    inspector = _inspector_returning([other, match])

    captured = {}
    prompt = ScriptedPrompter([])

    def _select(message, choices, default=None):
        captured["choices"] = list(choices)
        captured["default"] = default
        prompt.calls.append(("select", message))
        return choices[0]

    prompt.select = _select  # type: ignore[assignment]

    result = resolve_usable_connection(
        inspector, prompt, repo_owner="geekcafe", provider_hint="GitHub"
    )
    assert result.source == "selected"
    # Paste override is always present.
    assert PASTE_ARN_CHOICE in captured["choices"]
    # Recommended match is pre-selected as default and ranked first.
    assert captured["default"] is not None
    assert "recommended" in captured["default"]
    assert "geekcafe" in captured["default"]


def test_select_paste_override_validates_pasted_arn():
    a = ConnectionSummary("a", ARN_CC, "AVAILABLE", "GitHub")
    b = ConnectionSummary("b", ARN_CSC, "AVAILABLE", "Bitbucket")
    inspector = _inspector_returning([a, b])

    prompt = ScriptedPrompter([])

    def _select(message, choices, default=None):
        prompt.calls.append(("select", message))
        return PASTE_ARN_CHOICE

    prompt.select = _select  # type: ignore[assignment]
    prompt.answers = [ARN_CSC]  # text() pops this
    result = resolve_usable_connection(inspector, prompt, repo_owner=None)
    assert result.source == "pasted"
    assert result.arn == ARN_CSC


# ---------------------------------------------------------------------------
# Genuine zero -> create-it guidance + paste/exit
# ---------------------------------------------------------------------------


def test_genuine_zero_shows_create_it_guidance():
    inspector = _inspector_returning([])
    prompt = ScriptedPrompter([""])  # blank paste -> cancel (exit)
    result = resolve_usable_connection(inspector, prompt, repo_owner="geekcafe")
    assert result.source == "none"
    assert result.arn is None
    assert result.access_denied is False
    titles = [t for (t, _b, _s) in prompt.panels]
    assert any("No usable connection" in (t or "") for t in titles)


def test_pending_surfaced_not_selected():
    pending = ConnectionSummary("p", ARN_CC, "PENDING", "GitHub")
    inspector = _inspector_returning([pending])
    prompt = ScriptedPrompter([""])  # blank paste
    result = resolve_usable_connection(inspector, prompt)
    assert result.arn is None
    assert result.pending == [pending]
    # The create-it guidance lists the pending ARN.
    body = "".join(b for (_t, b, _s) in prompt.panels)
    assert ARN_CC in body


# ---------------------------------------------------------------------------
# AccessDenied -> distinct permission panel, NOT create-it
# ---------------------------------------------------------------------------


def test_access_denied_distinct_permission_panel():
    inspector = MagicMock()
    inspector.list_connections.side_effect = AwsInspectorError(
        "denied", access_denied=True
    )
    prompt = ScriptedPrompter([ARN_CC])  # operator pastes a valid ARN
    result = resolve_usable_connection(inspector, prompt, repo_owner="geekcafe")
    assert result.access_denied is True
    assert result.arn == ARN_CC
    panel_text = " ".join(
        f"{t} {b}" for (t, b, _s) in prompt.panels
    )
    assert "access denied" in panel_text.lower()
    # Must NOT be the create-it path.
    assert "Create connection" not in panel_text
    assert "create one" not in panel_text.lower()


# ---------------------------------------------------------------------------
# Preferred-arn reuse + override
# ---------------------------------------------------------------------------


def test_preferred_arn_reuse():
    conn = ConnectionSummary("gh", ARN_CC, "AVAILABLE", "GitHub")
    inspector = _inspector_returning([conn])
    prompt = ScriptedPrompter([True])  # confirm reuse
    result = resolve_usable_connection(
        inspector, prompt, preferred_arn=ARN_CC, repo_owner="geekcafe"
    )
    assert result.source == "preferred"
    assert result.arn == ARN_CC


def test_preferred_arn_override_falls_through_to_select():
    preferred = ConnectionSummary("old", ARN_CC, "AVAILABLE", "GitHub")
    newer = ConnectionSummary("new", ARN_CSC, "AVAILABLE", "GitHub")
    inspector = _inspector_returning([preferred, newer])
    prompt = ScriptedPrompter([False])  # decline reuse

    def _select(message, choices, default=None):
        prompt.calls.append(("select", message))
        # pick the newer connection's label
        for c in choices:
            if ARN_CSC in c:
                return c
        return choices[0]

    prompt.select = _select  # type: ignore[assignment]
    result = resolve_usable_connection(
        inspector, prompt, preferred_arn=ARN_CC, repo_owner=None
    )
    assert result.source == "selected"
    assert result.arn == ARN_CSC
