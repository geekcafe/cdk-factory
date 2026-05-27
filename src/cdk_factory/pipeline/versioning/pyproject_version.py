"""Read project version from pyproject.toml.

Ported from aplos_saas_devops_cdk.versioning.pyproject_version with
import paths updated and TOML parser fallback chain added.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Union


def _load_toml(text: str) -> dict:
    """Load TOML text using the best available parser.

    Fallback chain:
      1. tomllib (stdlib, Python 3.11+)
      2. tomli (third-party, API-compatible with tomllib)
      3. toml (third-party, older API)
    """
    if sys.version_info >= (3, 11):
        import tomllib  # noqa: F401

        return tomllib.loads(text)

    try:
        import tomli  # type: ignore[import-untyped]

        return tomli.loads(text)
    except ModuleNotFoundError:
        pass

    import toml  # type: ignore[import-untyped]

    return toml.loads(text)


def read_project_version_from_pyproject(project_root: Union[str, Path]) -> str:
    """Read the version field from pyproject.toml at the given project root.

    Args:
        project_root: Path to the project root directory containing pyproject.toml.

    Returns:
        The version string from the [project] table.

    Raises:
        FileNotFoundError: If pyproject.toml does not exist at the given root.
        ValueError: If the [project] section or version field is missing/empty.
    """
    root = Path(project_root)
    pyproject_path = root / "pyproject.toml"

    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found at: {pyproject_path}")

    data = _load_toml(pyproject_path.read_text(encoding="utf-8"))

    project = data.get("project")
    if not isinstance(project, dict):
        raise ValueError("Missing [project] section in pyproject.toml")

    version = project.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("Missing or empty project.version in pyproject.toml")

    return version.strip()
