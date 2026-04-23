"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig


class ECRConfig(EnhancedBaseConfig):
    """ECR Configuration"""

    def __init__(
        self, config: dict, deployment: DeploymentConfig | None = None
    ) -> None:
        super().__init__(
            config,
            resource_type="ecr",
            resource_name=config.get("name", "ecr") if config else "ecr",
        )
        self.__config = config
        self.__deployment = deployment
        self.__ssm_prefix_template = config.get("ssm_prefix_template", None)

    @property
    def name(self) -> str:
        """Repository Name"""
        if self.__config and isinstance(self.__config, dict):
            name = self.__config.get("name", "")
            if not self.__deployment:
                raise RuntimeError("Deployment is not defined")

            return self.__deployment.build_resource_name(name)

        raise RuntimeError('ECR Configuration is missing the "name" key/value pair')

    @property
    def uri(self) -> str:
        """Repository Uri"""
        uri = None
        if self.__config and isinstance(self.__config, dict):
            uri = self.__config.get("uri")

        if not uri:
            uri = f"{self.account}.dkr.ecr.{self.region}.amazonaws.com/{self.name}"
        return uri

    @property
    def arn(self) -> str:
        """Repository Arn"""
        arn = None
        if self.__config and isinstance(self.__config, dict):
            arn = self.__config.get("arn")
        if not arn:
            arn = f"arn:aws:ecr:{self.region}:{self.account}:repository/{self.name}"
        return arn

    @property
    def image_scan_on_push(self) -> bool:
        """Perform an image scan on Push"""
        if self.__config and isinstance(self.__config, dict):
            return str(self.__config.get("image_scan_on_push")).lower() == "true"

        return False

    @property
    def empty_on_delete(self) -> bool:
        """Empty a repository on a detele request."""
        if self.__config and isinstance(self.__config, dict):
            return str(self.__config.get("empty_on_delete")).lower() == "true"

        return False

    @property
    def auto_delete_untagged_images_in_days(self) -> int | None:
        """
        Clear out untagged images after x days.  This helps save costs.
        Untagged images will stay forever if you don't clean them out.
        """
        days = None
        if self.__config and isinstance(self.__config, dict):
            days = self.__config.get("auto_delete_untagged_images_in_days")
            if days:
                days = int(days)

        return days

    @property
    def use_existing(self) -> bool:
        """
        Use Existing Repository
        """
        if self.__config and isinstance(self.__config, dict):
            return str(self.__config.get("use_existing")).lower() == "true"

        return False

    @property
    def ecr_ssm_path(self) -> str | None:
        """SSM parameter base path for resolving ECR repository details at synth time.

        Can be set explicitly, or auto-derived from ``ecr_ref`` when an SSM
        namespace is available.  Resolution order:

        1. Explicit ``ecr_ssm_path`` in config (highest priority)
        2. ``ecr_ref`` + ``ssm.namespace`` or ``ssm.imports.namespace`` → ``/{namespace}/ecr/{ecr_ref}``
        3. ``None`` (fall back to explicit name/arn/uri fields)
        """
        if self.__config and isinstance(self.__config, dict):
            # Explicit path takes priority
            explicit = self.__config.get("ecr_ssm_path")
            if explicit:
                return explicit

            # Auto-derive from ecr_ref + namespace
            ref = self.__config.get("ecr_ref")
            if ref:
                ssm_ns = self.__config.get("ssm", {}).get("namespace")
                ssm_imports_ns = (
                    self.__config.get("ssm", {}).get("imports", {}).get("namespace")
                )
                ns = ssm_ns or ssm_imports_ns
                if ns:
                    return f"/{ns}/ecr/{ref}"
                raise ValueError(
                    f"'ssm.namespace' or 'ssm.imports.namespace' is required "
                    f"when using 'ecr_ref' ('{ref}') without an explicit 'ecr_ssm_path'. "
                    f"Add a namespace to your stack config."
                )

        return None

    @property
    def ecr_ref(self) -> str | None:
        """Logical ECR repository key name for name-based lookup.

        When set, the Lambda stack resolves the ECR repository details from
        SSM using the convention ``/{workload}/{environment}/ecr/{ecr_ref}``.
        This replaces fragile array-index-based ``__inherits__`` references.
        """
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("ecr_ref")

        return None

    @property
    def account(self) -> str:
        """Account"""
        value: str | None = None
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("account")

        if not value and self.__deployment:
            value = self.__deployment.account

        if not value:
            raise RuntimeError("Account is not defined")
        return value

    @property
    def region(self) -> str:
        """Region"""
        value: str | None = None
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("region")

        if not value and self.__deployment:
            value = self.__deployment.region

        if not value:
            raise RuntimeError("Region is not defined")
        return value

    @property
    def cross_account_access(self) -> dict:
        """
        Cross-account access configuration.

        Example:
        {
            "enabled": true,
            "accounts": [os.environ.get("ECR_ALLOWED_ACCOUNT_1"), os.environ.get("ECR_ALLOWED_ACCOUNT_2")],
            "services": [
                {
                    "name": "lambda",
                    "actions": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
                    "condition": {
                        "StringLike": {
                            "aws:sourceArn": "arn:aws:lambda:*:*:function:*"
                        }
                    }
                },
                {
                    "name": "ecs-tasks",
                    "service_principal": "ecs-tasks.amazonaws.com",
                    "actions": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
                },
                {
                    "name": "codebuild",
                    "service_principal": "codebuild.amazonaws.com",
                    "actions": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
                }
            ]
        }
        """
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("cross_account_access", {})
        return {}

    @property
    def cross_account_enabled(self) -> bool:
        """Whether cross-account access is explicitly enabled"""
        access_config = self.cross_account_access
        if access_config:
            return str(access_config.get("enabled", "true")).lower() == "true"
        return True  # Default to enabled for backward compatibility

    @property
    def accounts_with_access(self) -> list[str]:
        """
        Get list of AWS account IDs that should have access to this ECR repository.

        Supports multiple configuration patterns:
        1. Direct "accounts_with_access" field with array of objects containing "id" field
        2. "cross_account_access.accounts" field with simple string array
        3. "cross_account_access.accounts" field with array of objects containing "id" field

        Returns:
            List of AWS account ID strings (region field is ignored as it's not relevant for ECR policies)

        Examples:
            # Pattern 1: accounts_with_access with objects
            {
                "accounts_with_access": [
                    {"id": "123456789012", "description": "dev"},
                    {"id": "987654321098", "description": "prod"}
                ]
            }

            # Pattern 2: cross_account_access.accounts with strings
            {
                "cross_account_access": {
                    "accounts": ["123456789012", "987654321098"]
                }
            }
        """
        if not self.__config or not isinstance(self.__config, dict):
            return []

        # Check for direct "accounts_with_access" field first
        accounts_with_access = self.__config.get("accounts_with_access")
        if accounts_with_access and isinstance(accounts_with_access, list):
            return self._extract_account_ids(accounts_with_access)

        # Fall back to cross_account_access.accounts_with_access or cross_account_access.accounts
        access_config = self.cross_account_access
        if access_config and isinstance(access_config, dict):
            # Try accounts_with_access first (new pattern)
            accounts = access_config.get("accounts_with_access", [])
            if not accounts:
                # Fall back to accounts (legacy pattern)
                accounts = access_config.get("accounts", [])

            if accounts and isinstance(accounts, list):
                return self._extract_account_ids(accounts)

        return []

    def _extract_account_ids(self, accounts: list) -> list[str]:
        """
        Extract account IDs from a list that may contain either strings or objects.

        Args:
            accounts: List of either strings (account IDs) or objects with "id" field

        Returns:
            List of account ID strings
        """
        account_ids = []
        for account in accounts:
            if isinstance(account, str):
                # Simple string account ID
                account_ids.append(account)
            elif isinstance(account, dict) and "id" in account:
                # Object with "id" field (region is ignored)
                account_ids.append(account["id"])

        return account_ids

    # SSM properties are now inherited from EnhancedBaseConfig
    # Keeping these for any direct access patterns in existing code
    @property
    def ssm_parameters(self) -> dict:
        """Get legacy SSM parameter paths (for backward compatibility)"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("ssm_parameters", {})
        return {}

    def format_ssm_path(
        self,
        path: str,
        resource_type: str,
        resource_name: str,
        attribute: str,
        context: dict = None,
    ) -> str:
        """Format an SSM parameter path using the configured template

        Args:
            path: The path or attribute name to format
            resource_type: The type of resource (e.g., 'ecr')
            resource_name: The name of the resource
            attribute: The attribute name (e.g., 'name', 'uri', 'arn')
            context: Additional context variables for template formatting

        Returns:
            Formatted SSM parameter path
        """
        # If path starts with '/', it's already a full path
        if path.startswith("/"):
            return path

        # Get the template from config, or use deployment default
        template = self.__ssm_prefix_template

        # If no template is defined at the resource level, check if deployment has one
        if not template and self.__deployment:
            # This would need to be implemented in DeploymentConfig
            if hasattr(self.__deployment, "ssm_prefix_template"):
                template = self.__deployment.ssm_prefix_template

        # If still no template, use the default format
        if not template:
            # Try to get namespace from config
            ssm_ns = None
            if self.__config and isinstance(self.__config, dict):
                ssm_ns = self.__config.get("ssm", {}).get("namespace")
                if not ssm_ns:
                    ssm_ns = (
                        self.__config.get("ssm", {}).get("imports", {}).get("namespace")
                    )
            return self.__deployment.get_ssm_parameter_name(
                resource_type, resource_name, attribute, ssm_namespace=ssm_ns
            )

        # Format the template with available variables
        context = context or {}
        format_vars = {
            "deployment_name": self.__deployment.name if self.__deployment else "",
            "environment": self.__deployment.environment if self.__deployment else "",
            "workload_name": (
                self.__deployment.workload_name if self.__deployment else ""
            ),
            "resource_type": resource_type,
            "resource_name": resource_name,
            "attribute": path,  # Use the path as the attribute if it's a simple name
        }

        # Add any additional context variables
        format_vars.update(context)

        # Format the template
        formatted_path = template.format(**format_vars)

        # Ensure the path starts with '/'
        if not formatted_path.startswith("/"):
            formatted_path = f"/{formatted_path}"

        return formatted_path
