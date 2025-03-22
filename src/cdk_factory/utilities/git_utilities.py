"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import os
import subprocess


class GitUtilities:
    """Git Utilities"""

    @staticmethod
    def get_current_git_branch() -> str | None:
        """
        Get the current branch that your on

        Returns:
            str | None: The git branch or None
        """
        try:
            # Run the Git command to get the current branch name
            branch_name: str | None = (
                subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"])
                .strip()
                .decode()
            )

            if str(branch_name).upper() == "HEAD":
                # GIT_BRANCH_NAME is being passed into CodeBuild
                branch_name = os.getenv("GIT_BRANCH_NAME")

            return branch_name
        except subprocess.CalledProcessError as e:
            print(f"Error getting current Git branch: {e}")
            return None

    @staticmethod
    def get_git_commit_hash() -> str | None:
        """
        Gets the current git commit hash
        Returns:
            str | None : the git hash or None
        """
        try:
            # Run the git command to get the current commit hash
            commit_hash = (
                subprocess.check_output(["git", "rev-parse", "HEAD"])
                .decode("utf-8")
                .strip()
            )
            return commit_hash
        except subprocess.CalledProcessError:
            print(
                "An error occurred while trying to fetch the current Git commit hash."
            )
            return None
