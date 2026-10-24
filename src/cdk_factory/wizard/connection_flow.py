"""Pipeline-mode CodeConnections resolution (design §2.5).

Resolves a usable (``AVAILABLE``) CodeConnections ARN for a pipeline deploy,
ranking by match to the monitor repo, always offering a paste-an-ARN override,
and handling ``AccessDenied`` as a distinct permission panel (never "create
one").

Carries OPEN-FINDINGS MEDIUM-2 + NIT-4: a **NEW** wizard ARN validator
(:func:`is_valid_connection_arn`) that accepts BOTH the ``codeconnections`` and
``codestar-connections`` partitions and REJECTS the all-zeros placeholder uuid.
It deliberately does NOT reuse ``CdkDeploymentCommand._validate_arn`` (which only
accepts ``arn:aws:codeconnections:`` and would trap a valid pasted/fallback
``codestar-connections`` ARN in a re-prompt loop).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from cdk_factory.wizard.aws_inspectors import (
    AwsInspector,
    AwsInspectorError,
    ConnectionSummary,
)
from cdk_factory.wizard.prompts import PromptPort

#: Accepts both CodeConnections partitions and requires a non-empty connection
#: uuid segment. The all-zeros placeholder is rejected separately below.
_CONNECTION_ARN_RE = re.compile(
    r"^arn:aws:(codeconnections|codestar-connections):"
    r"[a-z0-9-]+:\d{12}:connection/[0-9a-fA-F-]+$"
)

#: The all-zeros placeholder uuid shipped in config.json's CODE_REPOSITORY_ARN
#: default — a non-functional placeholder that must never be accepted.
_PLACEHOLDER_UUID = "00000000-0000-0000-0000-000000000000"

#: Always-present select entry letting the operator paste any ARN.
PASTE_ARN_CHOICE = "✎ Paste a different ARN"


def is_valid_connection_arn(arn: Optional[str]) -> bool:
    """Return True iff *arn* is a real CodeConnections connection ARN.

    Accepts both ``arn:aws:codeconnections:...`` and
    ``arn:aws:codestar-connections:...`` and rejects the all-zeros placeholder
    uuid (``00000000-0000-0000-0000-000000000000``) so an operator cannot accept
    a non-functional placeholder.
    """
    if not arn or not isinstance(arn, str):
        return False
    if not _CONNECTION_ARN_RE.match(arn):
        return False
    connection_id = arn.rsplit("/", 1)[-1]
    if connection_id == _PLACEHOLDER_UUID:
        return False
    # Reject an all-zeros id of any form (require a non-zero segment).
    if set(connection_id) <= {"0", "-"}:
        return False
    return True


@dataclass(frozen=True)
class ConnectionResult:
    """Outcome of :func:`resolve_usable_connection`."""

    arn: Optional[str]
    source: str  # "preferred" | "auto" | "selected" | "pasted" | "none"
    available: List[ConnectionSummary] = field(default_factory=list)
    pending: List[ConnectionSummary] = field(default_factory=list)
    access_denied: bool = False


def _matches_repo(conn: ConnectionSummary, repo_owner: Optional[str], provider_hint: Optional[str]) -> bool:
    """True when a connection plausibly matches the target repo/provider."""
    owner_match = bool(
        repo_owner and repo_owner.lower() in (conn.name or "").lower()
    )
    provider_match = bool(
        provider_hint
        and provider_hint.lower() == (conn.provider_type or "").lower()
    )
    if provider_hint and repo_owner:
        return owner_match or provider_match
    if provider_hint:
        return provider_match
    if repo_owner:
        return owner_match
    return False


def _rank(available: List[ConnectionSummary], repo_owner, provider_hint) -> List[ConnectionSummary]:
    """Return AVAILABLE connections with repo/provider matches first (stable)."""
    matches = [c for c in available if _matches_repo(c, repo_owner, provider_hint)]
    rest = [c for c in available if c not in matches]
    return matches + rest


def _label(conn: ConnectionSummary, recommended: bool, repo_owner: Optional[str]) -> str:
    base = f"{conn.name}  [{conn.provider_type}]  {conn.arn}"
    if recommended:
        suffix = f" (recommended — matches {repo_owner})" if repo_owner else " (recommended)"
        return base + suffix
    return base


def _paste_until_valid(prompt: PromptPort) -> Optional[str]:
    """Prompt for an ARN, re-prompting until valid or the operator gives up."""
    for _ in range(100):  # generous upper bound to avoid an infinite test hang
        pasted = (prompt.text("Paste a CodeConnections connection ARN:") or "").strip()
        if not pasted:
            return None
        if is_valid_connection_arn(pasted):
            return pasted
        prompt.note(
            "That does not look like a valid CodeConnections connection ARN "
            "(or it is the all-zeros placeholder). Try again, or leave blank to cancel.",
            style="warning",
        )
    return None


def resolve_usable_connection(
    inspector: AwsInspector,
    prompt: PromptPort,
    *,
    preferred_arn: Optional[str] = None,
    repo_owner: Optional[str] = None,
    provider_hint: Optional[str] = None,
) -> ConnectionResult:
    """Resolve a usable connection ARN for pipeline mode.

    ``access_denied`` is handled BEFORE the zero/AVAILABLE branch: a permission
    panel + paste/exit, never the create-it guidance.
    """
    # 1. List connections, routing AccessDenied to a distinct permission panel.
    try:
        connections = inspector.list_connections()
    except AwsInspectorError as exc:
        if exc.access_denied:
            prompt.panel(
                "Could not list CodeConnections: access denied on "
                "codeconnections:ListConnections.\n"
                "If you already have a connection ARN, paste it below. Otherwise "
                "grant codeconnections:ListConnections (and GetConnection) and "
                "re-run — do NOT create a new connection if one already exists.",
                title="Permission needed",
                style="error",
            )
            pasted = _paste_until_valid(prompt)
            return ConnectionResult(
                arn=pasted,
                source="pasted" if pasted else "none",
                available=[],
                pending=[],
                access_denied=True,
            )
        # Any other inspector error: surface and let the operator paste/exit.
        prompt.panel(
            f"{exc.message}" + (f"\n{exc.remediation}" if exc.remediation else ""),
            title="Could not list connections",
            style="error",
        )
        pasted = _paste_until_valid(prompt)
        return ConnectionResult(
            arn=pasted,
            source="pasted" if pasted else "none",
            available=[],
            pending=[],
        )

    available = [c for c in connections if c.status == "AVAILABLE"]
    pending = [c for c in connections if c.status == "PENDING"]

    # 2. Preferred ARN reuse (with override escape).
    if preferred_arn and any(c.arn == preferred_arn for c in available):
        reuse = prompt.confirm(
            f"Reuse the previously selected connection?\n  {preferred_arn}",
            default=True,
        )
        if reuse:
            return ConnectionResult(
                arn=preferred_arn,
                source="preferred",
                available=available,
                pending=pending,
            )
        # fall through to selection so a stale pick can be overridden

    # 3. Rank AVAILABLE by repo/provider match.
    ranked = _rank(available, repo_owner, provider_hint)
    recommended = ranked[0] if ranked else None
    has_confident_match = bool(
        recommended and _matches_repo(recommended, repo_owner, provider_hint)
    )

    # 3a. Exactly one AVAILABLE and it's a confident match -> auto-select.
    if len(available) == 1 and has_confident_match:
        return ConnectionResult(
            arn=available[0].arn,
            source="auto",
            available=available,
            pending=pending,
        )

    # 3b. One or more AVAILABLE -> select among ALL AVAILABLE + paste override.
    if available:
        choices: List[str] = []
        label_to_arn = {}
        for conn in ranked:
            is_rec = has_confident_match and conn is recommended
            label = _label(conn, is_rec, repo_owner)
            choices.append(label)
            label_to_arn[label] = conn.arn
        choices.append(PASTE_ARN_CHOICE)
        default = choices[0] if (has_confident_match and choices) else None
        picked = prompt.select(
            "Select a CodeConnections connection:", choices, default=default
        )
        if picked == PASTE_ARN_CHOICE:
            pasted = _paste_until_valid(prompt)
            return ConnectionResult(
                arn=pasted,
                source="pasted" if pasted else "none",
                available=available,
                pending=pending,
            )
        return ConnectionResult(
            arn=label_to_arn.get(picked),
            source="selected",
            available=available,
            pending=pending,
        )

    # 4. Genuine zero AVAILABLE -> create-it guidance + paste/exit.
    pending_lines = "\n".join(f"  Pending (not yet usable): {c.arn}" for c in pending)
    body = (
        "No usable CodeConnections connection found.\n"
        "A pipeline deploy needs an AVAILABLE connection to your Git provider.\n"
        "Create one (one-time, in the console):\n"
        "  AWS Console -> Developer Tools -> Settings -> Connections -> Create "
        "connection -> pick GitHub/Bitbucket -> Install/authorize the app "
        "(moves it from PENDING to AVAILABLE) -> copy the connection ARN.\n"
        "Or via CLI: aws codeconnections create-connection "
        "--provider-type GitHub --connection-name <name>  "
        "(then finish the handshake in the console)."
    )
    if pending_lines:
        body = body + "\n" + pending_lines
    prompt.panel(body, title="No usable connection", style="warning")
    pasted = _paste_until_valid(prompt)
    return ConnectionResult(
        arn=pasted,
        source="pasted" if pasted else "none",
        available=[],
        pending=pending,
    )
