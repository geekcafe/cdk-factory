"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import base64
import hashlib
import re

from cdk_factory.configurations.resources.resource_types import ResourceTypes


class ResourceNaming:
    """Resource Naming"""

    @staticmethod
    def shorten_name(input_string: str, length=100):
        """
        Gets a short name, where we hash it if it's too long

        """
        if len(input_string) < length:
            return input_string

        full_hash = ResourceNaming.base64_hash(input_string)
        short_name_length = int((length * 0.66))
        short_hash_length = int((length * 0.34) - 1)

        total = short_name_length + short_hash_length
        if (total) > length:
            x = total - length
            short_name_length -= x

        short_name = input_string[:short_name_length]
        short_hash = full_hash[:short_hash_length]
        new_name = f"{short_name}-{short_hash}"
        return new_name

    @staticmethod
    def base64_hash(input_string: str):
        """Base64 hash"""
        hash_object = hashlib.sha256(input_string.encode())
        full_hash = base64.b64encode(hash_object.digest()).decode("utf-8")

        # Replace any characters that are not alphanumeric, underscores, or dashes
        full_hash = re.sub(r"[^a-zA-Z0-9_-]", "", full_hash)
        return full_hash

    @staticmethod
    def validate_name(
        resource_name: str, resource_type: ResourceTypes, fix: bool = False
    ) -> str:
        """Generates a standardized resource name"""
        if resource_type:
            if resource_type == ResourceTypes.S3_BUCKET:
                if " " in resource_name or "." in resource_name:
                    if not fix:
                        raise ValueError(
                            "S3 Bucket names cannot contain spaces or periods. "
                            "Please use a hyphen (-) instead. You can also use the auto-fix "
                            "feature to automatically replace spaces and periods with hyphens."
                        )
                resource_name = resource_name.replace(".", "-").replace(" ", "-")
                if len(resource_name) > 63:
                    if not fix:
                        raise ValueError(
                            "S3 Bucket names cannot be longer than 63 characters. "
                            "Please use a shorter name or use the auto-fix "
                            "feature to automatically shorten the name."
                        )
                resource_name = ResourceNaming.shorten_name(resource_name, 63)

            if resource_type == ResourceTypes.LAMBDA_FUNCTION:
                # resource_name = f"{resource_name}"
                if len(resource_name) > 64:
                    if not fix:
                        raise ValueError(
                            "Lambda Function names cannot be longer than 64 characters. "
                            "Please use a shorter name or use the auto-fix "
                            "feature to automatically shorten the name."
                        )
                resource_name = ResourceNaming.shorten_name(resource_name, 64)

            if resource_type == ResourceTypes.SQS:
                # resource_name = f"{resource_name}-queue"
                if len(resource_name) > 80:
                    if not fix:
                        raise ValueError(
                            "SQS Queue names cannot be longer than 80 characters. "
                            "Please use a shorter name or use the auto-fix "
                            "feature to automatically shorten the name."
                        )
                resource_name = ResourceNaming.shorten_name(resource_name, 80)

            if resource_type == ResourceTypes.PARAMETER_STORE:
                if not resource_name.startswith("/"):
                    if not fix:
                        raise ValueError(
                            "Parameter Store names must start with a forward slash (/). "
                            "Please use the auto-fix feature to automatically add the forward slash."
                        )
                    resource_name = f"/{resource_name}"

        return resource_name
