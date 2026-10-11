"""Unit tests for the package.json version reader and writer.

Covers:
- read_version_from_package_json: valid, missing file, invalid JSON,
  missing/empty version.
- update_version_in_package_json: version updated, other fields preserved,
  formatting (2-space indent + trailing newline).
"""

from pathlib import Path

import pytest

from cdk_factory.versioning.package_json_version import (
    read_version_from_package_json,
)
from cdk_factory.versioning.package_json_version_writer import (
    update_version_in_package_json,
)


# ---------------------------------------------------------------------------
# read_version_from_package_json
# ---------------------------------------------------------------------------


class TestReadVersionFromPackageJson:
    def test_reads_valid_version(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text(
            '{"name": "demo", "version": "1.2.3"}\n', encoding="utf-8"
        )
        assert read_version_from_package_json(tmp_path) == "1.2.3"

    def test_strips_surrounding_whitespace(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text(
            '{"version": "  2.0.1  "}\n', encoding="utf-8"
        )
        assert read_version_from_package_json(tmp_path) == "2.0.1"

    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            read_version_from_package_json(tmp_path)

    def test_invalid_json_raises_value_error(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ValueError):
            read_version_from_package_json(tmp_path)

    def test_non_object_json_raises_value_error(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(ValueError):
            read_version_from_package_json(tmp_path)

    def test_missing_version_raises_value_error(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"name": "demo"}', encoding="utf-8")
        with pytest.raises(ValueError):
            read_version_from_package_json(tmp_path)

    def test_empty_version_raises_value_error(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"version": "   "}', encoding="utf-8")
        with pytest.raises(ValueError):
            read_version_from_package_json(tmp_path)

    def test_non_string_version_raises_value_error(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"version": 123}', encoding="utf-8")
        with pytest.raises(ValueError):
            read_version_from_package_json(tmp_path)


# ---------------------------------------------------------------------------
# update_version_in_package_json
# ---------------------------------------------------------------------------


class TestUpdateVersionInPackageJson:
    def test_updates_version(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text(
            '{"name": "demo", "version": "1.2.3"}\n', encoding="utf-8"
        )
        update_version_in_package_json(tmp_path, "1.2.99")
        assert read_version_from_package_json(tmp_path) == "1.2.99"

    def test_preserves_other_fields(self, tmp_path: Path) -> None:
        import json

        original = {
            "name": "demo",
            "version": "1.2.3",
            "scripts": {"build": "vite build"},
            "dependencies": {"vue": "^3.0.0"},
            "private": True,
        }
        (tmp_path / "package.json").write_text(
            json.dumps(original, indent=2) + "\n", encoding="utf-8"
        )

        update_version_in_package_json(tmp_path, "1.2.42")

        data = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
        assert data["version"] == "1.2.42"
        assert data["name"] == "demo"
        assert data["scripts"] == {"build": "vite build"}
        assert data["dependencies"] == {"vue": "^3.0.0"}
        assert data["private"] is True

    def test_formatting_indent_and_trailing_newline(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text(
            '{"name":"demo","version":"1.0.0"}', encoding="utf-8"
        )
        update_version_in_package_json(tmp_path, "1.0.5")

        content = (tmp_path / "package.json").read_text(encoding="utf-8")
        assert content.endswith("\n")
        # 2-space indent produces lines like '  "name": "demo",'
        assert '  "name": "demo"' in content
        assert '  "version": "1.0.5"' in content

    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            update_version_in_package_json(tmp_path, "1.0.0")

    def test_invalid_json_raises_value_error(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{not valid", encoding="utf-8")
        with pytest.raises(ValueError):
            update_version_in_package_json(tmp_path, "1.0.0")
