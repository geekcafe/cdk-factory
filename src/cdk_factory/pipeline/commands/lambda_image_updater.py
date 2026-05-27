#!/usr/bin/env python3
"""
Lambda Image Updater — Centralized Docker Lambda Update Tool

Updates Lambda functions with new Docker images after ECR push.
Reads deployment configuration from docker-images.json in each project.

Usage:
    # Update all Lambdas defined in a docker-images.json
    python -m cdk_factory.pipeline.commands.lambda_image_updater \
        --config /path/to/docker-images.json

    # Update specific image only
    python -m cdk_factory.pipeline.commands.lambda_image_updater \
        --config /path/to/docker-images.json \
        --image-name my-app-processor

    # Dry run (show what would be updated)
    python -m cdk_factory.pipeline.commands.lambda_image_updater \
        --config /path/to/docker-images.json \
        --dry-run

Ported from aplos_saas_devops_cdk.commands.lambda_image_updater with import paths
updated to cdk_factory.pipeline.*.
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

from cdk_factory.version import __version__


class LambdaImageUpdater:
    """Updates Lambda functions with new Docker images."""

    def __init__(
        self,
        config_path: str,
        dry_run: bool = False,
        image_name: Optional[str] = None,
        cross_account_role: Optional[str] = None,
    ):
        """
        Initialize the Lambda image updater.

        Args:
            config_path: Path to docker-images.json configuration file
            dry_run: If True, only show what would be updated without making changes
            image_name: Optional specific image name to update (updates all if None)
            cross_account_role: Optional IAM role name for cross-account access
        """
        self.config_path = config_path
        self.dry_run = dry_run
        self.image_name = image_name

        # Detect caller account via STS
        self._sts_client = boto3.client("sts")
        self._caller_account = self._sts_client.get_caller_identity()["Account"]

        # Session cache for assumed-role sessions (keyed by account ID)
        self._session_cache: Dict[str, boto3.Session] = {}

        # Cross-account role name: constructor arg → env var → default
        self._cross_account_role = (
            cross_account_role
            or os.environ.get("CROSS_ACCOUNT_ROLE_NAME")
            or "DevOpsCrossAccountAccessRole"
        )

        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load and validate docker-images.json configuration."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, "r") as f:
            config = json.load(f)

        if "images" not in config:
            raise ValueError(f"Config file missing 'images' array: {self.config_path}")

        return config

    def _get_cross_account_session(
        self,
        account: str,
        region: str,
        role_name: Optional[str] = None,
    ) -> Optional[boto3.Session]:
        """
        Get a boto3 Session with assumed-role credentials for cross-account access.

        Args:
            account: Target AWS account ID
            region: AWS region
            role_name: Optional per-deployment role name override

        Returns:
            boto3.Session with temporary credentials, or None for same-account
        """
        if account == self._caller_account:
            return None

        if account in self._session_cache:
            return self._session_cache[account]

        effective_role = role_name or self._cross_account_role
        role_arn = f"arn:aws:iam::{account}:role/{effective_role}"

        response = self._sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName="lambda-image-updater",
        )
        creds = response["Credentials"]

        session = boto3.Session(
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )
        self._session_cache[account] = session
        return session

    def _get_ssm_client(
        self, account: str, region: str, role_name: Optional[str] = None
    ) -> Any:
        """
        Get boto3 SSM client for the specified account/region.

        Args:
            account: AWS account ID
            region: AWS region
            role_name: Optional per-deployment role name override

        Returns:
            boto3 SSM client
        """
        session = self._get_cross_account_session(account, region, role_name=role_name)
        if session is not None:
            return session.client("ssm", region_name=region)
        return boto3.client("ssm", region_name=region)

    def _get_lambda_client(
        self, account: str, region: str, role_name: Optional[str] = None
    ) -> Any:
        """
        Get boto3 Lambda client for the specified account/region.

        Args:
            account: AWS account ID
            region: AWS region
            role_name: Optional per-deployment role name override

        Returns:
            boto3 Lambda client
        """
        session = self._get_cross_account_session(account, region, role_name=role_name)
        if session is not None:
            return session.client("lambda", region_name=region)
        return boto3.client("lambda", region_name=region)

    def _resolve_ssm_parameter(
        self,
        ssm_client: Any,
        parameter_path: str,
    ) -> Optional[str]:
        """
        Resolve SSM parameter value.

        Args:
            ssm_client: boto3 SSM client
            parameter_path: SSM parameter path

        Returns:
            Parameter value or None if not found
        """
        try:
            response = ssm_client.get_parameter(Name=parameter_path)
            return response["Parameter"]["Value"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "ParameterNotFound":
                print(f"  ⚠️  SSM parameter not found: {parameter_path}")
                return None
            raise

    def _get_current_image_uri(
        self,
        lambda_client: Any,
        function_arn: str,
    ) -> Optional[str]:
        """
        Get current image URI for a Lambda function.

        Args:
            lambda_client: boto3 Lambda client
            function_arn: Lambda function ARN

        Returns:
            Current image URI or None if error
        """
        try:
            response = lambda_client.get_function(FunctionName=function_arn)
            return response["Code"].get("ImageUri")
        except ClientError as e:
            print(f"  ❌ Failed to get function config: {e}")
            return None

    def _update_lambda_image(
        self,
        lambda_client: Any,
        function_arn: str,
        new_image_uri: str,
        max_retries: int = 3,
        base_delay: float = 2.0,
    ) -> bool:
        """
        Update Lambda function with new image URI, with retry/backoff
        for transient AccessDeniedException errors caused by ECR
        image propagation delays.

        Args:
            lambda_client: boto3 Lambda client
            function_arn: Lambda function ARN
            new_image_uri: New Docker image URI
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds (doubles each retry)

        Returns:
            True if successful, False otherwise
        """
        for attempt in range(max_retries + 1):
            try:
                response = lambda_client.update_function_code(
                    FunctionName=function_arn,
                    ImageUri=new_image_uri,
                )
                print(f"  ✅ Updated successfully")
                print(f"     Last modified: {response.get('LastModified')}")
                print(f"     Version: {response.get('Version')}")
                return True
            except ClientError as e:
                error_code = e.response["Error"]["Code"]
                is_ecr_access_error = (
                    error_code == "AccessDeniedException" and "ECR" in str(e)
                )

                if is_ecr_access_error and attempt < max_retries:
                    delay = base_delay * (2**attempt)
                    print(
                        f"  ⏳ ECR image not yet accessible, "
                        f"retrying in {delay:.0f}s "
                        f"(attempt {attempt + 1}/{max_retries})..."
                    )
                    time.sleep(delay)
                    continue

                print(f"  ❌ Update failed: {e}")
                return False
        return False

    def _get_ecr_client(
        self, account: str, region: str, role_name: Optional[str] = None
    ) -> Any:
        """
        Get boto3 ECR client for the specified account/region.

        Args:
            account: AWS account ID
            region: AWS region
            role_name: Optional per-deployment role name override

        Returns:
            boto3 ECR client
        """
        session = self._get_cross_account_session(account, region, role_name=role_name)
        if session is not None:
            return session.client("ecr", region_name=region)
        return boto3.client("ecr", region_name=region)

    def _resolve_image_digest(
        self,
        ecr_client: Any,
        repo_name: str,
        tag: str,
    ) -> Optional[str]:
        """
        Resolve an image tag to its SHA256 digest via ECR.

        Using the digest instead of a mutable tag avoids race conditions
        where Lambda tries to resolve a tag before the manifest has
        fully propagated after a push.

        Args:
            ecr_client: boto3 ECR client for the account that owns the repo
            repo_name: ECR repository name
            tag: Image tag to resolve

        Returns:
            Image digest string (e.g. "sha256:abc123...") or None on failure
        """
        try:
            response = ecr_client.batch_get_image(
                repositoryName=repo_name,
                imageIds=[{"imageTag": tag}],
                acceptedMediaTypes=[
                    "application/vnd.docker.distribution.manifest.v2+json"
                ],
            )
            images = response.get("images", [])
            if images:
                return images[0]["imageId"]["imageDigest"]
            print(f"  ⚠️  No image found for {repo_name}:{tag}")
            return None
        except ClientError as e:
            print(f"  ⚠️  Failed to resolve digest for {repo_name}:{tag}: {e}")
            return None

    def _discover_docker_lambdas(
        self,
        ssm_client: Any,
        ssm_prefix: str,
        repo_name: str,
    ) -> List[Dict[str, str]]:
        """
        Discover all Docker Lambda ARNs registered under an ECR repo path.

        Lambda stacks register Docker Lambdas at:
            /{ssm_prefix}/ecr/{safe-repo-name}/{lambda-name}/arn

        Args:
            ssm_client: boto3 SSM client
            ssm_prefix: Workload/deployment prefix (e.g. "my-app/dev")
            repo_name: ECR repository name (may contain slashes)

        Returns:
            List of dicts with 'arn', 'name', and 'param_path' keys.
        """
        safe_repo = repo_name.replace("/", "-")
        ecr_path = f"/{ssm_prefix}/ecr/{safe_repo}"

        discovered: List[Dict[str, str]] = []

        try:
            paginator = ssm_client.get_paginator("get_parameters_by_path")
            for page in paginator.paginate(Path=ecr_path, Recursive=True):
                for param in page.get("Parameters", []):
                    if param["Name"].endswith("/arn"):
                        # Extract lambda name from path:
                        # /{prefix}/ecr/{repo}/{lambda-name}/arn → lambda-name
                        parts = param["Name"].rsplit("/", 2)
                        lambda_name = parts[-2] if len(parts) >= 2 else "unknown"
                        discovered.append(
                            {
                                "arn": param["Value"],
                                "name": lambda_name,
                                "param_path": param["Name"],
                            }
                        )
        except ClientError as e:
            print(f"  ❌ Failed to discover Docker Lambdas at {ecr_path}: {e}")
            return []

        if not discovered:
            print(f"  ⚠️  No Docker Lambdas found at {ecr_path}")

        return discovered

    def _build_image_uri(
        self,
        account: str,
        region: str,
        repo_name: str,
        tag: str,
    ) -> str:
        """
        Build ECR image URI.

        Args:
            account: AWS account ID
            region: AWS region
            repo_name: ECR repository name
            tag: Image tag

        Returns:
            Full ECR image URI
        """
        return f"{account}.dkr.ecr.{region}.amazonaws.com/{repo_name}:{tag}"

    def update_image(self, image_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update Lambda functions for a single Docker image.

        Args:
            image_config: Image configuration from docker-images.json

        Returns:
            Update results dictionary
        """
        repo_name = image_config.get("repo_name")
        if not repo_name:
            return {"error": "Missing repo_name in image config"}

        deployments = image_config.get("lambda_deployments", [])
        if not deployments:
            print(f"  ℹ️  No lambda_deployments configured for {repo_name}")
            return {"skipped": True, "reason": "no_deployments"}

        results: Dict[str, Any] = {
            "repo_name": repo_name,
            "deployments": [],
        }

        for deployment in deployments:
            account = deployment.get("account")
            region = deployment.get("region", "us-east-1")
            ssm_parameter = deployment.get("ssm_parameter")
            ssm_prefix = deployment.get("ssm_prefix")
            tag = deployment.get("tag", "latest")
            enabled = deployment.get("enabled", True)

            # Skip disabled deployments with a warning
            if not enabled:
                label = ssm_prefix or ssm_parameter or "unknown"
                print(
                    f"\n  ⚠️  Skipping disabled deployment: {account}/{region} ({label})"
                )
                results["deployments"].append(
                    {
                        "account": account or "unknown",
                        "region": region,
                        "status": "skipped",
                    }
                )
                continue

            if not account or (not ssm_parameter and not ssm_prefix):
                results["deployments"].append(
                    {
                        "account": account or "unknown",
                        "region": region,
                        "ssm_parameter": ssm_parameter or "unknown",
                        "error": "Missing required fields (account, and either ssm_parameter or ssm_prefix)",
                    }
                )
                continue

            # Get clients
            role_name = deployment.get("role_name")
            ssm_client = self._get_ssm_client(account, region, role_name=role_name)
            lambda_client = self._get_lambda_client(
                account, region, role_name=role_name
            )
            ecr_account = deployment.get("ecr_account", self._caller_account)

            # --- ssm_prefix path: auto-discover and update all Lambdas ---
            if ssm_prefix:
                if ssm_parameter:
                    print(f"  ℹ️  ssm_prefix takes precedence over ssm_parameter")

                safe_repo = repo_name.replace("/", "-")
                print(f"\n  🔍 Auto-discovery: account={account}, region={region}")
                print(f"     SSM path: /{ssm_prefix}/ecr/{safe_repo}")
                print(f"     Tag: {tag}")

                discovered = self._discover_docker_lambdas(
                    ssm_client, ssm_prefix, repo_name
                )
                if not discovered:
                    results["deployments"].append(
                        {
                            "account": account,
                            "region": region,
                            "ssm_prefix": ssm_prefix,
                            "error": f"No Docker Lambdas discovered at /{ssm_prefix}/ecr/{repo_name.replace('/', '-')}",
                        }
                    )
                    continue

                for lamb in discovered:
                    function_arn = lamb["arn"]
                    lambda_name = lamb["name"]

                    print(f"\n  📍 Deployment: {account}/{region}")
                    print(f"     Lambda: {lambda_name}")
                    print(f"     Lambda ARN: {function_arn}")

                    # Get current image
                    current_image = self._get_current_image_uri(
                        lambda_client, function_arn
                    )
                    if current_image:
                        print(f"     Current image: {current_image}")

                    # Build new image URI
                    new_image_uri = self._build_image_uri(
                        ecr_account, region, repo_name, tag
                    )
                    print(f"     New image (tag): {new_image_uri}")

                    # Resolve digest
                    ecr_client = self._get_ecr_client(ecr_account, region)
                    digest = self._resolve_image_digest(ecr_client, repo_name, tag)
                    use_digest = False
                    if use_digest and digest:
                        new_image_uri = f"{ecr_account}.dkr.ecr.{region}.amazonaws.com/{repo_name}@{digest}"
                        print(f"     Resolved digest: {digest}")
                        print(f"     New image (digest): {new_image_uri}")
                    elif not use_digest:
                        print(f"     Using {tag}")
                    else:
                        print(
                            f"  ⚠️  Could not resolve digest, falling back to tag-based URI"
                        )

                    # Perform update
                    if self.dry_run:
                        print(f"  🔍 DRY RUN: Would update Lambda {lambda_name}")
                        results["deployments"].append(
                            {
                                "account": account,
                                "region": region,
                                "ssm_prefix": ssm_prefix,
                                "function_arn": function_arn,
                                "status": "dry_run",
                            }
                        )
                    else:
                        success = self._update_lambda_image(
                            lambda_client,
                            function_arn,
                            new_image_uri,
                        )
                        results["deployments"].append(
                            {
                                "account": account,
                                "region": region,
                                "ssm_prefix": ssm_prefix,
                                "function_arn": function_arn,
                                "status": "success" if success else "failed",
                            }
                        )

                continue  # skip legacy ssm_parameter path

            # --- Legacy ssm_parameter path (unchanged) ---
            print(f"\n  📍 Deployment: {account}/{region}")
            print(f"     SSM: {ssm_parameter}")
            print(f"     Tag: {tag}")

            # Resolve Lambda ARN from SSM
            function_arn = self._resolve_ssm_parameter(ssm_client, ssm_parameter)
            if not function_arn:
                results["deployments"].append(
                    {
                        "account": account,
                        "region": region,
                        "ssm_parameter": ssm_parameter,
                        "error": f"SSM parameter not found: {ssm_parameter}",
                    }
                )
                continue

            print(f"     Lambda ARN: {function_arn}")

            # Get current image
            current_image = self._get_current_image_uri(lambda_client, function_arn)
            if current_image:
                print(f"     Current image: {current_image}")

            # Build new image URI — ECR images live in the devops/caller account,
            # not necessarily the deployment account where the Lambda runs
            new_image_uri = self._build_image_uri(ecr_account, region, repo_name, tag)
            print(f"     New image (tag): {new_image_uri}")

            # Resolve the tag to an immutable digest to avoid race conditions
            # where Lambda can't pull a just-pushed tag that hasn't propagated yet
            ecr_client = self._get_ecr_client(ecr_account, region)
            digest = self._resolve_image_digest(ecr_client, repo_name, tag)
            use_digest = False
            if use_digest and digest:
                new_image_uri = (
                    f"{ecr_account}.dkr.ecr.{region}.amazonaws.com/{repo_name}@{digest}"
                )
                print(f"     Resolved digest: {digest}")
                print(f"     New image (digest): {new_image_uri}")
            elif not use_digest:
                print(f"     Using {tag}")
            else:
                print(f"  ⚠️  Could not resolve digest, falling back to tag-based URI")

            # Perform update
            if self.dry_run:
                print(f"  🔍 DRY RUN: Would update Lambda")
                results["deployments"].append(
                    {
                        "account": account,
                        "region": region,
                        "status": "dry_run",
                    }
                )
            else:
                success = self._update_lambda_image(
                    lambda_client,
                    function_arn,
                    new_image_uri,
                )
                results["deployments"].append(
                    {
                        "account": account,
                        "region": region,
                        "ssm_parameter": ssm_parameter,
                        "function_arn": function_arn,
                        "status": "success" if success else "failed",
                    }
                )

        return results

    def run(self) -> int:
        """
        Run the Lambda image updater.

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        print("=" * 70)
        print(f"  Lambda Image Updater v{__version__}")
        print("=" * 70)
        print(f"Config: {self.config_path}")
        if self.dry_run:
            print("Mode: DRY RUN (no changes will be made)")
        if self.image_name:
            print(f"Filter: {self.image_name}")
        print()

        images = self.config.get("images", [])
        total_images = len(images)
        processed = 0
        updated = 0
        failed = 0
        failed_details: List[Dict[str, Any]] = []

        for image_config in images:
            repo_name = image_config.get("repo_name", "unknown")

            # Filter by image name if specified
            if self.image_name and self.image_name not in repo_name:
                continue

            print(f"─" * 70)
            print(f"Image: {repo_name}")
            print(f"─" * 70)

            result = self.update_image(image_config)
            processed += 1

            if result.get("skipped"):
                continue

            for deployment_result in result.get("deployments", []):
                if deployment_result.get("status") == "success":
                    updated += 1
                elif (
                    deployment_result.get("error")
                    or deployment_result.get("status") == "failed"
                ):
                    failed += 1
                    failed_details.append(
                        {
                            "image": repo_name,
                            "account": deployment_result.get("account", "unknown"),
                            "region": deployment_result.get("region", "unknown"),
                            "ssm_parameter": deployment_result.get("ssm_parameter", ""),
                            "function_arn": deployment_result.get("function_arn", ""),
                            "error": deployment_result.get(
                                "error", "Update failed (no error details)"
                            ),
                        }
                    )

        print()
        print("=" * 70)
        print(f"  Summary")
        print("=" * 70)
        print(f"Total images: {total_images}")
        print(f"Processed: {processed}")
        print(f"Updated: {updated}")
        print(f"Failed: {failed}")

        if failed_details:
            print()
            print("  ❌ Failed Deployments:")
            for detail in failed_details:
                print(
                    f"     • {detail['image']} → {detail['account']}/{detail['region']}"
                )
                if detail.get("ssm_parameter"):
                    print(f"       SSM: {detail['ssm_parameter']}")
                if detail.get("function_arn"):
                    print(f"       Lambda: {detail['function_arn']}")
                print(f"       Error: {detail['error']}")

        print()

        return 0 if failed == 0 else 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Update Lambda functions with new Docker images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to docker-images.json configuration file",
    )
    parser.add_argument(
        "--image-name",
        help="Optional: Update only this specific image (partial match on repo_name)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes",
    )
    parser.add_argument(
        "--cross-account-role",
        help="IAM role name for cross-account access (default: DevOpsCrossAccountAccessRole)",
    )

    args = parser.parse_args()

    try:
        updater = LambdaImageUpdater(
            config_path=args.config,
            dry_run=args.dry_run,
            image_name=args.image_name,
            cross_account_role=args.cross_account_role,
        )
        sys.exit(updater.run())
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
