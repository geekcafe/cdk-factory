"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import re
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

        # Skip validation for unresolved placeholders
        if "{{" not in value:
            if len(value) < 3 or len(value) > 63:
                raise ValueError(
                    f"S3 bucket name '{value}' must be between 3 and 63 characters. "
                    f"Got {len(value)} characters."
                )
            if (
                not re.match(r"^[a-z0-9][a-z0-9\.\-]*[a-z0-9]$", value)
                and len(value) > 2
            ):
                raise ValueError(
                    f"S3 bucket name '{value}' must contain only lowercase letters, "
                    "numbers, hyphens, and dots, and must start and end with a "
                    "letter or number."
                )
            if ".." in value:
                raise ValueError(
                    f"S3 bucket name '{value}' must not contain consecutive dots."
                )

        return value

    @property
    def use_existing(self) -> bool:
        """Flag if we should import an existing bucket rather than create one."""
        value = self.__config.get("use_existing", "false")
        return str(value).lower() == "true"

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

    # HTTP method string-to-enum mapping for CORS configuration
    _HTTP_METHOD_MAP: dict[str, s3.HttpMethods] = {
        "GET": s3.HttpMethods.GET,
        "PUT": s3.HttpMethods.PUT,
        "POST": s3.HttpMethods.POST,
        "DELETE": s3.HttpMethods.DELETE,
        "HEAD": s3.HttpMethods.HEAD,
    }

    @property
    def cors_rules(self) -> list[s3.CorsRule]:
        """Returns the CORS rules parsed from the configuration.

        Each rule dict may contain:
        - allowed_methods: list[str] — e.g. ["GET", "PUT", "POST"]
        - allowed_origins: list[str] — e.g. ["*"]
        - allowed_headers: list[str] — e.g. ["*"]
        - exposed_headers: list[str] — e.g. ["Date"]
        - max_age: int — e.g. 3600
        """
        raw_rules: list[dict] = self.__config.get("cors_rules", [])
        if not raw_rules or not isinstance(raw_rules, list):
            return []

        cors_rules: list[s3.CorsRule] = []
        for rule in raw_rules:
            if not isinstance(rule, dict):
                continue

            # Map method strings to s3.HttpMethods enums
            allowed_methods: list[s3.HttpMethods] = []
            for method_str in rule.get("allowed_methods", []):
                mapped = self._HTTP_METHOD_MAP.get(method_str.upper())
                if mapped is None:
                    raise ValueError(
                        f"Unknown HTTP method '{method_str}' in cors_rules. "
                        f"Valid methods: {list(self._HTTP_METHOD_MAP.keys())}"
                    )
                allowed_methods.append(mapped)

            max_age_val = rule.get("max_age")
            max_age = int(max_age_val) if max_age_val is not None else None

            cors_rules.append(
                s3.CorsRule(
                    allowed_methods=allowed_methods,
                    allowed_origins=rule.get("allowed_origins", []),
                    allowed_headers=rule.get("allowed_headers", None),
                    exposed_headers=rule.get("exposed_headers", None),
                    max_age=max_age,
                )
            )

        return cors_rules

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
                    restrict_public_buckets=False,
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
