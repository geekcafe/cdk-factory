"""
SSM Parameter Resolver CLI Utility

Resolves AWS SSM Parameter Store values and prints them to stdout.
Supports optional cross-account role assumption via STS and optional
region override, following the same cross-account client pattern as
route53_delegation.py.

Usage as a CLI (called from pipeline steps):

    python -m cdk_factory.utilities.ssm_resolver \
        --parameter-name "/aplos-nca-saas/beta/route53/hosted-zone-id" \
        --role-arn "arn:aws:iam::111111111111:role/CrossAccountRole" \
        --region "us-east-1"

Usage for shell variable capture:

    export VAR=$(python -m cdk_factory.utilities.ssm_resolver \
        --parameter-name "/path" --role-arn "arn:...")

Usage as a library:

    from cdk_factory.utilities.ssm_resolver import SsmResolver
    resolver = SsmResolver()
    value = resolver.resolve("/my/param", role_arn="arn:aws:iam::111...:role/Role")
"""

import sys
import logging
import argparse
from typing import Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class SsmResolver:
    """Resolves AWS SSM Parameter Store values, optionally via cross-account role assumption."""

    def _get_client(
        self, service: str, role_arn: Optional[str] = None, region: Optional[str] = None
    ):
        """
        Get a boto3 client, optionally assuming a cross-account role.

        Follows the same STS assume-role pattern as Route53Delegation._get_client.
        """
        kwargs = {}
        if region:
            kwargs["region_name"] = region

        if role_arn:
            sts = boto3.client("sts")
            creds = sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName=f"ssm-resolver-{service}",
            )["Credentials"]
            return boto3.client(
                service,
                aws_access_key_id=creds["AccessKeyId"],
                aws_secret_access_key=creds["SecretAccessKey"],
                aws_session_token=creds["SessionToken"],
                **kwargs,
            )
        return boto3.client(service, **kwargs)

    def resolve(
        self,
        parameter_name: str,
        role_arn: Optional[str] = None,
        region: Optional[str] = None,
    ) -> str:
        """
        Resolve an SSM parameter value by name.

        Args:
            parameter_name: The SSM parameter path (e.g., "/aplos-nca-saas/beta/route53/hosted-zone-id")
            role_arn: Optional IAM role ARN for cross-account access
            region: Optional AWS region override

        Returns:
            The parameter value as a string.

        Raises:
            SystemExit: On ParameterNotFound, STS failure, or unexpected errors.
        """
        try:
            client = self._get_client("ssm", role_arn=role_arn, region=region)
        except ClientError as e:
            print(
                f"ERROR: Failed to assume role {role_arn} for parameter {parameter_name}: {e}",
                file=sys.stderr,
            )
            sys.exit(1)

        try:
            response = client.get_parameter(Name=parameter_name, WithDecryption=True)
            return response["Parameter"]["Value"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "ParameterNotFound":
                print(
                    f"ERROR: SSM parameter not found: {parameter_name}",
                    file=sys.stderr,
                )
                sys.exit(1)
            print(
                f"ERROR: Failed to resolve parameter {parameter_name}: {e}",
                file=sys.stderr,
            )
            sys.exit(1)
        except Exception as e:
            print(
                f"ERROR: Unexpected error resolving {parameter_name}: {e}",
                file=sys.stderr,
            )
            sys.exit(1)


def main() -> None:
    """CLI entry point. Parses args, resolves parameter, prints to stdout."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    parser = argparse.ArgumentParser(
        description="Resolve an AWS SSM Parameter Store value"
    )
    parser.add_argument(
        "--parameter-name",
        required=True,
        help="SSM parameter path to resolve",
    )
    parser.add_argument(
        "--role-arn",
        default=None,
        help="IAM role ARN for cross-account STS assumption",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="AWS region for the SSM API call",
    )

    args = parser.parse_args()

    resolver = SsmResolver()
    value = resolver.resolve(
        parameter_name=args.parameter_name,
        role_arn=args.role_arn,
        region=args.region,
    )
    print(value)


if __name__ == "__main__":
    main()
