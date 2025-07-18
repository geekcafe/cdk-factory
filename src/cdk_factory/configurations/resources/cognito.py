"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""


class CognitoConfig:
    """
    Cognito Configuration - supports all major UserPool settings.
    Each property reads from the config dict and provides a sensible default if not set.
    """

    def __init__(self, config: dict) -> None:
        self.__config = config or {}

    @property
    def user_pool_name(self) -> str | None:
        """Name for the Cognito User Pool"""
        return self.__config.get("user_pool_name")

    @property
    def user_pool_id(self) -> str | None:
        """Gets the cognito user pool id (for import/reference)"""
        return self.__config.get("user_pool_id")

    @property
    def self_sign_up_enabled(self) -> bool:
        """Whether self sign-up is enabled (default: False)"""
        return bool(self.__config.get("self_sign_up_enabled", False))

    @property
    def sign_in_case_sensitive(self) -> bool:
        """Whether sign-in is case-sensitive (default: False)"""
        return bool(self.__config.get("sign_in_case_sensitive", False))

    @property
    def sign_in_aliases(self) -> dict | None:
        """Sign-in aliases config (username, email, phone, preferred_username)"""
        return self.__config.get("sign_in_aliases")

    @property
    def sign_in_policy(self) -> dict | None:
        """Sign-in policy config (if present)"""
        return self.__config.get("sign_in_policy")

    @property
    def auto_verify(self) -> dict | None:
        """Auto-verify attributes (email, phone)"""
        return self.__config.get("auto_verify")

    @property
    def custom_attributes(self) -> dict | None:
        """Custom attributes for the user pool"""
        return self.__config.get("custom_attributes")

    @property
    def custom_sender_kms_key(self):
        """Custom sender KMS key (if present)"""
        return self.__config.get("custom_sender_kms_key")

    @property
    def custom_threat_protection_mode(self):
        """Custom threat protection mode (if present)"""
        return self.__config.get("custom_threat_protection_mode")

    @property
    def standard_attributes(self) -> dict | None:
        """Standard attributes config"""
        return self.__config.get("standard_attributes")

    @property
    def password_policy(self) -> dict | None:
        """Password policy config (min_length, require_uppercase, etc.)"""
        return self.__config.get("password_policy")

    @property
    def mfa(self) -> str:
        """MFA setting (OFF, ON, OPTIONAL)"""
        return self.__config.get("mfa", "OFF")

    @property
    def mfa_second_factor(self) -> dict | None:
        """MFA second factor config (sms, otp)"""
        return self.__config.get("mfa_second_factor")

    @property
    def passkey_relying_party_id(self) -> str | None:
        """Passkey relying party ID"""
        return self.__config.get("passkey_relying_party_id")

    @property
    def passkey_user_verification(self) -> dict | None:
        """Passkey user verification config"""
        return self.__config.get("passkey_user_verification")

    @property
    def password_policy(self) -> dict | None:
        """Password policy config (min_length, require_uppercase, etc.)"""
        return self.__config.get("password_policy")

    @property
    def removal_policy(self) -> str:
        """Removal policy (DESTROY, RETAIN, SNAPSHOT)"""
        return self.__config.get("removal_policy", "RETAIN")

    @property
    def account_recovery(self) -> str:
        """Account recovery setting (EMAIL_ONLY, PHONE_ONLY_WITHOUT_MFA, etc.)"""
        return self.__config.get("account_recovery", "EMAIL_ONLY")

    @property
    def sms_role(self) -> str | None:
        """ARN of the IAM role for SMS configuration"""
        return self.__config.get("sms_role")

    @property
    def enable_sms_role(self) -> bool | None:
        """Whether to enable the SMS role (if present)"""
        return self.__config.get("enable_sms_role")

    @property
    def feature_plan(self) -> str | None:
        """Feature plan for the user pool (if present)"""
        return self.__config.get("feature_plan")

    @property
    def keep_original(self) -> bool | None:
        """Keep original attributes for the user pool (if present)"""
        return self.__config.get("keep_original")

    @property
    def lambda_triggers(self) -> dict | None:
        """Lambda triggers for the user pool (if present)"""
        return self.__config.get("lambda_triggers")

    @property
    def mfa_message(self) -> dict | None:
        """MFA message for the user pool (if present)"""
        return self.__config.get("mfa_message")

    @property
    def email(self) -> dict | None:
        """Email configuration for the user pool (if present)"""
        return self.__config.get("email")

    @property
    def device_tracking(self) -> dict | None:
        """Device tracking config (if present)"""
        return self.__config.get("device_tracking")

    @property
    def sms_role_external_id(self) -> str | None:
        """External ID for the SMS role"""
        return self.__config.get("sms_role_external_id")

    @property
    def sns_region(self) -> str | None:
        """SNS region"""
        return self.__config.get("sns_region")

    @property
    def standard_attributes(self) -> dict | None:
        """Standard attributes config"""
        return self.__config.get("standard_attributes")

    @property
    def standard_threat_protection_mode(self) -> str | None:
        """Standard threat protection mode"""
        return self.__config.get("standard_threat_protection_mode")

    @property
    def user_invitation(self) -> dict | None:
        """User invitation config (email_subject, sms_message, etc.)"""
        return self.__config.get("user_invitation")

    @property
    def user_verification(self) -> dict | None:
        """User verification config (email_subject, sms_message, etc.)"""
        return self.__config.get("user_verification")

    @property
    def advanced_security_mode(self) -> str | None:
        """Advanced security mode (OFF, AUDIT, ENFORCED)"""
        return self.__config.get("advanced_security_mode")

    # Deprecated/legacy or rarely used
    @property
    def removal_policy(self) -> str:
        """Removal policy (DESTROY, RETAIN, SNAPSHOT)"""
        return self.__config.get("removal_policy", "RETAIN")

    @property
    def user_verification(self) -> dict | None:
        """User verification config (email_subject, sms_message, etc.)"""
        return self.__config.get("user_verification")

    @property
    def user_invitation(self) -> dict | None:
        """User invitation config (email_subject, sms_message, etc.)"""
        return self.__config.get("user_invitation")

    @property
    def deletion_protection(self) -> bool:
        """Whether deletion protection is enabled (default: False)"""
        return bool(self.__config.get("deletion_protection", False))

    # Add more properties as needed for all UserPool options
