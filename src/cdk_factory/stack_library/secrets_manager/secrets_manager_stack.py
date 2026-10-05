"""
Secrets Manager Stack Pattern for CDK-Factory
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.

Generic Secrets Manager stack. Creates one or more Secrets Manager secrets, each
seeded with a recognizable PLACEHOLDER value at create time. Real values are
seeded out-of-band after deploy (e.g. via the console or `aws secretsmanager
put-secret-value`), never committed to the template.

NO-CLOBBER CONTRACT (read this before changing any placeholder):
    CloudFormation only re-asserts a secret's value when the ``SecretString``
    PROPERTY CHANGES between deploys. Because the placeholder is a CONSTANT in
    config, redeploys do NOT overwrite a value that was changed out-of-band —
    the property is identical, so CloudFormation leaves the live value alone.

    THEREFORE: the placeholder is set exactly ONCE, at create. NEVER edit the
    placeholder string in config afterward. If you do, the property changes and
    CloudFormation will OVERWRITE the real (out-of-band seeded) value with the
    new placeholder on the next deploy, destroying the live credential.

RETAIN SEMANTICS:
    Secrets default to ``RemovalPolicy.RETAIN`` so the secret SURVIVES stack
    deletion (by design — credentials must not be lost if the stack is torn down
    or a resource is replaced). ``DESTROY`` may be set explicitly per secret when
    the secret is genuinely disposable.

SYNTH SAFETY:
    No live AWS calls at synth. No boto3. Secret names/descriptions may contain
    ``{{WORKLOAD_NAME}}`` / ``{{ENVIRONMENT}}`` template tokens, resolved from the
    deployment context (not a live lookup). Construct IDs are DETERMINISTIC
    (stable explicit strings), so logical IDs never churn between synths.

SSM EXPORT:
    This stack intentionally does NOT publish secret ARNs to SSM. The consuming
    Lambda IAM references the secrets by name-pattern ARN, so an SSM export adds
    no value here. Kept minimal on purpose.
"""

from typing import Dict

import aws_cdk as cdk
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.secrets_manager import SecretsManager
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="SecretsManagerStack")


@register_stack("secrets_manager_library_module")
@register_stack("secrets_manager_stack")
class SecretsManagerStack(IStack):
    """
    Reusable stack for AWS Secrets Manager.

    Creates each configured secret with a placeholder value and a RETAIN removal
    policy by default. See the module docstring for the no-clobber contract and
    RETAIN semantics.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.secrets_config: SecretsManager | None = None
        self.stack_config: StackConfig | None = None
        self.deployment: DeploymentConfig | None = None
        self.workload: WorkloadConfig | None = None
        self.secrets: Dict[str, secretsmanager.Secret] = {}

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Build the Secrets Manager stack."""
        self._build(stack_config, deployment, workload)

    def _build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Internal build method for the Secrets Manager stack."""
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload

        self.secrets_config = SecretsManager(stack_config.dictionary)

        for secret_config in self.secrets_config.secrets:
            self._create_secret(secret_config)

    def _substitute_variables(self, value: str | None) -> str | None:
        """Resolve ``{{WORKLOAD_NAME}}`` / ``{{ENVIRONMENT}}`` template tokens.

        Values are resolved from the deployment context (no live AWS call).
        Returns the value unchanged when it is ``None`` or contains no token.
        """
        if value is None:
            return None
        replacements = {
            "{{WORKLOAD_NAME}}": self.deployment.workload_name,
            "{{ENVIRONMENT}}": self.deployment.environment,
        }
        result = value
        for placeholder, replacement in replacements.items():
            result = result.replace(placeholder, replacement)
        return result

    def _create_secret(self, secret_config) -> secretsmanager.Secret:
        """Create a single Secrets Manager secret seeded with its placeholder.

        The secret value is set once at create to the configured placeholder.
        See the module docstring: NEVER change the placeholder in config after the
        first deploy or CloudFormation will overwrite the real value.
        """
        secret_name = self._substitute_variables(secret_config.name)
        description = self._substitute_variables(secret_config.description)
        placeholder = secret_config.placeholder

        removal_policy = (
            cdk.RemovalPolicy.DESTROY
            if secret_config.removal_policy == "DESTROY"
            else cdk.RemovalPolicy.RETAIN
        )

        # Deterministic construct ID derived from the resolved secret name.
        # Stable across synths/processes/machines so the logical ID never churns.
        construct_id = f"secret-{self._sanitize_id(secret_name)}"

        secret = secretsmanager.Secret(
            self,
            construct_id,
            secret_name=secret_name,
            description=description,
            secret_string_value=cdk.SecretValue.unsafe_plain_text(placeholder),
            removal_policy=removal_policy,
        )

        logger.warning(
            f"Created Secrets Manager secret '{secret_name}' with a PLACEHOLDER "
            f"value ('{placeholder}'). Seed the real value out-of-band (e.g. "
            f"`aws secretsmanager put-secret-value`). Do NOT change the placeholder "
            f"in config afterward or the next deploy will overwrite the real value."
        )

        self.secrets[secret_name] = secret
        return secret

    @staticmethod
    def _sanitize_id(secret_name: str) -> str:
        """Turn a secret name/path into a stable, construct-ID-safe token.

        Deterministic (pure string transform — no hashing, no randomness):
        non-alphanumeric characters are replaced with ``-`` so the same secret
        name always yields the same construct (and therefore logical) ID.
        """
        return "".join(
            ch if ch.isalnum() else "-" for ch in secret_name
        ).strip("-")
