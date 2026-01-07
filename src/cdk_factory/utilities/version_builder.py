import os
import sys
import subprocess
from pathlib import Path
from enum import Enum
from typing import Optional, Tuple


class VersionSource(Enum):
    """Source for base version number."""

    FILE = "file"  # Read from version.txt or similar file
    GIT_TAG = "git_tag"  # Read from latest git tag


class VersionStrategy(Enum):
    """Strategy for version increment."""

    PATCH = "patch"  # Increment patch version (e.g., 1.2.3 → 1.2.4)
    MINOR = "minor"  # Increment minor version (e.g., 1.2.3 → 1.3.0)


class VersionBuilder:
    def __init__(self, version_source: VersionSource = VersionSource.FILE):
        """
        Initialize VersionBuilder with specified version source.

        Args:
            version_source: Source for base version (FILE or GIT_TAG)
        """
        self.version_source = version_source

    def get_version_from_file(self, version_file_path: str) -> str:
        """Read version from a file (e.g., version.txt)."""
        if not os.path.exists(version_file_path):
            raise ValueError(f"Invalid version file path: {version_file_path}")

        try:
            with open(version_file_path, "r") as f:
                return f.read().strip()
        except Exception as e:
            raise ValueError(f"Error reading version file: {e}")

    def get_version_from_git_tag(self, project_root: Optional[str] = None) -> str:
        """Get the latest semantic version tag from git."""
        if project_root is None:
            project_root = Path("./").resolve()

        try:
            # Get all tags sorted by version
            result = subprocess.run(
                ["git", "tag", "-l", "v*.*.*", "--sort=-version:refname"],
                cwd=project_root,
                capture_output=True,
                text=True,
                check=True,
            )

            tags = [t.strip() for t in result.stdout.strip().split("\n") if t.strip()]
            if not tags:
                raise ValueError("No semantic version tags found (format: v*.*.*)")

            latest_tag = tags[0]
            # Remove 'v' prefix if present
            version = latest_tag.lstrip("v")
            print(f"💬 Found latest git tag: {latest_tag} → {version}")
            return version

        except subprocess.CalledProcessError as e:
            raise ValueError(f"Git command failed: {e}")
        except Exception as e:
            raise ValueError(f"Error getting version from git tag: {e}")

    def get_base_version(self, version_file_path: Optional[str] = None) -> str:
        """Get base version from configured source (file or git tag)."""
        if self.version_source == VersionSource.FILE:
            if not version_file_path:
                raise ValueError("version_file_path required when using FILE source")
            return self.get_version_from_file(version_file_path)
        elif self.version_source == VersionSource.GIT_TAG:
            return self.get_version_from_git_tag()
        else:
            raise ValueError(f"Unknown version source: {self.version_source}")

    def parse_version(self, version_string: str) -> Tuple[str, str, str]:
        """Parse version string into major, minor, patch components."""
        version_parts = version_string.split(".")
        if len(version_parts) < 2:
            raise ValueError(
                f"Invalid version format: {version_string} (expected major.minor or major.minor.patch)"
            )

        major = version_parts[0]
        minor = version_parts[1]
        patch = version_parts[2] if len(version_parts) >= 3 else "0"

        return major, minor, patch

    def get_commits_since_tag(
        self, tag: str, project_root: Optional[str] = None
    ) -> int:
        """Count commits since a specific tag."""
        if project_root is None:
            project_root = Path("./").resolve()

        try:
            result = subprocess.run(
                ["git", "rev-list", f"{tag}..HEAD", "--count"],
                cwd=project_root,
                capture_output=True,
                text=True,
                check=True,
            )
            return int(result.stdout.strip())
        except subprocess.CalledProcessError as e:
            raise ValueError(f"Failed to count commits since tag {tag}: {e}")

    def get_git_build_number(
        self, major_minor_version: str, project_root: Optional[str] = None
    ) -> int:
        """
        Get build number by counting commits since the last tag matching the major.minor version.
        This automatically resets to 0 when you bump the version.

        For example:
        - If base version is "3.2", it looks for tags like "v3.2.0", "v3.2.1", etc.
        - Counts commits since the most recent matching tag
        - Returns 0 if no matching tag is found (starting fresh)
        """
        if project_root is None:
            project_root = Path("./").resolve()

        try:
            # Try to find the latest tag matching this major.minor version
            result = subprocess.run(
                [
                    "git",
                    "tag",
                    "-l",
                    f"v{major_minor_version}.*",
                    "--sort=-version:refname",
                ],
                cwd=project_root,
                capture_output=True,
                text=True,
                check=True,
            )

            tags = [t.strip() for t in result.stdout.strip().split("\n") if t.strip()]
            latest_tag = tags[0] if tags else None

            if latest_tag:
                commit_count = self.get_commits_since_tag(latest_tag, project_root)
                print(f"💬 Found tag '{latest_tag}', commits since: {commit_count}")
                return commit_count
            else:
                # No matching tag found - count all commits on current branch
                result = subprocess.run(
                    ["git", "rev-list", "HEAD", "--count"],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                commit_count = int(result.stdout.strip())
                print(
                    f"💬 No matching tag for v{major_minor_version}.*, using total commit count: {commit_count}"
                )
                return commit_count

        except subprocess.CalledProcessError as e:
            print(f"⚠️ Git command failed: {e}")
            print(f"💬 Falling back to build number from environment or 0")
            return int(os.getenv("CODEBUILD_BUILD_NUMBER", "0"))
        except Exception as e:
            print(f"⚠️ Error getting git build number: {e}")
            return int(os.getenv("CODEBUILD_BUILD_NUMBER", "0"))

    def auto_increment_minor(
        self, base_version: str, project_root: Optional[str] = None
    ) -> str:
        """
        Auto-increment minor version based on commits since last tag.

        Logic:
        - Parse base version (e.g., "3.2.0" or "3.2")
        - Count commits since last matching tag
        - If commits > 0, increment minor version and reset patch to 0
        - Return new version string

        Example:
        - Base: "3.2.0", commits: 5 → "3.3.0"
        - Base: "3.2.0", commits: 0 → "3.2.0"
        """
        major, minor, patch = self.parse_version(base_version)
        major_minor = f"{major}.{minor}"

        commit_count = self.get_git_build_number(major_minor, project_root)

        if commit_count > 0:
            new_minor = int(minor) + 1
            new_version = f"{major}.{new_minor}.0"
            print(
                f"💬 Auto-incrementing: {base_version} → {new_version} (based on {commit_count} commits)"
            )
            return new_version
        else:
            print(f"💬 No commits since last tag, keeping version: {base_version}")
            return base_version

    def build_version_with_patch(self, version_file_path: Optional[str] = None) -> str:
        """
        Build version by appending patch number (commit count) to base version.

        This is the original behavior:
        - Get base version from configured source (file or git tag)
        - Count commits since last matching tag
        - Return major.minor.patch where patch = commit count
        """
        base_version = self.get_base_version(version_file_path)
        major, minor, _ = self.parse_version(base_version)
        major_minor = f"{major}.{minor}"

        # Get build number from git (commits since last matching tag)
        build_number = self.get_git_build_number(major_minor)
        new_version = f"{major_minor}.{build_number}"

        print(f"💬 Built version: {base_version} → {new_version}")
        return new_version

    def build_version_with_auto_increment(
        self, version_file_path: Optional[str] = None
    ) -> str:
        """
        Build version by auto-incrementing minor version based on commits.

        New behavior:
        - Get base version from configured source (file or git tag)
        - If commits exist since last tag, increment minor and reset patch to 0
        - Return new version
        """
        base_version = self.get_base_version(version_file_path)
        new_version = self.auto_increment_minor(base_version)
        return new_version

    def update_version_file(
        self,
        version_file_path: str,
        strategy: VersionStrategy = VersionStrategy.PATCH,
    ):
        """
        Update version file with new version.

        Args:
            version_file_path: Path to version file to update
            strategy: Version increment strategy (PATCH or MINOR)
        """
        if strategy == VersionStrategy.MINOR:
            new_version = self.build_version_with_auto_increment(version_file_path)
        elif strategy == VersionStrategy.PATCH:
            new_version = self.build_version_with_patch(version_file_path)
        else:
            raise ValueError(f"Unknown version strategy: {strategy}")

        try:
            with open(version_file_path, "w") as f:
                f.write(new_version)
                print(f"💬 Updated version file: {version_file_path}")
                print(f"💬 New version: {new_version}")
                print(
                    f"💬 To tag this build: git tag v{new_version} && git push origin v{new_version}"
                )
        except Exception as e:
            print(f"⚠️ Error updating version file: {e}")

        return new_version


def main():
    vb: VersionBuilder = VersionBuilder(VersionSource.GIT_TAG)
    version = vb.update_version_file(
        ".test_version.txt", strategy=VersionStrategy.PATCH
    )
    print(f"Final version: {version}")


if __name__ == "__main__":
    main()
