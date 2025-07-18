"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import aws_cdk as cdk
from aws_cdk import aws_cognito as cognito
from constructs import Construct
from aws_lambda_powertools import Logger

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.cognito import CognitoConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(__name__)


@register_stack("cognito_library_module")
@register_stack("cognito_stack")
class CognitoStack(IStack):
    """
    A CloudFormation Stack for AWS Cognito User Pool
    """

    def __init__(
        self,
        scope: Construct,
        id: str,  # pylint: disable=w0622
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)
        self.scope = scope
        self.id = id
        self.stack_config: StackConfig | None = None
        self.deployment: DeploymentConfig | None = None
        self.cognito_config: CognitoConfig | None = None

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Build the stack"""
        self.stack_config = stack_config
        self.deployment = deployment
        self.cognito_config = CognitoConfig(stack_config.dictionary.get("cognito", {}))

        # Build kwargs for all supported Cognito UserPool parameters
        kwargs = {
            "user_pool_name": self.cognito_config.user_pool_name,
            "self_sign_up_enabled": self.cognito_config.self_sign_up_enabled,
            "sign_in_case_sensitive": self.cognito_config.sign_in_case_sensitive,
            "sign_in_aliases": (
                cognito.SignInAliases(**self.cognito_config.sign_in_aliases)
                if self.cognito_config.sign_in_aliases
                else None
            ),
            "sign_in_policy": self.cognito_config.sign_in_policy,
            "auto_verify": (
                cognito.AutoVerifiedAttrs(**self.cognito_config.auto_verify)
                if self.cognito_config.auto_verify
                else None
            ),
            "custom_attributes": self.cognito_config.custom_attributes,
            "custom_sender_kms_key": self.cognito_config.custom_sender_kms_key,
            "custom_threat_protection_mode": self.cognito_config.custom_threat_protection_mode,
            "deletion_protection": self.cognito_config.deletion_protection,
            "device_tracking": self.cognito_config.device_tracking,
            "email": self.cognito_config.email,
            "enable_sms_role": self.cognito_config.enable_sms_role,
            "feature_plan": self.cognito_config.feature_plan,
            "keep_original": self.cognito_config.keep_original,
            "lambda_triggers": self.cognito_config.lambda_triggers,
            "mfa": (
                cognito.Mfa[self.cognito_config.mfa]
                if self.cognito_config.mfa
                else None
            ),
            "mfa_message": self.cognito_config.mfa_message,
            "mfa_second_factor": (
                cognito.MfaSecondFactor(**self.cognito_config.mfa_second_factor)
                if self.cognito_config.mfa_second_factor
                else None
            ),
            "passkey_relying_party_id": self.cognito_config.passkey_relying_party_id,
            "passkey_user_verification": self.cognito_config.passkey_user_verification,
            "password_policy": (
                cognito.PasswordPolicy(**self.cognito_config.password_policy)
                if self.cognito_config.password_policy
                else None
            ),
            "removal_policy": (
                cdk.RemovalPolicy[self.cognito_config.removal_policy]
                if self.cognito_config.removal_policy
                else None
            ),
            "account_recovery": (
                cognito.AccountRecovery[self.cognito_config.account_recovery]
                if self.cognito_config.account_recovery
                else None
            ),
            "sms_role": self.cognito_config.sms_role,
            "sms_role_external_id": self.cognito_config.sms_role_external_id,
            "sns_region": self.cognito_config.sns_region,
            "standard_attributes": self.cognito_config.standard_attributes,
            "standard_threat_protection_mode": self.cognito_config.standard_threat_protection_mode,
            "user_invitation": self.cognito_config.user_invitation,
            "user_verification": self.cognito_config.user_verification,
            "advanced_security_mode": (
                cognito.AdvancedSecurityMode[self.cognito_config.advanced_security_mode]
                if self.cognito_config.advanced_security_mode
                else None
            ),
        }
        # Remove None values
        kwargs = {k: v for k, v in kwargs.items() if v is not None}

        user_pool = cognito.UserPool(
            self,
            id=deployment.build_resource_name(
                self.cognito_config.user_pool_name
                or self.cognito_config.user_pool_id
                or "user-pool"
            ),
            **kwargs,
        )
        logger.info(f"Created Cognito User Pool: {user_pool.user_pool_id}")
