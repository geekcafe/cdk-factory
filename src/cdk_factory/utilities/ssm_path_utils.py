"""
SSM Parameter Path Utilities.

Provides path normalization and construction helpers for SSM parameter paths
used during CDK synthesis. These are synth-time utilities — they don't call
AWS APIs, they just ensure paths are well-formed before being passed to
CDK constructs like StringParameter.from_string_parameter_name().

Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

import re


def normalize_ssm_path(path: str) -> str:
    """Normalize an SSM parameter path.

    Ensures the path:
    - Starts with exactly one leading /
    - Contains no consecutive // segments
    - Has no trailing /
    - Strips leading/trailing whitespace

    This handles the common case where a namespace from config already includes
    a leading "/" and is then prefixed with another "/" during path construction,
    producing "//namespace/key".

    Args:
        path: The raw SSM parameter path.

    Returns:
        A normalized path starting with "/" and containing no double slashes.

    Examples:
        >>> normalize_ssm_path("my-app/dev/route53/id")
        '/my-app/dev/route53/id'
        >>> normalize_ssm_path("/my-app/dev/route53/id")
        '/my-app/dev/route53/id'
        >>> normalize_ssm_path("//my-app/dev//route53/id")
        '/my-app/dev/route53/id'
        >>> normalize_ssm_path("/my-app/dev/route53/id/")
        '/my-app/dev/route53/id'
    """
    path = path.strip()
    # Collapse any consecutive slashes into a single slash
    path = re.sub(r"/+", "/", path)
    # Ensure leading slash
    if not path.startswith("/"):
        path = "/" + path
    # Remove trailing slash
    path = path.rstrip("/")
    return path


def build_ssm_path(*segments: str) -> str:
    """Build an SSM parameter path from segments.

    Joins segments with "/" and normalizes the result. Each segment can
    optionally include leading/trailing slashes — they'll be cleaned up.

    Args:
        *segments: Path segments (e.g., namespace, resource_type, attribute_name).

    Returns:
        A normalized SSM path.

    Examples:
        >>> build_ssm_path("my-saas-app", "dev", "cognito", "user-pool-id")
        '/my-saas-app/dev/cognito/user-pool-id'
        >>> build_ssm_path("/my-saas-app/dev", "route53", "hosted-zone-id")
        '/my-saas-app/dev/route53/hosted-zone-id'
        >>> build_ssm_path("/my-saas-app/dev/", "/route53/", "hosted-zone-id")
        '/my-saas-app/dev/route53/hosted-zone-id'
    """
    joined = "/".join(segments)
    return normalize_ssm_path(joined)
