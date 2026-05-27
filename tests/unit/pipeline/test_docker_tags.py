"""Unit tests for cdk_factory.pipeline.conventions.docker_tags."""

import pytest

from cdk_factory.pipeline.conventions.docker_tags import resolve_docker_tags


def test_resolve_docker_tags_prod_only_version() -> None:
    """For prod, only the version tag is returned."""
    assert resolve_docker_tags(environment="prod", version="1.2.3") == ["1.2.3"]


def test_resolve_docker_tags_dev_includes_env_and_latest() -> None:
    """For dev, version + environment name + latest are returned."""
    assert resolve_docker_tags(environment="dev", version="1.2.3") == [
        "1.2.3",
        "dev",
        "latest",
    ]


def test_resolve_docker_tags_integration_includes_env_and_latest() -> None:
    """For integration, version + environment name + latest are returned."""
    assert resolve_docker_tags(environment="integration", version="1.2.3") == [
        "1.2.3",
        "integration",
        "latest",
    ]


def test_resolve_docker_tags_other_non_prod_includes_latest() -> None:
    """For other non-prod environments, version + latest are returned."""
    assert resolve_docker_tags(environment="qa", version="1.2.3") == ["1.2.3", "latest"]


def test_resolve_docker_tags_staging_includes_latest() -> None:
    """Staging is another non-prod environment that gets version + latest."""
    assert resolve_docker_tags(environment="staging", version="2.0.0") == [
        "2.0.0",
        "latest",
    ]


def test_resolve_docker_tags_dedupes_additional_tags() -> None:
    """Additional tags are appended but duplicates are removed."""
    assert resolve_docker_tags(
        environment="dev", version="1.2.3", additional_tags=["dev", "x"]
    ) == ["1.2.3", "dev", "latest", "x"]


def test_resolve_docker_tags_requires_environment() -> None:
    """Empty environment raises ValueError."""
    with pytest.raises(ValueError, match="environment is required"):
        resolve_docker_tags(environment="", version="1.2.3")


def test_resolve_docker_tags_none_environment_raises() -> None:
    """None environment raises ValueError."""
    with pytest.raises(ValueError, match="environment is required"):
        resolve_docker_tags(environment=None, version="1.2.3")  # type: ignore[arg-type]


def test_resolve_docker_tags_whitespace_only_environment_raises() -> None:
    """Whitespace-only environment raises ValueError."""
    with pytest.raises(ValueError, match="environment is required"):
        resolve_docker_tags(environment="   ", version="1.2.3")


def test_resolve_docker_tags_version_is_first_element() -> None:
    """Version is always the first element in the returned list."""
    result = resolve_docker_tags(environment="dev", version="5.6.7")
    assert result[0] == "5.6.7"


def test_resolve_docker_tags_case_insensitive_environment() -> None:
    """Environment matching is case-insensitive."""
    assert resolve_docker_tags(environment="PROD", version="1.0.0") == ["1.0.0"]
    assert resolve_docker_tags(environment="Dev", version="1.0.0") == [
        "1.0.0",
        "dev",
        "latest",
    ]
