"""
Property-based tests for versioning utilities round-trip.

Feature: cdk-pipeline-commands
Tests correctness properties of version reading/writing.
"""

import string
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis.strategies import composite, from_regex, text

from cdk_factory.pipeline.versioning.pyproject_version import (
    read_project_version_from_pyproject,
)
from cdk_factory.pipeline.versioning.pyproject_version_writer import (
    update_version_in_pyproject,
)
from cdk_factory.pipeline.versioning.version_file_writer import (
    update_version_in_version_py,
)


# Minimal valid pyproject.toml content to seed the temp file
SEED_PYPROJECT = """\
[project]
name = "test-package"
version = "0.0.0"
"""


# --- Strategies ---


@composite
def valid_package_name(draw):
    """Generate a valid Python package name (lowercase letters, digits, underscores).

    Must start with a letter and be at least 2 characters long.
    """
    first_char = draw(text(alphabet=string.ascii_lowercase, min_size=1, max_size=1))
    rest = draw(
        text(
            alphabet=string.ascii_lowercase + string.digits + "_",
            min_size=1,
            max_size=20,
        )
    )
    return first_char + rest


# ---------------------------------------------------------------------------
# Property 4: pyproject.toml version round-trip
# ---------------------------------------------------------------------------


class TestPyprojectVersionRoundTrip:
    """
    Property 4: pyproject.toml version round-trip

    For any valid semantic version string `v` (matching `major.minor.patch` format),
    writing `v` to a pyproject.toml file via `update_version_in_pyproject()` and then
    reading it back via `read_project_version_from_pyproject()` SHALL return the
    original version string `v`.

    **Validates: Requirements 8.4, 8.5**
    """

    @given(version=from_regex(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,5}", fullmatch=True))
    @settings(max_examples=100)
    def test_write_then_read_returns_original_version(self, version: str):
        """For any valid semver string, writing to pyproject.toml and reading
        back SHALL return the original version string.

        Feature: cdk-pipeline-commands, Property 4: pyproject.toml version round-trip

        **Validates: Requirements 8.4, 8.5**
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Arrange: create a pyproject.toml with a seed version
            pyproject_file = tmp_path / "pyproject.toml"
            pyproject_file.write_text(SEED_PYPROJECT, encoding="utf-8")

            # Act: write the generated version, then read it back
            update_version_in_pyproject(str(tmp_path), version)
            result = read_project_version_from_pyproject(str(tmp_path))

            # Assert: round-trip preserves the version exactly
            assert result == version


# ---------------------------------------------------------------------------
# Property 5: version.py write round-trip
# ---------------------------------------------------------------------------


class TestVersionPyWriteRoundTrip:
    """
    Property 5: version.py write round-trip

    For any valid version string `v` and valid package name `pkg`, writing via
    `update_version_in_version_py(root, pkg, v)` SHALL produce a `version.py`
    file whose `__version__` variable equals `v`.

    **Validates: Requirements 8.6**
    """

    @given(
        version=from_regex(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,5}", fullmatch=True),
        package_name=valid_package_name(),
    )
    @settings(max_examples=100)
    def test_property_5_version_py_write_roundtrip(
        self, version: str, package_name: str
    ):
        """Writing a version via update_version_in_version_py produces a file
        whose __version__ equals the written version.

        Feature: cdk-pipeline-commands, Property 5: version.py write round-trip

        **Validates: Requirements 8.6**
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Set up the expected directory structure: src/<package>/version.py
            package_dir = tmp_path / "src" / package_name
            package_dir.mkdir(parents=True)
            version_file = package_dir / "version.py"
            # Create an initial version.py (the function requires it to exist)
            version_file.write_text("__version__ = '0.0.0'\n", encoding="utf-8")

            # Act: write the version
            update_version_in_version_py(str(tmp_path), package_name, version)

            # Assert: read back and verify __version__ equals the written version
            content = version_file.read_text(encoding="utf-8")

            # Extract __version__ value from the file
            local_vars: dict = {}
            exec(content, {}, local_vars)

            assert (
                "__version__" in local_vars
            ), f"version.py does not define __version__. Content: {content!r}"
            assert local_vars["__version__"] == version, (
                f"Expected __version__ == {version!r}, "
                f"got {local_vars['__version__']!r}. "
                f"File content: {content!r}"
            )
