"""Unit tests for cdk_factory.versioning.nodejs_version_cli.compute_version.

Covers an end-to-end compute against a throwaway temp git repo in tmp_path,
plus a controlled monkeypatch of VersionBuilder.get_git_build_number for the
compose-and-write assertions. The real cdk-factory repo git history is never
touched.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from cdk_factory.utilities.version_builder import VersionBuilder
from cdk_factory.versioning.nodejs_version_cli import compute_version


def _git(args: list[str], cwd: Path) -> None:
    """Run a git command in cwd with a throwaway identity (no global config)."""
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test User",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _write_package_json(root: Path, version: str) -> None:
    (root / "package.json").write_text(
        json.dumps({"name": "demo", "version": version}, indent=2) + "\n",
        encoding="utf-8",
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_compute_version_end_to_end_git_commit_count(tmp_path: Path) -> None:
    """Version is major.minor.<commit count> with no matching tag present."""
    _write_package_json(tmp_path, "1.2.0")

    _git(["init"], tmp_path)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    _git(["add", "a.txt"], tmp_path)
    _git(["commit", "-m", "first"], tmp_path)
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    _git(["add", "b.txt"], tmp_path)
    _git(["commit", "-m", "second"], tmp_path)

    # Expected build number = total commit count (no v1.2.* tag exists).
    result = subprocess.run(
        ["git", "rev-list", "HEAD", "--count"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    expected_count = int(result.stdout.strip())
    assert expected_count == 2

    version = compute_version(str(tmp_path))

    assert version == f"1.2.{expected_count}"

    # package.json was rewritten to the computed version.
    data = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
    assert data["version"] == f"1.2.{expected_count}"
    assert data["name"] == "demo"

    # version.txt created with "{version}\n".
    version_txt = tmp_path / "version.txt"
    assert version_txt.exists()
    assert version_txt.read_text(encoding="utf-8") == f"1.2.{expected_count}\n"


def test_compute_version_composes_and_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a fixed build number, version is composed and written to both files."""
    _write_package_json(tmp_path, "4.7.0")

    monkeypatch.setattr(
        VersionBuilder, "get_git_build_number", lambda self, mm, root=None: 123
    )

    version = compute_version(str(tmp_path))

    assert version == "4.7.123"

    data = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
    assert data["version"] == "4.7.123"
    assert data["name"] == "demo"

    version_txt = tmp_path / "version.txt"
    assert version_txt.exists()
    assert version_txt.read_text(encoding="utf-8") == "4.7.123\n"
