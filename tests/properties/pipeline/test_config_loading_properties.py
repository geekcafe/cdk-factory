"""
Property-based tests for Docker config loading.

Feature: cdk-pipeline-commands, Property 8: Docker config loading processes all images in manifest
Validates: Requirements 3.7
"""

import json
import os
import tempfile

from hypothesis import given, settings
from hypothesis.strategies import (
    text,
    lists,
    integers,
)

from cdk_factory.pipeline.commands.docker_build_cli import (
    _load_config,
    _get_images_from_config,
)


# Strategies for generating test inputs
_repo_name_strategy = text(
    min_size=1, max_size=60, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_/."
)
_dockerfile_strategy = text(
    min_size=1, max_size=80, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_/."
)


def _image_entry(repo_name: str, dockerfile: str) -> dict:
    """Create a valid image entry dictionary."""
    return {"repo_name": repo_name, "dockerfile": dockerfile}


class TestDockerConfigLoadingProperties:
    """Property tests for Docker config loading.

    Feature: cdk-pipeline-commands, Property 8: Docker config loading processes all images in manifest
    """

    @given(
        repo_names=lists(_repo_name_strategy, min_size=0, max_size=20),
        dockerfiles=lists(_dockerfile_strategy, min_size=0, max_size=20),
    )
    @settings(max_examples=100)
    def test_load_config_preserves_all_images(
        self, repo_names: list, dockerfiles: list
    ):
        """For any valid docker-images.json with N images, loading and extracting
        images returns exactly N entries preserving repo_name and dockerfile values.

        Validates: Requirements 3.7
        """
        # Ensure both lists are the same length (use the shorter one)
        n = min(len(repo_names), len(dockerfiles))
        repo_names = repo_names[:n]
        dockerfiles = dockerfiles[:n]

        # Build the config structure
        images = [_image_entry(repo_names[i], dockerfiles[i]) for i in range(n)]
        config_data = {"images": images}

        # Write to a temporary file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            # Load the config and extract images
            loaded_config = _load_config(config_path)
            loaded_images = _get_images_from_config(loaded_config)

            # Property: exactly N images returned
            assert len(loaded_images) == n

            # Property: each image preserves repo_name and dockerfile
            for i in range(n):
                assert loaded_images[i]["repo_name"] == repo_names[i]
                assert loaded_images[i]["dockerfile"] == dockerfiles[i]
        finally:
            os.unlink(config_path)

    @given(
        num_images=integers(min_value=0, max_value=50),
    )
    @settings(max_examples=100)
    def test_image_count_matches_input_count(self, num_images: int):
        """The number of images returned always equals the number of entries
        in the images array of the config file.

        Validates: Requirements 3.7
        """
        # Build config with exactly num_images entries
        images = [
            {"repo_name": f"repo-{i}", "dockerfile": f"Dockerfile.{i}"}
            for i in range(num_images)
        ]
        config_data = {"images": images}

        # Write to a temporary file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            loaded_config = _load_config(config_path)
            loaded_images = _get_images_from_config(loaded_config)

            assert len(loaded_images) == num_images
        finally:
            os.unlink(config_path)
