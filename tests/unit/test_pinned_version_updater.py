"""Unit tests for PinnedVersionUpdater — tag resolution and discovery logic."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from cdk_factory.utilities.docker_version_locker import PinnedVersionUpdater


@pytest.fixture
def updater():
    """Create a PinnedVersionUpdater instance for testing."""
    return PinnedVersionUpdater(
        pinned_versions_path="/tmp/fake-pinned-versions.json",
        profile="test-profile",
        region="us-east-1",
        dry_run=False,
        repo_prefix="aplos-analytics/v3/",
    )


class TestResolveLatestByTimestamp:
    """Tests for PinnedVersionUpdater.resolve_latest_by_timestamp."""

    def test_returns_most_recent_semver_tag_by_push_time(self, updater):
        """Should return the tag with the most recent imagePushedAt among semver matches."""
        mock_ecr = MagicMock()
        mock_ecr.get_paginator.return_value.paginate.return_value = [
            {
                "imageDetails": [
                    {"imageTags": ["3.0.1"], "imagePushedAt": datetime(2024, 1, 15)},
                    {"imageTags": ["3.0.2"], "imagePushedAt": datetime(2024, 2, 20)},
                    {"imageTags": ["3.0.0"], "imagePushedAt": datetime(2023, 12, 1)},
                ]
            }
        ]

        result = updater.resolve_latest_by_timestamp(
            mock_ecr, "aplos-analytics/v3/my-service"
        )
        assert result == "3.0.2"

    def test_non_semver_tags_are_excluded(self, updater):
        """Tags like 'latest', 'dev', 'v1.0.0', '1.0.0-rc1' are excluded."""
        mock_ecr = MagicMock()
        mock_ecr.get_paginator.return_value.paginate.return_value = [
            {
                "imageDetails": [
                    {
                        "imageTags": ["latest"],
                        "imagePushedAt": datetime(2024, 3, 1),
                    },
                    {
                        "imageTags": ["dev"],
                        "imagePushedAt": datetime(2024, 3, 1),
                    },
                    {
                        "imageTags": ["v1.0.0"],
                        "imagePushedAt": datetime(2024, 3, 1),
                    },
                    {
                        "imageTags": ["1.0.0-rc1"],
                        "imagePushedAt": datetime(2024, 3, 1),
                    },
                    {
                        "imageTags": ["2.5.10"],
                        "imagePushedAt": datetime(2024, 1, 10),
                    },
                ]
            }
        ]

        result = updater.resolve_latest_by_timestamp(
            mock_ecr, "aplos-analytics/v3/my-service"
        )
        # Only 2.5.10 matches strict semver MAJOR.MINOR.PATCH
        assert result == "2.5.10"

    def test_returns_none_when_no_semver_tags_exist(self, updater):
        """Returns None when repo has no semver-matching tags."""
        mock_ecr = MagicMock()
        mock_ecr.get_paginator.return_value.paginate.return_value = [
            {
                "imageDetails": [
                    {
                        "imageTags": ["latest"],
                        "imagePushedAt": datetime(2024, 2, 1),
                    },
                    {"imageTags": ["dev"], "imagePushedAt": datetime(2024, 2, 1)},
                ]
            }
        ]

        result = updater.resolve_latest_by_timestamp(
            mock_ecr, "aplos-analytics/v3/my-service"
        )
        assert result is None

    def test_handles_repository_not_found(self, updater):
        """Returns None when repo doesn't exist (ClientError)."""
        mock_ecr = MagicMock()
        error_response = {
            "Error": {"Code": "RepositoryNotFoundException", "Message": "Not found"}
        }
        mock_ecr.get_paginator.return_value.paginate.return_value.__iter__ = MagicMock(
            side_effect=ClientError(error_response, "DescribeImages")
        )
        # Simulate the paginator raising ClientError during iteration
        mock_ecr.get_paginator.return_value.paginate.side_effect = ClientError(
            error_response, "DescribeImages"
        )

        # Re-mock to raise during paginate iteration
        mock_paginator = MagicMock()
        mock_ecr.get_paginator.return_value = mock_paginator

        def raise_client_error(**kwargs):
            raise ClientError(error_response, "DescribeImages")

        mock_paginator.paginate.side_effect = raise_client_error

        result = updater.resolve_latest_by_timestamp(
            mock_ecr, "aplos-analytics/v3/nonexistent-repo"
        )
        assert result is None


