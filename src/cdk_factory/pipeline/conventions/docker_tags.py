"""Docker tag resolution for environment-specific tagging conventions.

Ported from aplos_saas_devops_cdk.conventions.docker_tags with import paths
updated to cdk_factory.pipeline.conventions.
"""

from __future__ import annotations

from typing import Iterable, List, Optional


def resolve_docker_tags(
    *,
    environment: str,
    version: str,
    additional_tags: Optional[Iterable[str]] = None,
) -> List[str]:
    """Resolve the list of Docker tags for a given environment and version.

    Args:
        environment: The deployment environment name (e.g., "prod", "dev", "integration").
        version: The version string to use as the primary tag.
        additional_tags: Optional extra tags to append (duplicates are removed).

    Returns:
        A deduplicated list of Docker tags where:
        - The version is always the first element.
        - For ``prod``: only the version tag is included.
        - For ``dev`` or ``integration``: the version, environment name, and ``latest``.
        - For any other non-prod environment: the version and ``latest``.

    Raises:
        ValueError: If environment is empty or missing.
        ValueError: If version is empty or missing.
    """
    env = (environment or "").strip().lower()
    if not env:
        raise ValueError("environment is required")
    if not version or not str(version).strip():
        raise ValueError("version is required")

    tags: List[str] = [str(version).strip()]

    if env != "prod":
        if env in ("dev", "integration"):
            tags.append(env)
        tags.append("latest")

    if additional_tags:
        tags.extend([t for t in additional_tags if t])

    seen: set[str] = set()
    return [t for t in tags if not (t in seen or seen.add(t))]  # type: ignore[func-returns-value]
