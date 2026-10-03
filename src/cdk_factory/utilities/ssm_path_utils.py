"""
SSM Parameter Path Utilities.

Provides path normalization and construction helpers for SSM parameter paths
used during CDK synthesis. These are synth-time utilities — they don't call
AWS APIs, they just ensure paths are well-formed before being passed to
CDK constructs like StringParameter.from_string_parameter_name().

The engine treats a handful of ``ssm.imports`` values as *namespace fragments*
(e.g. ``lambda_namespace``, ``route53_namespace``, ``cognito_namespace``) that it
then composes into a full path such as ``/{namespace}/{lambda}/arn``. Those
fragments are legitimately written bare in config (``"geekcafe/prod"``) because the
composing code supplies the leading ``/``. Older strict validation rejected a bare
fragment as if it were a full path; these helpers instead *normalize* tolerant
input into a canonical path so both a bare fragment and an already-slash-prefixed
value resolve to the same correct result.

Token safety: CDK tokens and unresolved ``{{PLACEHOLDER}}`` template variables are
left untouched. Normalization never corrupts a lazily-resolved token, so these
helpers remain compatible with the "no live AWS at synth / CDK tokens only" rule.

Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

import re

from aws_cdk import Token


def _is_token_like(value: str) -> bool:
    """Return True if the value is a CDK token or contains an unresolved
    ``{{PLACEHOLDER}}`` template variable.

    Such values must not be reshaped (adding/removing slashes) because their
    final string is produced later — at deploy time (CDK token) or after template
    variable resolution ("{{WORKLOAD_NAME}}"). Collapsing or prefixing slashes on
    them would corrupt the eventual value.
    """
    if Token.is_unresolved(value):
        return True
    # Unresolved template placeholders like {{WORKLOAD_NAME}} are resolved
    # elsewhere; leave them intact here.
    if "{{" in value and "}}" in value:
        return True
    return False


def normalize_ssm_path(path: str) -> str:
    """Normalize a value that is meant to be a FULL SSM parameter path.

    Produces a canonical path that:
    - Starts with exactly one leading ``/``
    - Collapses any internal duplicate slashes (``//`` -> ``/``)
    - Has no trailing ``/`` (except a lone root ``/``)
    - Is stripped of surrounding whitespace

    The function is idempotent: ``normalize_ssm_path(normalize_ssm_path(x))`` equals
    ``normalize_ssm_path(x)``.

    CDK tokens and unresolved ``{{PLACEHOLDER}}`` values are returned unchanged so
    they are not corrupted before their real resolution.

    Args:
        path: The raw SSM parameter path or namespace fragment.

    Returns:
        A normalized path starting with "/" and containing no double slashes.

    Examples:
        >>> normalize_ssm_path("geekcafe/prod")
        '/geekcafe/prod'
        >>> normalize_ssm_path("/geekcafe/prod")
        '/geekcafe/prod'
        >>> normalize_ssm_path("geekcafe/prod/")
        '/geekcafe/prod'
        >>> normalize_ssm_path("//a//b//")
        '/a/b'
        >>> normalize_ssm_path("my-app/dev/route53/id")
        '/my-app/dev/route53/id'
    """
    if not isinstance(path, str):
        return path

    # Leave CDK tokens / unresolved template placeholders untouched.
    if _is_token_like(path):
        return path

    path = path.strip()
    if not path:
        return path

    # Collapse any consecutive slashes into a single slash.
    path = re.sub(r"/+", "/", path)
    # Ensure exactly one leading slash.
    if not path.startswith("/"):
        path = "/" + path
    # Remove trailing slash(es), but keep a lone root "/".
    if len(path) > 1:
        path = path.rstrip("/") or "/"
    return path


def resolve_nested_ssm_config(config_dict: dict, nested_key: str) -> dict:
    """Resolve a stack's ``ssm`` block, reconciling a nested module location with
    the stack top level by MERGING them per-key (nested wins).

    Some stacks (notably ``api_gateway_stack``) nest the whole ``ssm`` block
    inside their module config (``{"api_gateway": {"ssm": {...}}}``) while the
    engine's generic reads looked at the stack top level (``{"ssm": {...}}``).
    That split meant one code path (the authorizer lookup, nested) worked while
    another (lambda-route auto-discovery, top level) saw an empty block and
    failed. This helper is the single resolution rule every read site shares.

    A plain "prefer whichever block is populated" rule is NOT enough: real
    configs populate BOTH blocks with DIFFERENT keys. For example
    ``tests/unit/files/lambda/sample_config.json`` carries
    ``ssm.imports.lambda_namespace`` at the TOP level but
    ``api_gateway.ssm.imports.namespace`` NESTED, while
    ``geek-cafe-lambdas/.../api-gateway.json`` carries
    ``api_gateway.ssm.imports.lambda_namespace`` NESTED. Returning either block
    wholesale would drop the key the other side needs. So this merges:

      - Start from the top-level ``ssm`` block (base).
      - Overlay the nested ``ssm`` block on top; a key present in BOTH takes the
        nested value (nested is the module-local, more specific intent).
      - The ``imports`` sub-dict is merged the same way (per-key, nested wins)
        rather than replaced wholesale, so a ``lambda_namespace`` in one block
        and a ``user_pool_arn`` in the other both survive.

    It operates on a plain config dict so it works for any config object
    (``StackConfig``, ``EnhancedBaseConfig``, ...) via that object's
    ``.dictionary``.

    Args:
        config_dict: The stack/config dictionary.
        nested_key: The module key to look under for a nested ``ssm`` block
            (e.g. ``"api_gateway"``).

    Returns:
        The reconciled ``ssm`` configuration dict (may be empty). A fresh dict is
        returned; the inputs are not mutated.
    """
    if not isinstance(config_dict, dict):
        return {}

    top_level = config_dict.get("ssm", {})
    if not isinstance(top_level, dict):
        top_level = {}

    nested_parent = config_dict.get(nested_key, {})
    nested_ssm = nested_parent.get("ssm", {}) if isinstance(nested_parent, dict) else {}
    if not isinstance(nested_ssm, dict):
        nested_ssm = {}

    # Fast paths: only one side populated.
    if not nested_ssm:
        return dict(top_level)
    if not top_level:
        return dict(nested_ssm)

    # Both populated — merge per-key with nested winning.
    merged = dict(top_level)
    for key, value in nested_ssm.items():
        if (
            key == "imports"
            and isinstance(value, dict)
            and isinstance(merged.get("imports"), dict)
        ):
            merged_imports = dict(merged["imports"])
            merged_imports.update(value)
            merged["imports"] = merged_imports
        else:
            merged[key] = value
    return merged


def join_ssm_path(*segments: str) -> str:
    """Build an SSM parameter path from segments, tolerant of stray slashes.

    Joins the segments with ``/`` and normalizes the result, so whether a segment
    arrives as ``"geekcafe/prod"``, ``"/geekcafe/prod"`` or ``"geekcafe/prod/"`` the
    composed path is a single clean ``/geekcafe/prod/<...>`` with no ``//``.

    Empty / ``None`` segments are skipped. If any segment is a CDK token or contains
    an unresolved ``{{PLACEHOLDER}}``, the composed string is still joined but the
    normalization step preserves the token (see :func:`normalize_ssm_path`).

    Args:
        *segments: Path segments (e.g., namespace, resource_type, attribute_name).

    Returns:
        A normalized SSM path.

    Examples:
        >>> join_ssm_path("geekcafe/prod", "my-lambda", "arn")
        '/geekcafe/prod/my-lambda/arn'
        >>> join_ssm_path("/geekcafe/prod/", "/my-lambda/", "arn")
        '/geekcafe/prod/my-lambda/arn'
        >>> join_ssm_path("my-saas-app", "dev", "cognito", "user-pool-id")
        '/my-saas-app/dev/cognito/user-pool-id'
    """
    parts = [str(s) for s in segments if s is not None and str(s) != ""]
    joined = "/".join(parts)
    return normalize_ssm_path(joined)


# Backward-compatible alias: the original helper was named ``build_ssm_path``.
# ``join_ssm_path`` is the clearer name used by new call sites; keep the old name
# working so existing imports/tests don't break.
build_ssm_path = join_ssm_path
