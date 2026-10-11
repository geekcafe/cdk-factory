"""Read version from package.json file."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Union


def read_version_from_package_json(project_root: Union[str, Path]) -> str:
    """
    Read the 'version' field from package.json at the given project root.

    Args:
        project_root: Path to directory containing package.json

    Returns:
        Version string (e.g. "3.0.23")

    Raises:
        FileNotFoundError: package.json not found
        ValueError: invalid JSON or missing/empty 'version' field
    """
    root = Path(project_root)
    package_json_path = root / "package.json"
    if not package_json_path.exists():
        raise FileNotFoundError(f"package.json not found at: {package_json_path}")

    content = package_json_path.read_text(encoding="utf-8")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {package_json_path}: {e}") from e

    if not isinstance(data, dict):
        raise ValueError(
            f"Expected JSON object in {package_json_path}, got {type(data).__name__}"
        )

    version = data.get("version")
    if version is None:
        raise ValueError(f"Missing 'version' field in {package_json_path}")
    if not isinstance(version, str) or not version.strip():
        raise ValueError(f"Empty or invalid 'version' field in {package_json_path}")

    return version.strip()
