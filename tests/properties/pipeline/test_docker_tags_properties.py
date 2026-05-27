"""
Property-based tests for Docker tag resolution.

Feature: cdk-pipeline-commands, Property 6: Docker tag resolver produces correct tag sets per environment
Validates: Requirements 11.3
"""

from hypothesis import given, settings, assume
from hypothesis.strategies import text, sampled_from, one_of

from cdk_factory.pipeline.conventions.docker_tags import resolve_docker_tags


# Strategies for generating test inputs
_env_known = sampled_from(
    ["prod", "dev", "integration", "staging", "qa", "uat", "sandbox"]
)
_env_random = text(
    min_size=1, max_size=30, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_"
)
_environment_strategy = one_of(_env_known, _env_random)
_version_strategy = text(
    min_size=1, max_size=40, alphabet="abcdefghijklmnopqrstuvwxyz0123456789.-"
)


class TestDockerTagResolverProperties:
    """Property tests for resolve_docker_tags().

    Feature: cdk-pipeline-commands, Property 6: Docker tag resolver produces correct tag sets per environment
    """

    @given(env=_environment_strategy, ver=_version_strategy)
    @settings(max_examples=100)
    def test_version_is_always_first_element(self, env: str, ver: str):
        """(a) The version is always the first element of the returned list.

        Validates: Requirements 11.3
        """
        # Filter out inputs that would be treated as empty after strip/lower
        assume(env.strip() != "")
        assume(ver.strip() != "")

        tags = resolve_docker_tags(environment=env, version=ver)
        assert tags[0] == ver.strip()

    @given(ver=_version_strategy)
    @settings(max_examples=100)
    def test_prod_returns_only_version(self, ver: str):
        """(b) For prod environments the list contains only the version.

        Validates: Requirements 11.3
        """
        assume(ver.strip() != "")

        tags = resolve_docker_tags(environment="prod", version=ver)
        assert tags == [ver.strip()]

    @given(env=sampled_from(["dev", "integration"]), ver=_version_strategy)
    @settings(max_examples=100)
    def test_dev_integration_returns_version_env_latest(self, env: str, ver: str):
        """(c) For dev or integration environments the list contains the version,
        the environment name, and 'latest'.

        Validates: Requirements 11.3
        """
        assume(ver.strip() != "")
        # Avoid version strings that equal the env name or "latest" to prevent dedup effects
        assume(ver.strip() != env)
        assume(ver.strip() != "latest")

        tags = resolve_docker_tags(environment=env, version=ver)
        assert ver.strip() in tags
        assert env in tags
        assert "latest" in tags
        assert len(tags) == 3

    @given(env=_environment_strategy, ver=_version_strategy)
    @settings(max_examples=100)
    def test_other_non_prod_returns_version_and_latest(self, env: str, ver: str):
        """(d) For any other non-prod environment the list contains the version and 'latest'.

        Validates: Requirements 11.3
        """
        assume(env.strip() != "")
        assume(ver.strip() != "")
        # Only test environments that are NOT prod, dev, or integration
        normalized_env = env.strip().lower()
        assume(normalized_env not in ("prod", "dev", "integration"))
        # Avoid version strings that equal "latest" to prevent dedup effects
        assume(ver.strip() != "latest")

        tags = resolve_docker_tags(environment=env, version=ver)
        assert ver.strip() in tags
        assert "latest" in tags
        assert len(tags) == 2

    @given(env=_environment_strategy, ver=_version_strategy)
    @settings(max_examples=100)
    def test_no_duplicate_entries(self, env: str, ver: str):
        """(e) There are no duplicate entries in the returned list.

        Validates: Requirements 11.3
        """
        assume(env.strip() != "")
        assume(ver.strip() != "")

        tags = resolve_docker_tags(environment=env, version=ver)
        assert len(tags) == len(set(tags))
