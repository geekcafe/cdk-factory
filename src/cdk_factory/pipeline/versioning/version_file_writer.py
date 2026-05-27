"""
Update version in version.py file.
"""

from pathlib import Path


def _normalize_package_name(name: str) -> str:
    """Normalize a PEP 503 distribution name to a Python package directory name.

    Converts dashes to underscores and lowercases, matching how pip/setuptools
    map distribution names (e.g. ``My-Cool-Package``) to importable
    package directories (e.g. ``my_cool_package``).
    """
    return name.lower().replace("-", "_")


def update_version_in_version_py(
    project_root: str, package_name: str, version: str
) -> None:
    """
    Update the __version__ variable in src/{package_name}/version.py.

    Args:
        project_root: Path to the project root directory
        package_name: Package name (e.g., "my_package" or "My-Cool-Package")
        version: New version string (e.g., "3.0.47")

    Raises:
        FileNotFoundError: If version.py doesn't exist
    """
    normalized = _normalize_package_name(package_name)
    version_py_path = Path(project_root) / "src" / normalized / "version.py"

    if not version_py_path.exists():
        raise FileNotFoundError(f"version.py not found at {version_py_path}")

    # Write new version.py content
    content = f"__version__ = '{version}'\n"
    version_py_path.write_text(content, encoding="utf-8")

    print(f"✓ Updated {version_py_path} to version: {version}")
