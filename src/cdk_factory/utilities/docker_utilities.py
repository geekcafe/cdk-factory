"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import os
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any
from aws_lambda_powertools import Logger


logger = Logger(__name__)


class DockerUtilities:
    def __init__(self) -> None:
        self.build_tag: str | None = None
        self.tags: List[str] = []

    def get_artifact_auth_token(
        self,
        code_artifact_domain: str,
        region: str,
        profile: str | None = None,
    ) -> bool:
        command = (
            f"aws codeartifact get-authorization-token "
            f" --domain {code_artifact_domain} "
            f" --region {region} "
        )

        if profile:
            command += f" --profile {profile}"

        response = self.__run_command(command, out=subprocess.PIPE)
        token = json.loads(response.stdout.strip())["authorizationToken"]
        return token

    def login_code_artifact(
        self,
        code_artifact_domain: str,
        repository_name: str,
        region: str,
        tool: str = "pip",
        profile: str | None = None,
    ) -> bool:
        command = (
            f"aws codeartifact login "
            f" --tool {tool} "
            f" --domain {code_artifact_domain} "
            f" --repository {repository_name} "
            f" --region {region} "
        )

        if profile:
            command += f" --profile {profile}"

        response = self.__run_command(command)
        return response.stdout.strip()

    def execute_build(
        self, docker_file: str, context_path: str, tag: str, build_args: List[str]
    ) -> bool:
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
            docker_file_path=docker_file,
            context_path=context_path,
            tag=tag,
            build_args_list=build_args,
        )

        return self.__run_command(command)

    def get_docker_build_command(
        self,
        docker_file_path: str,
        context_path: str,
        tag: str,
        build_args_list: List[str] | None = None,
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

        build_args = " ".join(build_args_list) if build_args_list else ""

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

        if tags and self.__run_command(login_command).returncode == 0:

            for tag in tags:

                if aws_ecr_uri not in tag:
                    raise ValueError(
                        "The tag should be the fully qualified tag including the ecr_uri:tag"
                    )

                docker_push_command = f"docker push {tag}"
                logger.info(
                    {"action": "docker_push_command", "command": docker_push_command}
                )
                success = self.__run_command(docker_push_command).returncode == 0
        else:
            success = False

        return success

    def __run_command(
        self, command: str | list[str], out: Any = None
    ) -> subprocess.CompletedProcess[str]:
        # Normalize to a string
        if isinstance(command, list):
            cmd_str = " ".join(command)
        elif isinstance(command, str):
            cmd_str = command
        else:
            msg = f"Unknown command type: {type(command)}"
            logger.error(msg)
            raise RuntimeError(msg)

        logger.debug(f"Running shell command: {cmd_str!r}")
        result = subprocess.run(
            cmd_str,
            stdout=out,
            stderr=out,
            text=True,
            shell=True,
            env=os.environ,
        )

        if result.returncode != 0:
            # log both stdout and stderr for debugging
            logger.error(f"Command failed ({result.returncode}): {cmd_str}")
            if out:
                logger.error(f"stdout:\n{result.stdout}")
                logger.error(f"stderr:\n{result.stderr}")
            raise RuntimeError(f"Command `{cmd_str}` exited {result.returncode}")

        # return the trimmed stdout to the caller
        return result


def main():
    print("Starting docker build utilities")
    ecr_uri: str | None = os.getenv("ECR_URI")
    environment: str = os.getenv("ENVIRONMENT")
    tag: str = os.getenv("DOCKER_TAG") or environment
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

    if not environment:
        raise RuntimeError("Missing environment. To fix add an environment var of ENVIRONMENT")
    if not tag:
        raise RuntimeError("Missing tag. To fix add an environment var of DOCKER_TAG")
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
    tags = [
        f"{ecr_uri}:{tag}",
        f"{ecr_uri}:{version}",
    ]
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
