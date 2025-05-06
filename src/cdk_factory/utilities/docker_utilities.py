"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import os
import subprocess
from pathlib import Path
from typing import List
from aws_lambda_powertools import Logger


logger = Logger(__name__)


class DockerUtilities:
    def __init__(self) -> None:
        self.build_tag: str | None = None
        self.tags: List[str] = []

    def generate_tags(
        self, repo_uri, primary_tag: str, environment: str, version: str
    ) -> List[str]:
        """
        Generates the docker tag based on the uri, tag and branch
        Args:
            repo_uri (_type_): Repo URI
            primary_tag (str): build tag
            branch (str): build branch

        Returns:
            List[str]: a tag in with the following formats ~
                "{repo_uri}:{primary_tag}_{branch}_{version}"
                "{repo_uri}:{primary_tag}_{branch}"
                "{repo_uri}:{version}"
        """
        if not environment:
            environment = "dev"

        if not version:
            version = "0.0.0"

        tags = []
        tags.append(f"{repo_uri}:{primary_tag}")
        tags.append(f"{repo_uri}:{primary_tag}_{version}")
        tags.append(f"{repo_uri}:{version}")
        tags.append(f"{repo_uri}:{environment}")

        return tags

    def execute_build(self, docker_file: str, context_path: str, tag: str) -> bool:
        """
        Issue a docker build
        Args:
            docker_file (str): _description_
            context_path (str): _description_
            tag (str): _description_

        Returns:
            bool: _description_
        """
        logger.info("executing build command")
        command = self.get_docker_build_command(
            docker_file_path=docker_file, context_path=context_path, tag=tag
        )

        return self.__run_command(command)

    def get_docker_build_command(
        self, docker_file_path: str, context_path: str, tag: str
    ) -> str:
        """
        Gets the docker build command
        Args:
            docker_file (str): path to the docker file
            context_path (str): path for the context
            tag (str): the tag we're using for this docker build

        Raises:
            FileNotFoundError: If the docker file is not found

        Returns:
            str: the docker build command in a string format of
            "docker build -f {docker_file_path} -t ${tag} {context_path}"
        """

        logger.info("getting build command")

        self.build_tag = tag

        # Extract all environment variables
        env_vars = os.environ

        # Format environment variables as Docker build arguments
        # to make this reusable and generic for any Dockerfile we're passing in all
        # environment variables will be passed as build arguments
        build_args = " ".join(
            [f'--build-arg {key}="{value}"' for key, value in env_vars.items()]
        )

        # validate docker file
        if not os.path.exists(docker_file_path):
            raise FileNotFoundError(
                f"Missing docker file.  File not found at: {docker_file_path}"
            )

        command = (
            f"docker build {build_args} -f {docker_file_path} -t {tag} {context_path}"
        )

        logger.info({"command": command})

        return command

    def execute_tag_command(self, original_tag: str, new_tag: str) -> bool:
        """Generate a docker tag"""
        command = f"docker tag {original_tag} {new_tag}"
        logger.info({"action": "execute_tag_command", "command": command})
        return self.__run_command(command=command) == 0

    def execute_push_to_aws(
        self,
        aws_region: str,
        aws_ecr_uri: str,
        tags: List[str] | None = None,
        aws_profile: str | None = None,
    ) -> bool:
        success = True
        profile = ""
        if aws_profile:
            profile = f" --profile {aws_profile}"

        login_command = f"aws ecr get-login-password --region {aws_region} {profile} | docker login --username AWS --password-stdin  {aws_ecr_uri} "

        logger.info({"action": "login_command", "command": login_command})

        if tags and self.__run_command(login_command):
            for tag in tags:
                docker_push_command = f"docker push {tag}"
                logger.info(
                    {"action": "docker_push_command", "command": docker_push_command}
                )
                success = self.__run_command(docker_push_command) == 0
        else:
            success = False

        return success

    def __run_command(self, command: str | List[str]) -> bool:
        result: subprocess.CompletedProcess[str] | None = None
        try:
            commands: str = ""
            if isinstance(command, str):
                commands = command
            elif isinstance(command, list):
                commands = " ".join(command)
            else:
                # not sure what we have here
                msg = f"Unknown type: {type(command)} for: {command}"
                logger.error(msg)
                raise RuntimeError(msg)

            result = subprocess.run(
                commands,
                stdout=None,
                stderr=None,
                text=True,
                check=False,
                shell=True,
                env=os.environ,  # pass all current environment vars
            )

            if result.returncode != 0:
                raise RuntimeError("Error during command execution")

        except subprocess.CalledProcessError as e:
            logger.error(str(e))
            raise e

        except Exception as e:  # pylint: disable=w0718
            logger.error(str(e))
            raise e

        logger.info(result.returncode)

        return result.returncode == 0


def main():
    print("Starting docker build utilities")
    ecr_uri: str | None = os.getenv("ECR_URI")
    environment: str = os.getenv("ENVIRONMENT") or "dev"
    tag: str = os.getenv("DOCKER_TAG") or environment
    branch: str = os.getenv("GIT_BRANCH") or "dev"
    version: str = os.getenv("VERSION") or "0.0.0"
    aws_profile: str | None = os.getenv("AWS_PROFILE")
    aws_region: str | None = os.getenv("DEPLOYMENT_AWS_REGION") or os.getenv(
        "AWS_REGION"
    )
    docker_file: str | None = os.getenv("DOCKER_FILE")

    # print all environment vars
    print("Printing all environment vars")
    print("-----------------------------")
    for key, value in os.environ.items():
        print(f"{key}: {value}")
    print("-----------------------------")

    if not ecr_uri:
        raise RuntimeError("Missing ECR URI. To fix add an environment var of ECR_URI")
    if not docker_file:
        raise RuntimeError(
            "Missing docker file. To fix add an environment var of DOCKER_FILE"
        )
    if not aws_region:
        raise RuntimeError(
            "Missing AWS region. To fix add an environment var of AWS_REGION"
        )

    docker: DockerUtilities = DockerUtilities()
    tags = docker.generate_tags(
        repo_uri=ecr_uri, primary_tag=tag, branch=branch, version=version
    )
    project_root = str(Path(__file__).parents[3])
    docker_file = os.path.join(project_root, docker_file)
    # set up the context to the root directory
    docker_context = project_root
    print(f"project_root: {project_root}")
    print(f"docker_file: {project_root}")
    print(f"docker_context: {project_root}")
    print(f"tags: {tags}")

    docker.execute_build(
        docker_file=docker_file, context_path=docker_context, tag=tags[0]
    )
    # add the additional tags
    primary_tag = tags[0]
    for tag in tags[1:]:
        docker.execute_tag_command(primary_tag, tag)

    docker.execute_push_to_aws(
        aws_region=aws_region, aws_ecr_uri=ecr_uri, tags=tags, aws_profile=aws_profile
    )


if __name__ == "__main__":
    main()
