"""Update version in package.json file."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Union


def update_version_in_package_json(
    project_root: Union[str, Path], new_version: str
) -> None:
    """
    Update the 'version' field in package.json, preserving all other fields.

    Args:
        project_root: Path to directory containing package.json
        new_version: Version string to write (e.g. "3.0.47")

    Raises:
        FileNotFoundError: package.json not found
        ValueError: invalid JSON in existing file
    """
    root = Path(project_root)
    package_json_path = root / "package.json"

    if not package_json_path.exists():
        raise FileNotFoundError(f"package.json not found at {package_json_path}")

    content = package_json_path.read_text(encoding="utf-8")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {package_json_path}: {e}") from e

    data["version"] = new_version

    updated_content = json.dumps(data, indent=2) + "\n"
    package_json_path.write_text(updated_content, encoding="utf-8")

    print(f"✓ Updated {package_json_path} version: {new_version}")
