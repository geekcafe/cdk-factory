import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import List

import toml
from aws_lambda_powertools import Logger

logger = Logger()


def main():
    """build the artifacts"""
    project_root = Path(__file__).parent.parent

    # extract the version
    pyproject_toml = os.path.join(project_root, "pyproject.toml")
    version_file = os.path.join(project_root, "src", "cdk_factory", "version.py")
    extract_version_and_write_to_file(pyproject_toml, version_file)
    # do the build
    run_local_clean_up()

    run_build()
    run_publish()


def run_local_clean_up():
    """run a local clean up and remove older items in the dist directory"""
    root = Path(__file__).parent.parent
    dist_dir = os.path.join(root, "dist")
    if os.path.exists(dist_dir):
        # clear it out
        shutil.rmtree(dist_dir)


def run_remote_clean_up():
    """
    Clean out older versions
    """
    logger.warning("warning/info: older versions are not being cleaned out.")


def extract_version_and_write_to_file(pyproject_toml: str, version_file: str):
    """
    extract the version number from the pyproject.toml file and write it
    to the version.py file
    """
    if not os.path.exists(pyproject_toml):
        raise FileNotFoundError(
            f"The pyproject.toml file ({pyproject_toml}) not found. "
            "Please check the path and try again."
        )

    with open(pyproject_toml, "r", encoding="utf-8") as file:
        pyproject_data = toml.load(file)
        version = pyproject_data["project"]["version"]
        with open(version_file, "w", encoding="utf-8") as f:
            f.write(f"__version__ = '{version}'\n")


def run_build():
    """Run python build commands"""
    run_commands(["python", "-m", "build", "--no-isolation"])


def run_publish():
    """publish to code artifact"""

    # Set up the environment variables for the upload command
    api_token = os.getenv("PYPI_API_TOKEN")

    if not api_token:
        raise ValueError("PYPI_API_TOKEN environment variable is not set.")

    env = os.environ.copy()
    env["TWINE_USERNAME"] = "__token__"
    env["TWINE_PASSWORD"] = api_token

    run_commands(
        ["python", "-m", "twine", "upload", "dist/*"],
        env=env,
    )


def get_url(payload: str):
    """get the url from the payload"""
    value: dict = json.loads(payload)
    url = value.get("repositoryEndpoint")

    return url


def run_commands(
    commands: List[str], capture_output: bool = False, env=None
) -> str | None:
    """centralized area for running process commands"""
    try:
        # Run the publish command
        result = subprocess.run(
            commands,
            check=True,
            capture_output=capture_output,
            env=env,  # pass any environment vars
        )

        if capture_output:
            output = result.stdout.decode().strip()
            print(output)
            return output

    except subprocess.CalledProcessError as e:
        logger.exception(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