class TestFindNewRepositories:
    """Tests for PinnedVersionUpdater.find_new_repositories."""

    def test_returns_repos_in_ecr_but_not_in_file(self, updater):
        """New repos (discovered minus existing) are identified correctly."""
        discovered = [
            "aplos-analytics/v3/service-a",
            "aplos-analytics/v3/service-b",
            "aplos-analytics/v3/service-c",
        ]
        existing_ecrs = {
            "aplos-analytics/v3/service-a",
        }

        result = updater.find_new_repositories(discovered, existing_ecrs)
        assert "aplos-analytics/v3/service-b" in result
        assert "aplos-analytics/v3/service-c" in result
        assert "aplos-analytics/v3/service-a" not in result

    def test_existing_repos_not_duplicated(self, updater):
        """Repos already in the file are not returned."""
        discovered = [
            "aplos-analytics/v3/service-a",
            "aplos-analytics/v3/service-b",
        ]
        existing_ecrs = {
            "aplos-analytics/v3/service-a",
            "aplos-analytics/v3/service-b",
        }

        result = updater.find_new_repositories(discovered, existing_ecrs)
        assert result == []

    def test_returns_sorted_list(self, updater):
        """New repos are returned in sorted order."""
        discovered = [
            "aplos-analytics/v3/zebra-service",
            "aplos-analytics/v3/alpha-service",
            "aplos-analytics/v3/middle-service",
        ]
        existing_ecrs: set = set()

        result = updater.find_new_repositories(discovered, existing_ecrs)
        assert result == sorted(result)
        assert result == [
            "aplos-analytics/v3/alpha-service",
            "aplos-analytics/v3/middle-service",
            "aplos-analytics/v3/zebra-service",
        ]


class TestResolveNewEntries:
    """Tests for PinnedVersionUpdater.resolve_new_entries."""

    def test_new_repos_with_semver_get_resolved_tag(self, updater, monkeypatch):
        """New repos with semver tags get their latest tag resolved."""
        mock_ecr = MagicMock()

        # Mock resolve_latest_version on the DockerVersionLocker instance
        # that gets created inside resolve_new_entries (includes self param)
        def mock_resolve_latest_version(self_locker, ecr_client, repo_name):
            return "4.1.0"

        monkeypatch.setattr(
            "cdk_factory.utilities.docker_version_locker.DockerVersionLocker.resolve_latest_version",
            mock_resolve_latest_version,
        )

        new_repos = ["aplos-analytics/v3/new-service"]
        result = updater.resolve_new_entries(mock_ecr, new_repos)

        assert len(result) == 1
        assert result[0]["ecr"] == "aplos-analytics/v3/new-service"
        assert result[0]["tag"] == "4.1.0"

    def test_new_repos_without_semver_get_auto_tag(self, updater, monkeypatch):
        """New repos with no semver tags get tag='auto'."""
        mock_ecr = MagicMock()

        # Mock resolve_latest_version to return None (no latest tag, includes self param)
        def mock_resolve_latest_version(self_locker, ecr_client, repo_name):
            return None

        monkeypatch.setattr(
            "cdk_factory.utilities.docker_version_locker.DockerVersionLocker.resolve_latest_version",
            mock_resolve_latest_version,
        )

        # Also mock the fallback resolve_latest_by_timestamp to return None
        def mock_resolve_by_timestamp(ecr_client, repo_name):
            return None

        monkeypatch.setattr(
            updater, "resolve_latest_by_timestamp", mock_resolve_by_timestamp
        )

        new_repos = ["aplos-analytics/v3/no-semver-service"]
        result = updater.resolve_new_entries(mock_ecr, new_repos)

        assert len(result) == 1
        assert result[0]["ecr"] == "aplos-analytics/v3/no-semver-service"
        assert result[0]["tag"] == "auto"


