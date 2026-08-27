"""
Cognito Lambda Trigger Attachment Utility

Attaches Lambda triggers (PreTokenGeneration, PostAuthentication, PreSignUp, etc.)
to a Cognito User Pool as a post-deploy step. This is necessary because CDK cannot
manage Lambda triggers on an IMPORTED user pool — the pool is referenced by ID, so
CDK has no control over its pool-level settings.

This utility runs after the trigger Lambda functions are deployed (their ARNs are
published to SSM by the lambda stack's auto_export), discovers the ARNs from SSM,
and:
    1. Grants each Lambda a resource-based policy allowing cognito-idp to invoke it
    2. Merges the trigger configuration into the pool's LambdaConfig (describe-then-merge
       so existing triggers are preserved)

Usage as a CLI (called from pipeline post_steps):

    export COGNITO_USER_POOL_ID="us-east-1_XXXXXXXXX"
    export SSM_LAMBDA_NAMESPACE="my-app/dev/lambda"
    export COGNITO_TRIGGERS="PreTokenGeneration=cognito-pre-token-trigger,PostAuthentication=cognito-post-auth-trigger"
    export AWS_ACCOUNT_NUMBER="123456789012"
    export AWS_REGION="us-east-1"
    export CROSS_ACCOUNT_ROLE_ARN="arn:aws:iam::123456789012:role/DevOpsCrossAccountAccessRole"
    python -m cdk_factory.utilities.cognito_trigger_attachment

Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

import os
import sys
import logging
from typing import Dict, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Valid Cognito Lambda trigger keys (as used in UserPool.LambdaConfig)
VALID_TRIGGER_KEYS = {
    "PreSignUp",
    "PostConfirmation",
    "PreAuthentication",
    "PostAuthentication",
    "DefineAuthChallenge",
    "CreateAuthChallenge",
    "VerifyAuthChallengeResponse",
    "PreTokenGeneration",
    "UserMigration",
    "CustomMessage",
    "CustomEmailSender",
    "CustomSMSSender",
}


class CognitoTriggerAttachment:
    """Attaches Lambda triggers to a Cognito User Pool via boto3 (post-deploy)."""

    def _get_client(self, service: str, role_arn: Optional[str] = None):
        """Get a boto3 client, optionally assuming a cross-account role."""
        if role_arn:
            sts = boto3.client("sts")
            creds = sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName=f"cognito-trigger-attach-{service}",
            )["Credentials"]
            return boto3.client(
                service,
                aws_access_key_id=creds["AccessKeyId"],
                aws_secret_access_key=creds["SecretAccessKey"],
                aws_session_token=creds["SessionToken"],
            )
        return boto3.client(service)

    def get_ssm_parameter(
        self, parameter_name: str, role_arn: Optional[str] = None
    ) -> Optional[str]:
        """Read an SSM parameter. Returns None if not found (idempotent)."""
        client = self._get_client("ssm", role_arn)
        try:
            return client.get_parameter(Name=parameter_name)["Parameter"]["Value"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "ParameterNotFound":
                logger.warning(f"SSM parameter not found: {parameter_name}")
                return None
            raise

    def resolve_trigger_arn(
        self,
        ssm_namespace: str,
        lambda_short_name: str,
        role_arn: Optional[str] = None,
    ) -> Optional[str]:
        """Resolve a trigger Lambda's ARN from SSM.

        The lambda stack's auto_export publishes ARNs at:
            /{ssm_namespace}/{lambda_short_name}/arn
        """
        from cdk_factory.utilities.ssm_path_utils import normalize_ssm_path

        ssm_path = normalize_ssm_path(f"/{ssm_namespace}/{lambda_short_name}/arn")
        arn = self.get_ssm_parameter(ssm_path, role_arn=role_arn)
        if arn:
            logger.info(f"Resolved {lambda_short_name} ARN: {arn}")
        else:
            logger.warning(
                f"Could not resolve ARN for '{lambda_short_name}' at {ssm_path}"
            )
        return arn

    def grant_cognito_invoke_permission(
        self,
        function_arn: str,
        user_pool_arn: str,
        statement_id: str,
        role_arn: Optional[str] = None,
    ) -> None:
        """Grant cognito-idp permission to invoke the Lambda.

        Idempotent — if the statement already exists, it's left in place.
        """
        client = self._get_client("lambda", role_arn)
        try:
            client.add_permission(
                FunctionName=function_arn,
                StatementId=statement_id,
                Action="lambda:InvokeFunction",
                Principal="cognito-idp.amazonaws.com",
                SourceArn=user_pool_arn,
            )
            logger.info(
                f"Granted cognito-idp invoke permission on {function_arn} "
                f"(statement: {statement_id})"
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceConflictException":
                # Permission already exists — idempotent no-op
                logger.info(
                    f"Invoke permission '{statement_id}' already exists on {function_arn}"
                )
            else:
                raise

    def build_user_pool_arn(
        self, user_pool_id: str, account: str, region: str
    ) -> str:
        """Construct the user pool ARN from its ID."""
        return f"arn:aws:cognito-idp:{region}:{account}:userpool/{user_pool_id}"

    def attach_triggers(
        self,
        user_pool_id: str,
        triggers: Dict[str, str],
        account: str,
        region: str,
        role_arn: Optional[str] = None,
    ) -> None:
        """Attach Lambda triggers to the user pool.

        Describe-then-merge: preserves any existing LambdaConfig entries and only
        adds/overrides the specified triggers.

        Args:
            user_pool_id: The Cognito User Pool ID.
            triggers: Map of trigger key (e.g. "PostAuthentication") to Lambda ARN.
            account: AWS account ID (for building the pool ARN for permissions).
            region: AWS region.
            role_arn: Optional cross-account role to assume.
        """
        if not triggers:
            logger.info("No triggers to attach — nothing to do")
            return

        client = self._get_client("cognito-idp", role_arn)
        user_pool_arn = self.build_user_pool_arn(user_pool_id, account, region)

        # Grant invoke permissions for each trigger Lambda first
        for trigger_key, function_arn in triggers.items():
            statement_id = f"Cognito{trigger_key}"
            self.grant_cognito_invoke_permission(
                function_arn=function_arn,
                user_pool_arn=user_pool_arn,
                statement_id=statement_id,
                role_arn=role_arn,
            )

        # Describe the pool to get current settings (update_user_pool is destructive)
        pool = client.describe_user_pool(UserPoolId=user_pool_id)["UserPool"]
        existing_lambda_config = pool.get("LambdaConfig", {})

        # Merge: existing config + new triggers (new triggers override)
        merged_lambda_config = {**existing_lambda_config, **triggers}

        if merged_lambda_config == existing_lambda_config:
            logger.info("LambdaConfig already up to date — no update needed")
            return

        # update_user_pool requires re-supplying certain existing fields or they reset.
        # We pass through the fields that are safe/required to preserve.
        update_kwargs = {
            "UserPoolId": user_pool_id,
            "LambdaConfig": merged_lambda_config,
        }

        # Preserve fields that update_user_pool would otherwise reset to defaults
        self._preserve_pool_settings(pool, update_kwargs)

        client.update_user_pool(**update_kwargs)
        logger.info(
            f"Attached triggers to pool {user_pool_id}: {list(triggers.keys())}"
        )

    def _preserve_pool_settings(self, pool: dict, update_kwargs: dict) -> None:
        """Copy existing pool settings into update_kwargs to avoid resetting them.

        update_user_pool replaces the entire configuration, so any field not
        explicitly passed reverts to its default. This preserves the settings
        that are commonly configured and would be destructive to lose.
        """
        # Simple passthrough fields
        passthrough = [
            "Policies",
            "AutoVerifiedAttributes",
            "SmsVerificationMessage",
            "EmailVerificationMessage",
            "EmailVerificationSubject",
            "VerificationMessageTemplate",
            "SmsAuthenticationMessage",
            "MfaConfiguration",
            "UserAttributeUpdateSettings",
            "DeviceConfiguration",
            "EmailConfiguration",
            "SmsConfiguration",
            "UserPoolTags",
            "AdminCreateUserConfig",
            "UserPoolAddOns",
            "AccountRecoverySetting",
        ]
        for field in passthrough:
            if field in pool and pool[field] is not None:
                update_kwargs[field] = pool[field]

        # DeletionProtection is an enum string
        if pool.get("DeletionProtection"):
            update_kwargs["DeletionProtection"] = pool["DeletionProtection"]


def _parse_triggers_spec(
    spec: str, ssm_namespace: str, attacher: CognitoTriggerAttachment, role_arn: Optional[str]
) -> Dict[str, str]:
    """Parse the COGNITO_TRIGGERS spec and resolve each Lambda ARN from SSM.

    Spec format: "TriggerKey=lambda-short-name,TriggerKey2=lambda-short-name-2"
    e.g. "PreTokenGeneration=cognito-pre-token-trigger,PostAuthentication=cognito-post-auth-trigger"

    Returns a dict of {trigger_key: resolved_arn} for triggers that resolved successfully.
    """
    triggers: Dict[str, str] = {}
    for pair in spec.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        trigger_key, lambda_name = pair.split("=", 1)
        trigger_key = trigger_key.strip()
        lambda_name = lambda_name.strip()

        if trigger_key not in VALID_TRIGGER_KEYS:
            logger.warning(
                f"Skipping unknown trigger key '{trigger_key}'. "
                f"Valid keys: {sorted(VALID_TRIGGER_KEYS)}"
            )
            continue

        arn = attacher.resolve_trigger_arn(ssm_namespace, lambda_name, role_arn=role_arn)
        if arn:
            triggers[trigger_key] = arn
        else:
            logger.warning(
                f"Trigger '{trigger_key}' -> '{lambda_name}' not attached (ARN not found)"
            )

    return triggers


def main():
    """CLI entry point for pipeline steps."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    user_pool_id = os.getenv("COGNITO_USER_POOL_ID") or os.getenv(
        "COGNITO_PRIMARY_USER_POOL_ID"
    )
    ssm_namespace = os.getenv("SSM_LAMBDA_NAMESPACE")
    triggers_spec = os.getenv("COGNITO_TRIGGERS")
    account = os.getenv("AWS_ACCOUNT_NUMBER") or os.getenv("AWS_ACCOUNT")
    region = os.getenv("AWS_REGION", "us-east-1")
    role_arn = os.getenv("CROSS_ACCOUNT_ROLE_ARN")

    # Normalize "none"/"None"/empty to None
    def _norm(v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v or v.lower() == "none":
            return None
        return v

    user_pool_id = _norm(user_pool_id)
    ssm_namespace = _norm(ssm_namespace)
    triggers_spec = _norm(triggers_spec)
    account = _norm(account)
    role_arn = _norm(role_arn)

    # If no user pool is configured, this is a no-op (e.g., deployments without SSO)
    if not user_pool_id:
        logger.info(
            "COGNITO_USER_POOL_ID not set — skipping trigger attachment (no-op)"
        )
        sys.exit(0)

    if not triggers_spec:
        logger.info("COGNITO_TRIGGERS not set — skipping trigger attachment (no-op)")
        sys.exit(0)

    if not ssm_namespace:
        print("ERROR: SSM_LAMBDA_NAMESPACE is required", file=sys.stderr)
        sys.exit(1)

    if not account:
        print("ERROR: AWS_ACCOUNT_NUMBER (or AWS_ACCOUNT) is required", file=sys.stderr)
        sys.exit(1)

    attacher = CognitoTriggerAttachment()

    triggers = _parse_triggers_spec(triggers_spec, ssm_namespace, attacher, role_arn)

    if not triggers:
        logger.warning(
            "No triggers resolved — nothing attached. Check SSM_LAMBDA_NAMESPACE "
            "and that the trigger Lambdas were deployed."
        )
        sys.exit(0)

    attacher.attach_triggers(
        user_pool_id=user_pool_id,
        triggers=triggers,
        account=account,
        region=region,
        role_arn=role_arn,
    )

    logger.info("Cognito trigger attachment complete")


if __name__ == "__main__":
    main()
