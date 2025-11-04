"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import aws_cdk as cdk
from aws_cdk import aws_s3 as s3

from cdk_factory.utilities.json_loading_utility import JsonLoadingUtility
from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig


class S3BucketConfig(EnhancedBaseConfig):
    """S3 Resource Configuration"""

    def __init__(self, config: dict = None) -> None:
        super().__init__(
            config or {},
            resource_type="s3",
            resource_name=config.get("name", "s3") if config else "s3",
        )
        self.__config = config

        if self.__config is None:
            raise ValueError("S3 Bucket Configuration cannot be None")

        if not isinstance(self.__config, dict):
            raise ValueError(
                "S3 Bucket Configuration must be a dictionary. Found: "
                f"{type(self.__config)}"
            )
        if not self.__config.keys():
            raise ValueError("S3 Bucket Configuration cannot be empty")

    @property
    def config(self) -> dict:
        """Returns the configuration"""
        return self.__config

    @property
    def name(self) -> str:
        """Bucket Name"""
        value: str | None = None
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("name")

        if not value:
            raise ValueError("Bucket name is not defined in the configuration")

        return value

    @property
    def exists(self) -> bool:
        """Flag if it's an existing bucket"""

        return str(self.__config.get("exists", "false")).lower() == "true"

    @property
    def enable_event_bridge(self) -> bool:
        """Determines if we send events to event bridge"""
        return str(self.__config.get("enable_event_bridge", "false")).lower() == "true"

    @property
    def public_read_access(self) -> bool:
        """Determines if the bucket is publicly readable"""
        return JsonLoadingUtility.get_boolean_setting(
            self.__config, "public_read_access", False
        )

    @property
    def enforce_ssl(self) -> bool:
        """Determines if the bucket enforces SSL"""
        return JsonLoadingUtility.get_boolean_setting(
            self.__config, "enforce_ssl", True
        )

    @property
    def versioned(self) -> bool:
        """Determines if the bucket is versioned"""
        return JsonLoadingUtility.get_boolean_setting(self.__config, "versioned", True)

    @property
    def auto_delete_objects(self) -> bool:
        """Determines if the bucket auto deletes objects"""
        return JsonLoadingUtility.get_boolean_setting(
            self.__config, "auto_delete_objects", False
        )

    @property
    def encryption(self) -> s3.BucketEncryption:
        """Returns the encryption type"""
        value: str | None = None
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("encryption")

        if value and isinstance(value, str):
            if value.lower() == "s3_managed":
                return s3.BucketEncryption.S3_MANAGED
            elif value.lower() == "kms_managed":
                return s3.BucketEncryption.KMS_MANAGED
            # raise ValueError("KMS Managed encryption is not yet supported")
            elif value.lower() == "kms":
                return s3.BucketEncryption.KMS

        return s3.BucketEncryption.S3_MANAGED

    @property
    def lifecycle_rules(self) -> list[dict]:
        """Returns the lifecycle rules"""
        value: list[dict] | None = None
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("lifecycle_rules")
            if value and isinstance(value, list):
                return value
            else:
                return []
            # raise ValueError("Lifecycle rules must be a list of dictionaries")

        return []

    @property
    def removal_policy(self) -> cdk.RemovalPolicy:
        """The Removal policy"""
        value = self.config.get("removal_policy", "retain")
        if isinstance(value, str):
            value = value.lower()
        
        if value == "destroy":
            return cdk.RemovalPolicy.DESTROY
        elif value == "snapshot":
            return cdk.RemovalPolicy.SNAPSHOT
        else:
            return cdk.RemovalPolicy.RETAIN

    @property
    def access_control(self) -> s3.BucketAccessControl:
        """Returns the access control"""
        value: str | None = None
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("access_control")

        if value and isinstance(value, str):
            if value.lower() == "public_read":
                return s3.BucketAccessControl.PUBLIC_READ
            elif value.lower() == "public_read_write":
                return s3.BucketAccessControl.PUBLIC_READ_WRITE
            elif value.lower() == "private":
                return s3.BucketAccessControl.PRIVATE

        return s3.BucketAccessControl.PRIVATE

    @property
    def block_public_access(self) -> s3.BlockPublicAccess:
        """Returns the block public access"""
        value: str | None = None
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("block_public_access")

        if value and isinstance(value, str):
            if value.lower() == "disabled":
                # For public website hosting, disable block public access
                return s3.BlockPublicAccess(
                    block_public_acls=False,
                    block_public_policy=False,
                    ignore_public_acls=False,
                    restrict_public_buckets=False
                )
            elif value.lower() == "block_acls":
                return s3.BlockPublicAccess.BLOCK_ACLS
            # elif value.lower() == "block_public_acls":
            #     return s3.BlockPublicAccess.block_public_acls
            # elif value.lower() == "block_public_policy":
            #     return s3.BlockPublicAccess.block_public_policy
            elif value.lower() == "block_all":
                return s3.BlockPublicAccess.BLOCK_ALL
            else:
                return s3.BlockPublicAccess.BLOCK_ALL
        if not value:
            return s3.BlockPublicAccess.BLOCK_ALL

        # return value
