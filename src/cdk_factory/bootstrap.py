"""
Bootstrap utilities for cdk-factory.

Provides cache invalidation logic for virtual environment dependency management.
"""

from pathlib import Path


def needs_install(requirements_path: Path, marker_path: Path) -> bool:
    """Determine if dependencies need (re)installation.

    Returns True if:
      - marker file does not exist, OR
      - requirements file mtime > marker file mtime

    Args:
        requirements_path: Path to the requirements file (e.g., requirements.txt).
        marker_path: Path to the marker file (e.g., .venv/.installed).

    Returns:
        True if installation is needed, False if dependencies are up to date.
    """
    if not marker_path.exists():
        return True
    return requirements_path.stat().st_mtime > marker_path.stat().st_mtime