class TestErrorHandlingAndResilience:
    """Tests for error handling in PinnedVersionUpdater methods.

    Validates Requirements 2.3, 2.4, 2.5:
    - Individual repo failures do not abort the entire run
    - Failed repos retain their existing tag value unchanged
    - Failed repos are reported in the failed_repos return value
    - ClientError during discover_repositories causes SystemExit
    - RepositoryNotFoundException for one repo doesn't stop others
    """

    def test_individual_repo_failure_does_not_abort_run(self):
        """When one repo fails resolution, others continue processing."""
        from unittest.mock import MagicMock, patch

        updater = PinnedVersionUpdater(
            pinned_versions_path="/fake/path",
            profile="test",
        )

        entries = [
            {"ecr": "aplos-analytics/v3/good-repo", "tag": "1.0.0"},
            {"ecr": "aplos-analytics/v3/bad-repo", "tag": "2.0.0"},
            {"ecr": "aplos-analytics/v3/another-good-repo", "tag": "3.0.0"},
        ]

        mock_ecr = MagicMock()

        # Patch resolve_latest_version to succeed for good repos, fail for bad
        with patch(
            "cdk_factory.utilities.docker_version_locker.DockerVersionLocker.resolve_latest_version"
        ) as mock_resolve:

            def side_effect(ecr_client, repo_name):
                if "bad-repo" in repo_name:
                    return None
                return "9.9.9"

            mock_resolve.side_effect = side_effect

            # Also patch resolve_latest_by_timestamp to return None for bad-repo
            with patch.object(
                updater, "resolve_latest_by_timestamp", return_value=None
            ) as mock_fallback:
                updated_entries, failed_repos = updater.resolve_entry_tags(
                    mock_ecr, entries
                )

        # All three entries should still be in the result
        assert len(updated_entries) == 3
        # Good repos resolved
        assert updated_entries[0]["tag"] == "9.9.9"
        assert updated_entries[2]["tag"] == "9.9.9"

    def test_failed_repos_retain_existing_tag(self):
        """Failed repos keep their original tag value unchanged."""
        from unittest.mock import MagicMock, patch

        updater = PinnedVersionUpdater(
            pinned_versions_path="/fake/path",
            profile="test",
        )

        entries = [
            {"ecr": "aplos-analytics/v3/good-repo", "tag": "1.0.0"},
            {"ecr": "aplos-analytics/v3/bad-repo", "tag": "2.0.0"},
        ]

        mock_ecr = MagicMock()

        with patch(
            "cdk_factory.utilities.docker_version_locker.DockerVersionLocker.resolve_latest_version"
        ) as mock_resolve:

            def side_effect(ecr_client, repo_name):
                if "bad-repo" in repo_name:
                    return None
                return "5.5.5"

            mock_resolve.side_effect = side_effect

            with patch.object(
                updater, "resolve_latest_by_timestamp", return_value=None
            ):
                updated_entries, failed_repos = updater.resolve_entry_tags(
                    mock_ecr, entries
                )

        # The bad repo retains its original tag
        assert updated_entries[1]["tag"] == "2.0.0"
        # The good repo is updated
        assert updated_entries[0]["tag"] == "5.5.5"

    def test_failed_repos_returned_in_failed_list(self):
        """Failed repos are reported in the failed_repos return value."""
        from unittest.mock import MagicMock, patch

        updater = PinnedVersionUpdater(
            pinned_versions_path="/fake/path",
            profile="test",
        )

        entries = [
            {"ecr": "aplos-analytics/v3/good-repo", "tag": "1.0.0"},
            {"ecr": "aplos-analytics/v3/bad-repo-1", "tag": "2.0.0"},
            {"ecr": "aplos-analytics/v3/bad-repo-2", "tag": "3.0.0"},
        ]

        mock_ecr = MagicMock()

        with patch(
            "cdk_factory.utilities.docker_version_locker.DockerVersionLocker.resolve_latest_version"
        ) as mock_resolve:

            def side_effect(ecr_client, repo_name):
                if "bad-repo" in repo_name:
                    return None
                return "7.7.7"

            mock_resolve.side_effect = side_effect

            with patch.object(
                updater, "resolve_latest_by_timestamp", return_value=None
            ):
                updated_entries, failed_repos = updater.resolve_entry_tags(
                    mock_ecr, entries
                )

        assert len(failed_repos) == 2
        assert "aplos-analytics/v3/bad-repo-1" in failed_repos
        assert "aplos-analytics/v3/bad-repo-2" in failed_repos

    def test_discover_repositories_paginator_error_exits(self, capsys):
        """ClientError during describe_repositories causes SystemExit."""
        from unittest.mock import MagicMock
        from botocore.exceptions import ClientError

        updater = PinnedVersionUpdater(
            pinned_versions_path="/fake/path",
            profile="test",
        )

        mock_ecr = MagicMock()
        mock_ecr.get_paginator.return_value.paginate.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}},
            "DescribeRepositories",
        )

        with pytest.raises(SystemExit) as exc_info:
            updater.discover_repositories(mock_ecr)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Failed to list ECR repositories" in captured.err

    def test_repository_not_found_logs_warning_continues(self):
        """RepositoryNotFoundException for one repo doesn't stop others."""
        from unittest.mock import MagicMock, patch
        from botocore.exceptions import ClientError

        updater = PinnedVersionUpdater(
            pinned_versions_path="/fake/path",
            profile="test",
        )

        entries = [
            {"ecr": "aplos-analytics/v3/existing-repo", "tag": "1.0.0"},
            {"ecr": "aplos-analytics/v3/deleted-repo", "tag": "2.0.0"},
            {"ecr": "aplos-analytics/v3/another-existing-repo", "tag": "3.0.0"},
        ]

        mock_ecr = MagicMock()

        with patch(
            "cdk_factory.utilities.docker_version_locker.DockerVersionLocker.resolve_latest_version"
        ) as mock_resolve:

            def resolve_side_effect(ecr_client, repo_name):
                if "deleted-repo" in repo_name:
                    return None  # Primary resolution fails
                return "4.4.4"

            mock_resolve.side_effect = resolve_side_effect

            # resolve_latest_by_timestamp raises RepositoryNotFoundException
            # for the deleted repo (simulated by returning None since the method
            # catches ClientError internally and returns None)
            def timestamp_side_effect(ecr_client, repo_name):
                if "deleted-repo" in repo_name:
                    return None  # Simulates repo not found — method returns None
                return None  # Not called for repos where primary succeeds

            with patch.object(
                updater,
                "resolve_latest_by_timestamp",
                side_effect=timestamp_side_effect,
            ):
                updated_entries, failed_repos = updater.resolve_entry_tags(
                    mock_ecr, entries
                )

        # Processing continued — all entries present
        assert len(updated_entries) == 3
        # Existing repos got updated
        assert updated_entries[0]["tag"] == "4.4.4"
        assert updated_entries[2]["tag"] == "4.4.4"
        # Deleted repo retained original tag
        assert updated_entries[1]["tag"] == "2.0.0"
        # Deleted repo reported as failed
        assert "aplos-analytics/v3/deleted-repo" in failed_repos


