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
