"""
Unit tests for DockerVersionLocker utility.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from cdk_factory.utilities.docker_version_locker import DockerVersionLocker


class TestLoadLockedVersions:
    """Tests for load_locked_versions."""

    def test_load_valid_json_array(self, tmp_path):
        """Load a valid JSON array file."""
        entries = [
            {"name": "get-tenant", "tag": "3.3.29", "ecr": "repo/core"},
            {"name": "download", "tag": "1.0.0", "ecr": "repo/files"},
        ]
        path = tmp_path / "locked.json"
        path.write_text(json.dumps(entries, indent=4) + "\n")

        locker = DockerVersionLocker(locked_versions_path=str(path), profile="test")
        result = locker.load_locked_versions(str(path))
        assert result == entries

    def test_load_empty_array(self, tmp_path):
        """Load an empty JSON array."""
        path = tmp_path / "locked.json"
        path.write_text("[]\n")

        locker = DockerVersionLocker(locked_versions_path=str(path), profile="test")
        result = locker.load_locked_versions(str(path))
        assert result == []

    def test_load_invalid_json(self, tmp_path):
        """Raise ValueError for invalid JSON."""
        path = tmp_path / "locked.json"
        path.write_text("{not valid json}")

        locker = DockerVersionLocker(locked_versions_path=str(path), profile="test")
        with pytest.raises(ValueError, match="Invalid JSON"):
            locker.load_locked_versions(str(path))

    def test_load_json_object_not_array(self, tmp_path):
        """Raise ValueError when JSON is an object, not an array."""
        path = tmp_path / "locked.json"
        path.write_text('{"key": "value"}')

        locker = DockerVersionLocker(locked_versions_path=str(path), profile="test")
        with pytest.raises(ValueError, match="JSON array"):
            locker.load_locked_versions(str(path))

    def test_load_file_not_found(self):
        """Raise FileNotFoundError for missing file."""
        locker = DockerVersionLocker(
            locked_versions_path="/nonexistent", profile="test"
        )
        with pytest.raises(FileNotFoundError):
            locker.load_locked_versions("/nonexistent/file.json")


class TestWriteLockedVersions:
    """Tests for write_locked_versions."""

    def test_write_with_indent_and_newline(self, tmp_path):
        """Verify 4-space indent and trailing newline."""
        entries = [{"name": "svc", "tag": "1.0.0", "ecr": "repo/svc"}]
        path = tmp_path / "locked.json"

        locker = DockerVersionLocker(locked_versions_path=str(path), profile="test")
        locker.write_locked_versions(str(path), entries)

        content = path.read_text()
        assert content == json.dumps(entries, indent=4) + "\n"
        assert content.endswith("\n")
        # Verify 4-space indent is present
        assert "    " in content

    def test_write_empty_array(self, tmp_path):
        """Write an empty array."""
        path = tmp_path / "locked.json"

        locker = DockerVersionLocker(locked_versions_path=str(path), profile="test")
        locker.write_locked_versions(str(path), [])

        content = path.read_text()
        assert content == "[]\n"


class TestResolveLatestVersion:
    """Tests for resolve_latest_version."""

    def _make_ecr_client(self, images=None, error_code=None):
        """Helper to create a mock ECR client."""
        client = MagicMock()
        if error_code:
            error_response = {"Error": {"Code": error_code, "Message": "test"}}
            client.describe_images.side_effect = ClientError(
                error_response, "DescribeImages"
            )
        else:
            client.describe_images.return_value = {"imageDetails": images or []}
        return client

    def test_resolve_semver_tag(self):
        """Return the semver tag when latest and semver share a digest."""
        client = self._make_ecr_client(
            images=[{"imageTags": ["latest", "3.2.5"], "imageDigest": "sha256:abc"}]
        )
        locker = DockerVersionLocker(
            locked_versions_path="/tmp/test.json", profile="test"
        )
        result = locker.resolve_latest_version(client, "repo/core")
        assert result == "3.2.5"

    def test_resolve_picks_first_semver(self):
        """Return the first semver tag when multiple exist."""
        client = self._make_ecr_client(
            images=[
                {
                    "imageTags": ["latest", "dev", "3.2.5", "3.2.4"],
                    "imageDigest": "sha256:abc",
                }
            ]
        )
        locker = DockerVersionLocker(
            locked_versions_path="/tmp/test.json", profile="test"
        )
        result = locker.resolve_latest_version(client, "repo/core")
        assert result == "3.2.5"

    def test_resolve_no_semver_tag(self):
        """Return None when latest image has no semver tag."""
        client = self._make_ecr_client(
            images=[{"imageTags": ["latest", "dev"], "imageDigest": "sha256:abc"}]
        )
        locker = DockerVersionLocker(
            locked_versions_path="/tmp/test.json", profile="test"
        )
        result = locker.resolve_latest_version(client, "repo/core")
        assert result is None

    def test_resolve_repo_not_found(self):
        """Return None for RepositoryNotFoundException."""
        client = self._make_ecr_client(error_code="RepositoryNotFoundException")
        locker = DockerVersionLocker(
            locked_versions_path="/tmp/test.json", profile="test"
        )
        result = locker.resolve_latest_version(client, "repo/missing")
        assert result is None

    def test_resolve_image_not_found(self):
        """Return None for ImageNotFoundException (no latest tag)."""
        client = self._make_ecr_client(error_code="ImageNotFoundException")
        locker = DockerVersionLocker(
            locked_versions_path="/tmp/test.json", profile="test"
        )
        result = locker.resolve_latest_version(client, "repo/core")
        assert result is None

    def test_resolve_transient_error(self):
        """Return None for transient ECR errors."""
        client = self._make_ecr_client(error_code="ThrottlingException")
        locker = DockerVersionLocker(
            locked_versions_path="/tmp/test.json", profile="test"
        )
        result = locker.resolve_latest_version(client, "repo/core")
        assert result is None

    def test_resolve_empty_image_details(self):
        """Return None when imageDetails is empty."""
        client = self._make_ecr_client(images=[])
        locker = DockerVersionLocker(
            locked_versions_path="/tmp/test.json", profile="test"
        )
        result = locker.resolve_latest_version(client, "repo/core")
        assert result is None


class TestUpdateEntries:
    """Tests for update_entries."""

    def test_update_matching_entries(self):
        """Update tag for entries matching resolved repos."""
        entries = [
            {"name": "svc-a", "tag": "", "ecr": "repo/core"},
            {"name": "svc-b", "tag": "", "ecr": "repo/files"},
        ]
        repo_versions = {"repo/core": "3.3.29", "repo/files": "1.0.0"}

        locker = DockerVersionLocker(
            locked_versions_path="/tmp/test.json", profile="test"
        )
        updated = locker.update_entries(entries, repo_versions)

        assert updated == 2
        assert entries[0]["tag"] == "3.3.29"
        assert entries[1]["tag"] == "1.0.0"

    def test_update_leaves_unresolved_unchanged(self):
        """Leave entries unchanged when their repo is not in repo_versions."""
        entries = [
            {"name": "svc-a", "tag": "old", "ecr": "repo/core"},
            {"name": "svc-b", "tag": "old", "ecr": "repo/missing"},
        ]
        repo_versions = {"repo/core": "3.3.29"}

        locker = DockerVersionLocker(
            locked_versions_path="/tmp/test.json", profile="test"
        )
        updated = locker.update_entries(entries, repo_versions)

        assert updated == 1
        assert entries[0]["tag"] == "3.3.29"
        assert entries[1]["tag"] == "old"

    def test_update_multiple_entries_same_repo(self):
        """Update all entries referencing the same repo."""
        entries = [
            {"name": "svc-a", "tag": "", "ecr": "repo/core"},
            {"name": "svc-b", "tag": "", "ecr": "repo/core"},
        ]
        repo_versions = {"repo/core": "2.0.0"}

        locker = DockerVersionLocker(
            locked_versions_path="/tmp/test.json", profile="test"
        )
        updated = locker.update_entries(entries, repo_versions)

        assert updated == 2
        assert entries[0]["tag"] == "2.0.0"
        assert entries[1]["tag"] == "2.0.0"

    def test_update_empty_repo_versions(self):
        """No updates when repo_versions is empty."""
        entries = [{"name": "svc-a", "tag": "old", "ecr": "repo/core"}]

        locker = DockerVersionLocker(
            locked_versions_path="/tmp/test.json", profile="test"
        )
        updated = locker.update_entries(entries, {})

        assert updated == 0
        assert entries[0]["tag"] == "old"


class TestRun:
    """Tests for the run() method."""

    @patch("cdk_factory.utilities.docker_version_locker.boto3.Session")
    def test_run_success(self, mock_session_cls, tmp_path):
        """Successful run resolves versions and writes file."""
        entries = [
            {"name": "svc-a", "tag": "", "ecr": "repo/core"},
            {"name": "svc-b", "tag": "", "ecr": "repo/files"},
        ]
        path = tmp_path / "locked.json"
        path.write_text(json.dumps(entries, indent=4) + "\n")

        mock_ecr = MagicMock()
        mock_ecr.describe_images.side_effect = [
            {
                "imageDetails": [
                    {"imageTags": ["latest", "3.3.29"], "imageDigest": "sha256:a"}
                ]
            },
            {
                "imageDetails": [
                    {"imageTags": ["latest", "1.0.0"], "imageDigest": "sha256:b"}
                ]
            },
        ]
        mock_session_cls.return_value.client.return_value = mock_ecr

        locker = DockerVersionLocker(locked_versions_path=str(path), profile="test")
        exit_code = locker.run()

        assert exit_code == 0
        result = json.loads(path.read_text())
        assert result[0]["tag"] in ("3.3.29", "1.0.0")
        assert result[1]["tag"] in ("3.3.29", "1.0.0")

    @patch("cdk_factory.utilities.docker_version_locker.boto3.Session")
    def test_run_dry_run(self, mock_session_cls, tmp_path, capsys):
        """Dry run prints JSON without writing."""
        entries = [{"name": "svc-a", "tag": "", "ecr": "repo/core"}]
        path = tmp_path / "locked.json"
        path.write_text(json.dumps(entries, indent=4) + "\n")

        mock_ecr = MagicMock()
        mock_ecr.describe_images.return_value = {
            "imageDetails": [
                {"imageTags": ["latest", "2.0.0"], "imageDigest": "sha256:a"}
            ]
        }
        mock_session_cls.return_value.client.return_value = mock_ecr

        locker = DockerVersionLocker(
            locked_versions_path=str(path), profile="test", dry_run=True
        )
        exit_code = locker.run()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "[DRY RUN]" in captured.out
        # Original file should still have empty tags
        original = json.loads(path.read_text())
        assert original[0]["tag"] == ""

    def test_run_file_not_found(self):
        """Return 1 when locked versions file does not exist."""
        locker = DockerVersionLocker(
            locked_versions_path="/nonexistent/file.json", profile="test"
        )
        exit_code = locker.run()
        assert exit_code == 1

    def test_run_invalid_json(self, tmp_path):
        """Return 1 when locked versions file has invalid JSON."""
        path = tmp_path / "locked.json"
        path.write_text("not json")

        locker = DockerVersionLocker(locked_versions_path=str(path), profile="test")
        exit_code = locker.run()
        assert exit_code == 1

    @patch("cdk_factory.utilities.docker_version_locker.boto3.Session")
    def test_run_partial_failure(self, mock_session_cls, tmp_path):
        """Return 1 when some repos fail to resolve."""
        entries = [
            {"name": "svc-a", "tag": "", "ecr": "repo/core"},
            {"name": "svc-b", "tag": "", "ecr": "repo/missing"},
        ]
        path = tmp_path / "locked.json"
        path.write_text(json.dumps(entries, indent=4) + "\n")

        mock_ecr = MagicMock()

        def describe_side_effect(**kwargs):
            repo = kwargs["repositoryName"]
            if repo == "repo/core":
                return {
                    "imageDetails": [
                        {"imageTags": ["latest", "3.0.0"], "imageDigest": "sha256:a"}
                    ]
                }
            raise ClientError(
                {"Error": {"Code": "RepositoryNotFoundException", "Message": ""}},
                "DescribeImages",
            )

        mock_ecr.describe_images.side_effect = describe_side_effect
        mock_session_cls.return_value.client.return_value = mock_ecr

        locker = DockerVersionLocker(locked_versions_path=str(path), profile="test")
        exit_code = locker.run()

        assert exit_code == 1

    @patch("cdk_factory.utilities.docker_version_locker.boto3.Session")
    def test_run_empty_repos(self, mock_session_cls, tmp_path):
        """Return 0 when no ECR repos in entries."""
        entries = [{"name": "svc-a", "tag": "", "ecr": ""}]
        path = tmp_path / "locked.json"
        path.write_text(json.dumps(entries, indent=4) + "\n")

        locker = DockerVersionLocker(locked_versions_path=str(path), profile="test")
        exit_code = locker.run()

        assert exit_code == 0


class TestScanConfigDirectory:
    """Tests for scan_config_directory."""

    def _make_locker(self):
        return DockerVersionLocker(
            locked_versions_path="/tmp/test.json", profile="test"
        )

    def test_scan_finds_docker_lambda(self, tmp_path):
        """Discover a Docker Lambda from an individual resource file."""
        config = {
            "name": "get-user",
            "docker": {"image": True},
            "ecr": {"name": "repo/core", "use_existing": True},
        }
        (tmp_path / "get-user.json").write_text(json.dumps(config))

        locker = self._make_locker()
        result = locker.scan_config_directory(str(tmp_path))

        assert len(result) == 1
        assert result[0] == {"name": "get-user", "tag": "", "ecr": "repo/core"}

    def test_scan_skips_non_docker_file(self, tmp_path):
        """Skip JSON files without docker.image=true."""
        config = {"name": "plain-lambda", "runtime": "python3.12"}
        (tmp_path / "plain.json").write_text(json.dumps(config))

        locker = self._make_locker()
        result = locker.scan_config_directory(str(tmp_path))

        assert result == []

    def test_scan_skips_docker_false(self, tmp_path):
        """Skip files where docker.image is false."""
        config = {
            "name": "svc",
            "docker": {"image": False},
            "ecr": {"name": "repo/core"},
        }
        (tmp_path / "svc.json").write_text(json.dumps(config))

        locker = self._make_locker()
        result = locker.scan_config_directory(str(tmp_path))

        assert result == []

    def test_scan_skips_missing_ecr_name(self, tmp_path):
        """Skip files with docker.image=true but no ecr.name."""
        config = {"name": "svc", "docker": {"image": True}, "ecr": {}}
        (tmp_path / "svc.json").write_text(json.dumps(config))

        locker = self._make_locker()
        result = locker.scan_config_directory(str(tmp_path))

        assert result == []

    def test_scan_skips_missing_name(self, tmp_path):
        """Skip files with docker.image=true and ecr.name but no name field."""
        config = {"docker": {"image": True}, "ecr": {"name": "repo/core"}}
        (tmp_path / "svc.json").write_text(json.dumps(config))

        locker = self._make_locker()
        result = locker.scan_config_directory(str(tmp_path))

        assert result == []

    def test_scan_recursive(self, tmp_path):
        """Discover Docker Lambdas in nested subdirectories."""
        sub = tmp_path / "stacks" / "lambdas"
        sub.mkdir(parents=True)

        config1 = {
            "name": "svc-a",
            "docker": {"image": True},
            "ecr": {"name": "repo/core"},
        }
        config2 = {
            "name": "svc-b",
            "docker": {"image": True},
            "ecr": {"name": "repo/files"},
        }
        (sub / "svc-a.json").write_text(json.dumps(config1))
        (sub / "svc-b.json").write_text(json.dumps(config2))

        locker = self._make_locker()
        result = locker.scan_config_directory(str(tmp_path))

        names = {e["name"] for e in result}
        assert names == {"svc-a", "svc-b"}
        assert all(e["tag"] == "" for e in result)

    def test_scan_skips_invalid_json(self, tmp_path):
        """Skip files with invalid JSON gracefully."""
        (tmp_path / "bad.json").write_text("{not valid json}")
        config = {
            "name": "good-svc",
            "docker": {"image": True},
            "ecr": {"name": "repo/core"},
        }
        (tmp_path / "good.json").write_text(json.dumps(config))

        locker = self._make_locker()
        result = locker.scan_config_directory(str(tmp_path))

        assert len(result) == 1
        assert result[0]["name"] == "good-svc"

    def test_scan_skips_non_json_files(self, tmp_path):
        """Ignore non-.json files."""
        (tmp_path / "readme.md").write_text("# Hello")
        (tmp_path / "config.yaml").write_text("key: value")

        locker = self._make_locker()
        result = locker.scan_config_directory(str(tmp_path))

        assert result == []

    def test_scan_handles_resources_array(self, tmp_path):
        """Discover Docker Lambdas from a stack-level file with resources array."""
        config = {
            "name": "stack-name",
            "resources": [
                {
                    "name": "res-a",
                    "docker": {"image": True},
                    "ecr": {"name": "repo/core"},
                },
                {
                    "name": "res-b",
                    "docker": {"image": True},
                    "ecr": {"name": "repo/files"},
                },
                {
                    "name": "non-docker",
                    "runtime": "python3.12",
                },
            ],
        }
        (tmp_path / "stack.json").write_text(json.dumps(config))

        locker = self._make_locker()
        result = locker.scan_config_directory(str(tmp_path))

        names = {e["name"] for e in result}
        assert names == {"res-a", "res-b"}

    def test_scan_empty_directory(self, tmp_path):
        """Return empty list for an empty directory."""
        locker = self._make_locker()
        result = locker.scan_config_directory(str(tmp_path))

        assert result == []

    def test_scan_mixed_docker_and_non_docker(self, tmp_path):
        """Return only Docker Lambda entries from a mix of files."""
        docker_config = {
            "name": "docker-svc",
            "docker": {"image": True},
            "ecr": {"name": "repo/core"},
        }
        non_docker_config = {
            "name": "plain-svc",
            "description": "A non-docker lambda",
        }
        stack_config = {
            "name": "stack",
            "module": "lambda_stack",
            "resources": {"__inherits__": "./some/path"},
        }
        (tmp_path / "docker.json").write_text(json.dumps(docker_config))
        (tmp_path / "plain.json").write_text(json.dumps(non_docker_config))
        (tmp_path / "stack.json").write_text(json.dumps(stack_config))

        locker = self._make_locker()
        result = locker.scan_config_directory(str(tmp_path))

        assert len(result) == 1
        assert result[0]["name"] == "docker-svc"

    def test_scan_json_array_at_top_level(self, tmp_path):
        """Skip JSON files that contain an array at the top level."""
        (tmp_path / "array.json").write_text('[{"name": "svc"}]')

        locker = self._make_locker()
        result = locker.scan_config_directory(str(tmp_path))

        assert result == []


class TestMergeEntries:
    """Tests for merge_entries."""

    def _make_locker(self):
        return DockerVersionLocker(
            locked_versions_path="/tmp/test.json", profile="test"
        )

    def test_merge_adds_new_entries(self):
        """Add discovered entries not present in existing list."""
        existing = [
            {"name": "svc-a", "tag": "1.0.0", "ecr": "repo/core"},
        ]
        discovered = [
            {"name": "svc-b", "tag": "", "ecr": "repo/files"},
        ]

        locker = self._make_locker()
        merged, new_count, preserved_count = locker.merge_entries(existing, discovered)

        assert new_count == 1
        assert preserved_count == 0
        names = {e["name"] for e in merged}
        assert names == {"svc-a", "svc-b"}

    def test_merge_preserves_non_empty_tags(self):
        """Never overwrite an existing entry that has a non-empty tag."""
        existing = [
            {"name": "svc-a", "tag": "1.0.0", "ecr": "repo/core"},
        ]
        discovered = [
            {"name": "svc-a", "tag": "", "ecr": "repo/core"},
        ]

        locker = self._make_locker()
        merged, new_count, preserved_count = locker.merge_entries(existing, discovered)

        assert new_count == 0
        assert preserved_count == 1
        assert len(merged) == 1
        assert merged[0]["tag"] == "1.0.0"

    def test_merge_does_not_count_empty_tag_as_preserved(self):
        """Existing entries with empty tags are not counted as preserved."""
        existing = [
            {"name": "svc-a", "tag": "", "ecr": "repo/core"},
        ]
        discovered = [
            {"name": "svc-a", "tag": "", "ecr": "repo/core"},
        ]

        locker = self._make_locker()
        merged, new_count, preserved_count = locker.merge_entries(existing, discovered)

        assert new_count == 0
        assert preserved_count == 0
        assert len(merged) == 1

    def test_merge_mixed_new_and_preserved(self):
        """Handle a mix of new entries and preserved existing entries."""
        existing = [
            {"name": "svc-a", "tag": "1.0.0", "ecr": "repo/core"},
            {"name": "svc-b", "tag": "", "ecr": "repo/files"},
        ]
        discovered = [
            {"name": "svc-a", "tag": "", "ecr": "repo/core"},
            {"name": "svc-b", "tag": "", "ecr": "repo/files"},
            {"name": "svc-c", "tag": "", "ecr": "repo/new"},
        ]

        locker = self._make_locker()
        merged, new_count, preserved_count = locker.merge_entries(existing, discovered)

        assert new_count == 1
        assert preserved_count == 1
        names = {e["name"] for e in merged}
        assert names == {"svc-a", "svc-b", "svc-c"}
        # svc-a tag preserved
        svc_a = next(e for e in merged if e["name"] == "svc-a")
        assert svc_a["tag"] == "1.0.0"

    def test_merge_empty_existing(self):
        """Merge into an empty existing list adds all discovered."""
        existing = []
        discovered = [
            {"name": "svc-a", "tag": "", "ecr": "repo/core"},
            {"name": "svc-b", "tag": "", "ecr": "repo/files"},
        ]

        locker = self._make_locker()
        merged, new_count, preserved_count = locker.merge_entries(existing, discovered)

        assert new_count == 2
        assert preserved_count == 0
        assert len(merged) == 2

    def test_merge_empty_discovered(self):
        """Merge with no discovered entries returns existing unchanged."""
        existing = [
            {"name": "svc-a", "tag": "1.0.0", "ecr": "repo/core"},
        ]
        discovered = []

        locker = self._make_locker()
        merged, new_count, preserved_count = locker.merge_entries(existing, discovered)

        assert new_count == 0
        assert preserved_count == 0
        assert len(merged) == 1
        assert merged[0]["tag"] == "1.0.0"

    def test_merge_both_empty(self):
        """Merge two empty lists returns empty."""
        locker = self._make_locker()
        merged, new_count, preserved_count = locker.merge_entries([], [])

        assert merged == []
        assert new_count == 0
        assert preserved_count == 0


class TestRunSeedMode:
    """Tests for seed mode in the run() method."""

    @patch("cdk_factory.utilities.docker_version_locker.boto3.Session")
    def test_run_seed_creates_new_file(self, mock_session_cls, tmp_path):
        """Seed mode creates a new locked versions file when none exists."""
        config_dir = tmp_path / "configs"
        config_dir.mkdir()
        config = {
            "name": "svc-a",
            "docker": {"image": True},
            "ecr": {"name": "repo/core"},
        }
        (config_dir / "svc-a.json").write_text(json.dumps(config))

        locked_path = tmp_path / "locked.json"

        mock_ecr = MagicMock()
        mock_ecr.describe_images.return_value = {
            "imageDetails": [
                {"imageTags": ["latest", "2.0.0"], "imageDigest": "sha256:a"}
            ]
        }
        mock_session_cls.return_value.client.return_value = mock_ecr

        locker = DockerVersionLocker(
            locked_versions_path=str(locked_path),
            profile="test",
            seed=True,
            config_dir=str(config_dir),
        )
        exit_code = locker.run()

        assert exit_code == 0
        result = json.loads(locked_path.read_text())
        assert len(result) == 1
        assert result[0]["name"] == "svc-a"
        # After ECR resolution, tag should be resolved
        assert result[0]["tag"] == "2.0.0"

    @patch("cdk_factory.utilities.docker_version_locker.boto3.Session")
    def test_run_seed_merges_with_existing(self, mock_session_cls, tmp_path):
        """Seed mode merges new entries into existing file, preserving pinned tags."""
        config_dir = tmp_path / "configs"
        config_dir.mkdir()
        config_a = {
            "name": "svc-a",
            "docker": {"image": True},
            "ecr": {"name": "repo/core"},
        }
        config_b = {
            "name": "svc-b",
            "docker": {"image": True},
            "ecr": {"name": "repo/files"},
        }
        (config_dir / "svc-a.json").write_text(json.dumps(config_a))
        (config_dir / "svc-b.json").write_text(json.dumps(config_b))

        # Existing file with svc-a already pinned
        locked_path = tmp_path / "locked.json"
        existing = [{"name": "svc-a", "tag": "1.0.0", "ecr": "repo/core"}]
        locked_path.write_text(json.dumps(existing, indent=4) + "\n")

        mock_ecr = MagicMock()
        mock_ecr.describe_images.side_effect = [
            {
                "imageDetails": [
                    {"imageTags": ["latest", "3.0.0"], "imageDigest": "sha256:a"}
                ]
            },
            {
                "imageDetails": [
                    {"imageTags": ["latest", "2.0.0"], "imageDigest": "sha256:b"}
                ]
            },
        ]
        mock_session_cls.return_value.client.return_value = mock_ecr

        locker = DockerVersionLocker(
            locked_versions_path=str(locked_path),
            profile="test",
            seed=True,
            config_dir=str(config_dir),
        )
        exit_code = locker.run()

        assert exit_code == 0
        result = json.loads(locked_path.read_text())
        assert len(result) == 2
        names = {e["name"] for e in result}
        assert names == {"svc-a", "svc-b"}

    @patch("cdk_factory.utilities.docker_version_locker.boto3.Session")
    def test_run_seed_no_docker_lambdas_found(self, mock_session_cls, tmp_path):
        """Seed mode with no Docker Lambdas creates empty file and exits 0."""
        config_dir = tmp_path / "configs"
        config_dir.mkdir()
        # Non-docker config
        (config_dir / "plain.json").write_text(json.dumps({"name": "plain"}))

        locked_path = tmp_path / "locked.json"

        locker = DockerVersionLocker(
            locked_versions_path=str(locked_path),
            profile="test",
            seed=True,
            config_dir=str(config_dir),
        )
        exit_code = locker.run()

        assert exit_code == 0
        result = json.loads(locked_path.read_text())
        assert result == []