class TestWritePinnedVersions:
    """Tests for PinnedVersionUpdater.write_pinned_versions.

    Validates Requirements 4.3, 4.4:
    - Output JSON has 4-space indentation
    - Output file ends with a trailing newline
    - Original entry ordering is preserved
    - Filesystem write error exits non-zero
    """

    def test_writes_json_with_4_space_indent(self, tmp_path):
        """Output file should have 4-space indentation."""
        updater = PinnedVersionUpdater(
            pinned_versions_path=str(tmp_path / "test.json"),
            profile="test",
        )
        entries = [{"ecr": "repo/a", "tag": "1.0.0"}]
        output_path = str(tmp_path / "output.json")

        updater.write_pinned_versions(output_path, entries)

        content = (tmp_path / "output.json").read_text()
        # 4-space indent means the inner object fields are indented 8 spaces
        # (4 for array item, 4 for object field)
        assert '        "ecr": "repo/a"' in content
        # Array element start is at 4 spaces
        assert "    {" in content

    def test_writes_trailing_newline(self, tmp_path):
        """Output file should end with a newline character."""
        updater = PinnedVersionUpdater(
            pinned_versions_path=str(tmp_path / "test.json"),
            profile="test",
        )
        entries = [{"ecr": "repo/a", "tag": "1.0.0"}, {"ecr": "repo/b", "tag": "2.0.0"}]
        output_path = str(tmp_path / "output.json")

        updater.write_pinned_versions(output_path, entries)

        content = (tmp_path / "output.json").read_text()
        assert content.endswith("\n")
        # Should not end with double newline
        assert not content.endswith("\n\n")

    def test_preserves_entry_order(self, tmp_path):
        """Entries should appear in the same order they were provided."""
        updater = PinnedVersionUpdater(
            pinned_versions_path=str(tmp_path / "test.json"),
            profile="test",
        )
        entries = [
            {"ecr": "repo/zebra", "tag": "3.0.0"},
            {"ecr": "repo/alpha", "tag": "1.0.0"},
            {"ecr": "repo/middle", "tag": "2.0.0"},
        ]
        output_path = str(tmp_path / "output.json")

        updater.write_pinned_versions(output_path, entries)

        import json

        content = (tmp_path / "output.json").read_text()
        loaded = json.loads(content)
        assert loaded[0]["ecr"] == "repo/zebra"
        assert loaded[1]["ecr"] == "repo/alpha"
        assert loaded[2]["ecr"] == "repo/middle"

    def test_filesystem_error_exits_nonzero(self, tmp_path):
        """Write failure causes SystemExit with non-zero code."""
        updater = PinnedVersionUpdater(
            pinned_versions_path=str(tmp_path / "test.json"),
            profile="test",
        )
        entries = [{"ecr": "repo/a", "tag": "1.0.0"}]
        # Write to a directory that doesn't exist (unwritable path)
        bad_path = str(tmp_path / "nonexistent_dir" / "sub" / "output.json")

        with pytest.raises(SystemExit) as exc_info:
            updater.write_pinned_versions(bad_path, entries)

        assert exc_info.value.code == 1


