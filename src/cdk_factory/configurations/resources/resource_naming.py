"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import base64
import hashlib
import re
from typing import Any, Dict, List

from cdk_factory.configurations.resources.resource_types import (
    ResourceMap,
    ResourceTypes,
)


class ResourceNaming:
    """Utility for standardizing resource names across various AWS resource types."""

    @staticmethod
    def shorten_name(input_string: str, length: int = 100) -> str:
        """
        Returns a shortened version of input_string if it exceeds the given length.
        The approach is to take a truncated version of the input and append a hash suffix.
        """
        if len(input_string) < length:
            return input_string

        full_hash = ResourceNaming.base64_hash(input_string)
        # Determine portions for the name and the hash (reserve 1 character for the separator)
        short_name_length = int(length * 0.66)
        short_hash_length = int(length * 0.34) - 1

        # Adjust if the total length exceeds allowed length
        total_length = short_name_length + short_hash_length
        if total_length > length:
            short_name_length -= total_length - length

        short_name = input_string[:short_name_length]
        short_hash = full_hash[:short_hash_length]
        return f"{short_name}-{short_hash}"

    @staticmethod
    def base64_hash(input_string: str) -> str:
        """
        Returns a base64-encoded SHA-256 hash of the input string,
        with any non-alphanumeric characters (except underscores and dashes) removed.
        """
        hash_object = hashlib.sha256(input_string.encode())
        full_hash = base64.b64encode(hash_object.digest()).decode("utf-8")
        return re.sub(r"[^a-zA-Z0-9_-]", "", full_hash)

    @staticmethod
    def _ensure_max_length(
        name: str, max_length: int, fix: bool, error_msg: str
    ) -> str:
        """
        Checks that the given name does not exceed max_length.
        If it does and fix is True, returns a shortened name;
        otherwise, raises a ValueError with error_msg.
        """
        if len(name) > max_length:
            if not fix:
                raise ValueError(error_msg)
            name = ResourceNaming.shorten_name(name, max_length)

        return name

    @staticmethod
    def _ensure_max_length_x(name: str, resource_type: ResourceTypes, fix: bool) -> str:
        """
        Checks that the given name does not exceed max_length.
        If it does and fix is True, returns a shortened name;
        otherwise, raises a ValueError with error_msg.
        """
        # find it by ResourceMap.type
        items: List[Dict[str, Any]] = ResourceMap

        resource = next((item for item in items if item["type"] == resource_type), None)

        if resource is not None:
            resource_name = resource.get("name", "Resource")

            max_length = resource.get("max_length", 2024)
            if len(name) > max_length:
                if not fix:
                    error_message = (
                        (
                            f"{resource_name} names cannot be longer than {max_length} characters. "
                            f"{resource_name} {name} is {len(name)} characters long. "
                            "Please use a shorter name or enable auto-fix."
                        ),
                    )

                    raise ValueError(error_message)
                new_name = ResourceNaming.shorten_name(name, max_length)
                print(
                    f"⚠️ Warning: {resource_name} {name} length too long ... auth fixing to {new_name}"
                )
            name = ResourceNaming.shorten_name(name, max_length)

        return name

    @staticmethod
    def validate_name(
        resource_name: str, resource_type: ResourceTypes, fix: bool = False
    ) -> str:
        """
        Validates and standardizes a resource name based on the given resource type.
        This includes:
          - Replacing invalid characters (e.g. spaces and periods for S3 Buckets)
          - Enforcing maximum length, and optionally auto-fixing by shortening the name
          - Enforcing required prefixes (e.g. "/" for Parameter Store)
        """
        if resource_type == ResourceTypes.S3_BUCKET:
            # For S3 buckets, spaces and periods are invalid.
            if " " in resource_name or "." in resource_name:
                if not fix:
                    raise ValueError(
                        "S3 Bucket names cannot contain spaces or periods. "
                        "Please use a hyphen (-) instead or enable auto-fix."
                    )
            resource_name = resource_name.replace(" ", "-").replace(".", "-")

        elif resource_type == ResourceTypes.PARAMETER_STORE:
            if not resource_name.startswith("/"):
                if not fix:
                    raise ValueError(
                        "Parameter Store names must start with a forward slash (/). "
                        "Please enable auto-fix to automatically add it."
                    )
                resource_name = f"/{resource_name}"

        elif resource_type == ResourceTypes.IAM_ROLE:
            # For S3 buckets, spaces and periods are invalid.
            resource_name = resource_name.replace(" ", "-")

        resource_name = ResourceNaming._ensure_max_length_x(
            resource_name, resource_type, fix
        )

        return resource_name
