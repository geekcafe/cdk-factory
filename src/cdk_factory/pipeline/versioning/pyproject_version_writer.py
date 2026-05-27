"""
Update version in pyproject.toml file.
"""

import re
from pathlib import Path


def update_version_in_pyproject(project_root: str, version: str) -> None:
    """
    Update the version field in pyproject.toml.

    Args:
        project_root: Path to the project root directory
        version: New version string (e.g., "3.0.47")

    Raises:
        ValueError: If version string is empty
        FileNotFoundError: If pyproject.toml doesn't exist
    """
    if not version:
        raise ValueError("Version string must not be empty")

    pyproject_path = Path(project_root) / "pyproject.toml"

    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

    content = pyproject_path.read_text(encoding="utf-8")

    # Match version = "x.y.z" in [project] section
    # This regex handles both single and double quotes
    pattern = r'(version\s*=\s*["\'])([^"\']+)(["\'])'

    if not re.search(pattern, content):
        raise ValueError(f"version field not found in {pyproject_path}")

    # Replace version value while preserving surrounding structure
    updated_content = re.sub(pattern, rf"\g<1>{version}\g<3>", content)

    # Write back to file
    pyproject_path.write_text(updated_content, encoding="utf-8")

    print(f"✓ Updated {pyproject_path} version: {version}")