class TestPrintDryRunReport:
    """Tests for PinnedVersionUpdater.print_dry_run_report.

    Validates Requirements 5.1:
    - Dry run does not modify the pinned versions file
    - Changed entries show old → new tags
    - Auto entries appear in separate section
    - New repositories section displayed
    - No changes prints appropriate message
    """

    def test_does_not_write_to_file(self, tmp_path):
        """Dry run report should not modify the pinned versions file."""
        import json

        pinned_file = tmp_path / "pinned.json"
        original_content = (
            json.dumps([{"ecr": "repo/a", "tag": "1.0.0"}], indent=4) + "\n"
        )
        pinned_file.write_text(original_content)

        updater = PinnedVersionUpdater(
            pinned_versions_path=str(pinned_file),
            profile="test",
            dry_run=True,
        )

        original = [{"ecr": "repo/a", "tag": "1.0.0"}]
        updated = [{"ecr": "repo/a", "tag": "2.0.0"}]
        new_entries = [{"ecr": "repo/b", "tag": "3.0.0"}]

        updater.print_dry_run_report(original, updated, new_entries)

        # File content should not have changed
        assert pinned_file.read_text() == original_content

    def test_shows_changed_entries_with_old_and_new_tags(self, capsys):
        """Changed entries show old_tag → new_tag."""
        updater = PinnedVersionUpdater(
            pinned_versions_path="/fake/path",
            profile="test",
            dry_run=True,
        )

        original = [{"ecr": "repo/service-a", "tag": "1.0.0"}]
        updated = [{"ecr": "repo/service-a", "tag": "2.0.0"}]
        new_entries = []

        updater.print_dry_run_report(original, updated, new_entries)

        captured = capsys.readouterr()
        assert "repo/service-a" in captured.out
        assert "1.0.0" in captured.out
        assert "2.0.0" in captured.out
        assert "→" in captured.out

    def test_shows_auto_entries_separately(self, capsys):
        """Auto entries appear in 'Auto (skipped)' section."""
        updater = PinnedVersionUpdater(
            pinned_versions_path="/fake/path",
            profile="test",
            dry_run=True,
        )

        original = [
            {"ecr": "repo/service-a", "tag": "1.0.0"},
            {"ecr": "repo/auto-service", "tag": "auto"},
        ]
        updated = [
            {"ecr": "repo/service-a", "tag": "2.0.0"},
            {"ecr": "repo/auto-service", "tag": "auto"},
        ]
        new_entries = []

        updater.print_dry_run_report(original, updated, new_entries)

        captured = capsys.readouterr()
        assert "Auto (skipped)" in captured.out
        assert "repo/auto-service" in captured.out

    def test_shows_new_repos_section(self, capsys):
        """Newly discovered repos appear in 'New repositories' section."""
        updater = PinnedVersionUpdater(
            pinned_versions_path="/fake/path",
            profile="test",
            dry_run=True,
        )

        original = [{"ecr": "repo/service-a", "tag": "1.0.0"}]
        updated = [{"ecr": "repo/service-a", "tag": "2.0.0"}]
        new_entries = [{"ecr": "repo/new-service", "tag": "5.0.0"}]

        updater.print_dry_run_report(original, updated, new_entries)

        captured = capsys.readouterr()
        assert "New repositories" in captured.out
        assert "repo/new-service" in captured.out
        assert "5.0.0" in captured.out

    def test_no_changes_prints_no_changes_message(self, capsys):
        """When nothing changed, prints 'No changes detected'."""
        updater = PinnedVersionUpdater(
            pinned_versions_path="/fake/path",
            profile="test",
            dry_run=True,
        )

        original = [{"ecr": "repo/service-a", "tag": "1.0.0"}]
        updated = [{"ecr": "repo/service-a", "tag": "1.0.0"}]
        new_entries = []

        updater.print_dry_run_report(original, updated, new_entries)

        captured = capsys.readouterr()
        assert "No changes detected" in captured.out


