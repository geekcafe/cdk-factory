"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import os
import subprocess
from aws_lambda_powertools import Logger

logger = Logger()


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

    @staticmethod
    def get_version_tag(suffix: str | None = None) -> str:
        tag = None
        try:
            tag = None
            if not suffix:
                # Runs the git command to get the most recent tag reachable from the current commit
                tag = (
                    subprocess.check_output(
                        ["git", "describe", "--tags"], stderr=subprocess.STDOUT
                    )
                    .strip()
                    .decode()
                )
            else:
                tags = (
                    subprocess.check_output(
                        ["git", "tag", "--contains", "HEAD"], stderr=subprocess.STDOUT
                    )
                    .strip()
                    .decode()
                ).split("\n")

                for t in tags:
                    if suffix in t:
                        tag = t
                        break
                if not tag:
                    tag = tags[0]

            # Split the output by '-' and take the first part to ignore the commit count and hash
            # This splits the output and keeps only the tag part

            tag = tag.split("-", 1)[0]
        except subprocess.CalledProcessError as e:
            logger.exception(str(e))

        except Exception as e:  # pylint: disable=w0718
            logger.exception(str(e))
        if not tag:
            tag = "v0.0.0"

        return tag