class TestPrintSummary:
    """Tests for PinnedVersionUpdater.print_summary.

    Validates Requirements 7.1, 7.2:
    - Summary includes all counts (total, updated, skipped, failed, new)
    - Warning line shown when failed > 0
    - New repos line shown when new_count > 0
    """

    def test_shows_all_counts(self, capsys):
        """Summary includes total, updated, skipped, failed, and new counts."""
        updater = PinnedVersionUpdater(
            pinned_versions_path="/fake/path",
            profile="test",
        )

        updater.print_summary(total=10, updated=5, skipped=3, failed=2, new_count=1)

        captured = capsys.readouterr()
        assert "10" in captured.out  # total
        assert "5 updated" in captured.out
        assert "3 skipped" in captured.out
        assert "2 failed" in captured.out
        assert "1 new" in captured.out

    def test_failure_warning_shown_when_failed_gt_zero(self, capsys):
        """Warning line shown when failed > 0."""
        updater = PinnedVersionUpdater(
            pinned_versions_path="/fake/path",
            profile="test",
        )

        updater.print_summary(total=5, updated=3, skipped=1, failed=1, new_count=0)

        captured = capsys.readouterr()
        assert "failed resolution" in captured.out
        assert "⚠" in captured.out or "warning" in captured.out.lower()

    def test_no_failure_warning_when_failed_zero(self, capsys):
        """No warning line when failed == 0."""
        updater = PinnedVersionUpdater(
            pinned_versions_path="/fake/path",
            profile="test",
        )

        updater.print_summary(total=5, updated=3, skipped=2, failed=0, new_count=0)

        captured = capsys.readouterr()
        assert "failed resolution" not in captured.out

    def test_new_repos_line_shown_when_new_gt_zero(self, capsys):
        """New repos line shown when new_count > 0."""
        updater = PinnedVersionUpdater(
            pinned_versions_path="/fake/path",
            profile="test",
        )

        updater.print_summary(total=5, updated=3, skipped=2, failed=0, new_count=3)

        captured = capsys.readouterr()
        assert "3 new repositories discovered" in captured.out
        assert "🆕" in captured.out or "new" in captured.out.lower()
