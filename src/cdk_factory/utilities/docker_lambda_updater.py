#!/usr/bin/env python3
"""
Docker Lambda Updater — Unified Docker Lambda Update Tool with SSM Auto-Discovery

Replaces both LambdaImageUpdater (Acme-SaaS-DevOps-CDK) and the
lambda_boto3_utilities.py pattern (Acme-SaaS-Application) with a single
CLI utility that supports:

- Repo-triggered updates via docker-images.json (config-driven mode)
- Post-deployment refresh via SSM namespace (direct namespace mode)
- Locked version tags for production environments
- Multi-account/multi-environment targeting
- Dry-run preview mode
- SSM manifest-based auto-discovery

Usage:
    # Config-driven mode (repo-triggered update)
    python -m cdk_factory.utilities.docker_lambda_updater \
        --config /path/to/docker-images.json

    # Direct namespace mode (post-deployment refresh)
    python -m cdk_factory.utilities.docker_lambda_updater \
        --ssm-namespace acme-nca-saas/dev/lambda/core-services \
        --account 959096737760 --region us-east-1 --refresh

    # With locked versions
    python -m cdk_factory.utilities.docker_lambda_updater \
        --config /path/to/docker-images.json \
        --locked-versions /path/to/.docker-locked-versions.json

    # Dry run
    python -m cdk_factory.utilities.docker_lambda_updater \
        --config /path/to/docker-images.json --dry-run

"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class DockerLambdaUpdater:
    """Unified Docker Lambda update tool with SSM auto-discovery."""

    def __init__(
        self,
        config_path: Optional[str] = None,
        ssm_namespace: Optional[str] = None,
        account: Optional[str] = None,
        region: Optional[str] = None,
        dry_run: bool = False,
        refresh: bool = False,
        image_name: Optional[str] = None,
        locked_versions_path: Optional[str] = None,
        cross_account_role: Optional[str] = None,
    ):
        """
        Initialize the Docker Lambda updater.

        Args:
            config_path: Path to docker-images.json configuration file
            ssm_namespace: Direct SSM namespace for post-deployment mode
            account: Target AWS account ID
            region: Target AWS region
            dry_run: If True, only show what would be updated without making changes
            refresh: If True, re-deploy with current image URI (cold-start refresh)
            image_name: Optional specific ECR repo name to filter updates
            locked_versions_path: Path to .docker-locked-versions.json
            cross_account_role: IAM role name for cross-account access
        """
        self.config_path = config_path
        self.ssm_namespace = ssm_namespace
        self.account = account
        self.region = region or "us-east-1"
        self.dry_run = dry_run
        self.refresh = refresh
        self.image_name = image_name
        self.locked_versions_path = locked_versions_path

        # Cross-account role: constructor arg → env var (ARN or name) → default name
        self._cross_account_role = cross_account_role
        if not self._cross_account_role:
            # Check for full ARN first, then role name
            self._cross_account_role = os.environ.get(
                "CROSS_ACCOUNT_ROLE_ARN"
            ) or os.environ.get("CROSS_ACCOUNT_ROLE_NAME")

        # STS client and caller account detection (deferred until needed)
        self._sts_client: Optional[Any] = None
        self._caller_account: Optional[str] = None

        # Session cache for assumed-role sessions (keyed by account ID)
        self._session_cache: Dict[str, boto3.Session] = {}

        # Loaded config (populated by _load_config if config_path provided)
        self.config: Optional[Dict[str, Any]] = None

        # Locked versions (populated by _load_locked_versions if path provided)
        self.locked_versions: Optional[List[Dict[str, Any]]] = None

        # Track Lambda ARNs already processed in this run to avoid duplicates
        self._processed_arns: set = set()

    # ------------------------------------------------------------------
    # Cross-account session management
    # ------------------------------------------------------------------

    def _get_caller_account(self) -> str:
        """Get the caller's AWS account ID via STS, cached after first call."""
        if self._caller_account is None:
            if self._sts_client is None:
                self._sts_client = boto3.client("sts")
            self._caller_account = self._sts_client.get_caller_identity()["Account"]
        return self._caller_account

    def _get_cross_account_session(
        self,
        account: str,
        region: str,
        role_name: Optional[str] = None,
    ) -> Optional[boto3.Session]:
        """
        Get a boto3 Session with assumed-role credentials.

        Assumes the role when:
        - Target account differs from caller account, OR
        - An explicit role ARN/name is provided (even for same account)

        Supports both full ARNs and role names.

        Args:
            account: Target AWS account ID
            region: AWS region
            role_name: Optional per-deployment role name/ARN override

        Returns:
            boto3.Session with temporary credentials, or None if no role assumption needed
        """
        effective_role = role_name or self._cross_account_role

        # No role configured and same account → no assumption needed
        if not effective_role:
            return None

        caller_account = self._get_caller_account()
        if account == caller_account and not effective_role:
            return None

        # Cache key includes account
        cache_key = f"{account}-{effective_role}"
        if cache_key in self._session_cache:
            return self._session_cache[cache_key]

        if self._sts_client is None:
            self._sts_client = boto3.client("sts")

        # If it's already a full ARN, use it directly; otherwise construct it
        if effective_role.startswith("arn:aws:iam::"):
            role_arn = effective_role
        else:
            role_arn = f"arn:aws:iam::{account}:role/{effective_role}"

        response = self._sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName="docker-lambda-updater",
        )
        creds = response["Credentials"]

        session = boto3.Session(
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )
        self._session_cache[cache_key] = session
        return session

    def _get_ssm_client(
        self,
        account: str,
        region: str,
        role_name: Optional[str] = None,
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
        self,
        account: str,
        region: str,
        role_name: Optional[str] = None,
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

    def _get_ecr_client(
        self,
        account: str,
        region: str,
        role_name: Optional[str] = None,
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

    # ------------------------------------------------------------------
    # Config loading and validation (Task 3.2)
    # ------------------------------------------------------------------

    def _load_config(self) -> Dict[str, Any]:
        """
        Load and validate docker-images.json configuration.

        Returns:
            Parsed config dict with validated 'images' array.

        Raises:
            FileNotFoundError: If config file does not exist.
            ValueError: If config file is missing 'images' array.
        """
        if not self.config_path:
            raise ValueError("No config_path provided")

        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, "r") as f:
            config = json.load(f)

        if "images" not in config:
            raise ValueError(f"Config file missing 'images' array: {self.config_path}")

        return config

    def _validate_deployment_entry(
        self,
        deployment: Dict[str, Any],
        image_name: str,
        deployment_index: int,
    ) -> Optional[str]:
        """
        Validate a deployment entry has the required discovery fields.

        A valid entry must have at least one of:
        - ssm_parameter (legacy direct resolution)
        - ssm_namespace (single namespace auto-discovery)
        - ssm_namespaces (multi-namespace auto-discovery)

        When both ssm_parameter and ssm_namespace/ssm_namespaces are present,
        ssm_namespace/ssm_namespaces takes precedence and ssm_parameter is ignored.

        Args:
            deployment: Deployment entry dict from docker-images.json
            image_name: Parent image repo_name for error context
            deployment_index: Index of this deployment in the array for error context

        Returns:
            Validation error message string, or None if valid.
        """
        has_ssm_parameter = bool(deployment.get("ssm_parameter"))
        has_ssm_prefix = bool(deployment.get("ssm_prefix"))
        # Backward compat: also accept ssm_namespace as alias for ssm_prefix
        has_ssm_namespace = bool(deployment.get("ssm_namespace"))

        if not has_ssm_parameter and not has_ssm_prefix and not has_ssm_namespace:
            return (
                f"Deployment entry [{deployment_index}] for image '{image_name}' "
                f"is missing 'ssm_prefix' or 'ssm_parameter'. "
                f"At least one discovery field is required."
            )

        if has_ssm_parameter and (has_ssm_prefix or has_ssm_namespace):
            logger.info(
                "Deployment entry [%d] for image '%s' has both 'ssm_parameter' and "
                "'ssm_prefix'. Using ssm_prefix (auto-discovery); "
                "'ssm_parameter' will be ignored.",
                deployment_index,
                image_name,
            )

        return None

    def _get_ssm_prefix_from_deployment(
        self, deployment: Dict[str, Any]
    ) -> Optional[str]:
        """
        Extract the SSM prefix from a deployment entry.

        Checks ssm_prefix first, then ssm_namespace as a backward-compat alias.

        Args:
            deployment: Deployment entry dict

        Returns:
            SSM prefix string, or None if not present.
        """
        return deployment.get("ssm_prefix") or deployment.get("ssm_namespace")

    # ------------------------------------------------------------------
    # ECR-keyed discovery
    # ------------------------------------------------------------------

    def _discover_docker_lambdas(
        self,
        ssm_client: Any,
        ssm_prefix: str,
        repo_name: str,
        account: str = "",
        region: str = "",
    ) -> List[Dict[str, str]]:
        """
        Discover all Docker Lambda ARNs registered under an ECR repo path.

        Lambda stacks register Docker Lambdas at:
            /{ssm_prefix}/ecr/{safe-repo-name}/{lambda-name}/arn

        This method does a single get_parameters_by_path call on
        /{ssm_prefix}/ecr/{safe-repo-name}/ to find all registered lambdas.

        Args:
            ssm_client: boto3 SSM client
            ssm_prefix: Workload/deployment prefix (e.g. "acme-saas/dev")
            repo_name: ECR repository name (e.g. "acme-analytics/v3/acme-saas-core-services")
            account: AWS account ID (for error messages)
            region: AWS region (for error messages)

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
            logger.error(
                "Failed to discover Docker Lambdas at %s (account=%s, region=%s): %s",
                ecr_path,
                account,
                region,
                e,
            )
            return []

        if not discovered:
            logger.warning(
                "No Docker Lambdas found at %s (account=%s, region=%s)",
                ecr_path,
                account,
                region,
            )

        return discovered

    # ------------------------------------------------------------------
    # Legacy SSM parameter direct resolution (Task 3.5)
    # ------------------------------------------------------------------

    def _resolve_ssm_parameter(
        self,
        ssm_client: Any,
        parameter_path: str,
    ) -> Optional[str]:
        """
        Resolve an SSM parameter value directly (legacy mode).

        Used for backward compatibility with docker-images.json entries
        that specify ssm_parameter instead of ssm_namespace.

        Args:
            ssm_client: boto3 SSM client
            parameter_path: Full SSM parameter path

        Returns:
            Parameter value string, or None if not found.
        """
        try:
            response = ssm_client.get_parameter(Name=parameter_path)
            return response["Parameter"]["Value"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "ParameterNotFound":
                logger.warning(
                    "SSM parameter not found: %s",
                    parameter_path,
                )
                return None
            raise

    # ------------------------------------------------------------------
    # Locked version tag resolution (Task 3.6)
    # ------------------------------------------------------------------

    def _load_locked_versions(self, path: str) -> List[Dict[str, Any]]:
        """
        Load locked versions configuration from a JSON file.

        The file contains an array of objects with 'name', 'tag', and 'ecr' fields.

        Args:
            path: Path to .docker-locked-versions.json file

        Returns:
            List of locked version entry dicts.

        Raises:
            FileNotFoundError: If the locked versions file does not exist.
            ValueError: If the file content is not a valid JSON array.
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Locked versions file not found: {path}")

        with open(path, "r") as f:
            data = json.load(f)

        if not isinstance(data, list):
            raise ValueError(f"Locked versions file must contain a JSON array: {path}")

        return data

    @staticmethod
    def _resolve_tag(
        lambda_name: str,
        deployment_tag: str,
        locked_versions: Optional[List[Dict[str, Any]]],
    ) -> Tuple[Optional[str], str]:
        """
        Resolve the image tag for a Docker Lambda, considering locked versions.

        Resolution rules:
        1. If locked_versions is None or empty → use deployment_tag ("deployment")
        2. If a matching entry exists with a non-empty tag → use locked tag ("locked")
        3. If a matching entry exists with an empty tag → skip lambda ("skipped")
        4. If no matching entry exists → use deployment_tag ("deployment")

        Args:
            lambda_name: Docker Lambda name (matched against 'name' field)
            deployment_tag: Default tag from the deployment entry
            locked_versions: Optional list of locked version entries

        Returns:
            Tuple of (resolved_tag, source) where:
            - resolved_tag: The tag string to use, or None if skipped
            - source: One of "locked", "deployment", or "skipped"
        """
        if not locked_versions:
            return (deployment_tag, "deployment")

        for entry in locked_versions:
            if entry.get("name") == lambda_name:
                tag = entry.get("tag", "")
                if tag:
                    return (tag, "locked")
                else:
                    return (None, "skipped")

        return (deployment_tag, "deployment")

    # ------------------------------------------------------------------
    # Lambda update with retry (Task 4.1 helper)
    # ------------------------------------------------------------------

    def _update_lambda(
        self,
        lambda_client: Any,
        function_arn: str,
        new_image_uri: str,
        max_retries: int = 3,
        base_delay: float = 2.0,
    ) -> bool:
        """
        Update Lambda function code with new image URI.

        Includes retry with exponential backoff for transient
        AccessDeniedException errors caused by ECR image propagation delays.

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
                logger.info(
                    "Updated %s successfully (LastModified=%s, Version=%s)",
                    function_arn,
                    response.get("LastModified"),
                    response.get("Version"),
                )
                return True
            except ClientError as e:
                error_code = e.response["Error"]["Code"]
                is_ecr_access_error = (
                    error_code == "AccessDeniedException" and "ECR" in str(e)
                )

                if is_ecr_access_error and attempt < max_retries:
                    delay = base_delay * (2**attempt)
                    logger.info(
                        "ECR image not yet accessible for %s, retrying in %.0fs "
                        "(attempt %d/%d)...",
                        function_arn,
                        delay,
                        attempt + 1,
                        max_retries,
                    )
                    time.sleep(delay)
                    continue

                logger.error("Failed to update %s: %s", function_arn, e)
                return False
        return False

    # ------------------------------------------------------------------
    # Refresh mode (Task 4.3)
    # ------------------------------------------------------------------

    def _refresh_lambda(
        self,
        lambda_client: Any,
        function_arn: str,
        locked_tag: Optional[str] = None,
        ecr_account: Optional[str] = None,
        region: Optional[str] = None,
        repo_name: Optional[str] = None,
    ) -> bool:
        """
        Re-deploy a Lambda with its current image URI (cold-start refresh).

        When locked_tag is provided, builds the image URI from the locked tag
        instead of reading the current image URI from the Lambda function.

        Tags each updated Lambda with LastImageRefresh timestamp and
        RefreshedBy=deployment-pipeline.

        Args:
            lambda_client: boto3 Lambda client
            function_arn: Lambda function ARN
            locked_tag: Optional locked version tag to use instead of current image
            ecr_account: ECR account ID (required when locked_tag is provided)
            region: AWS region (required when locked_tag is provided)
            repo_name: ECR repo name (required when locked_tag is provided)

        Returns:
            True if successful, False otherwise
        """
        if locked_tag and ecr_account and region and repo_name:
            # Build image URI from locked tag
            image_uri = (
                f"{ecr_account}.dkr.ecr.{region}.amazonaws.com/"
                f"{repo_name}:{locked_tag}"
            )
            logger.info("Refresh %s with locked tag image: %s", function_arn, image_uri)
        else:
            # Get current image URI from the Lambda function
            try:
                response = lambda_client.get_function(FunctionName=function_arn)
                image_uri = response.get("Code", {}).get("ImageUri")
            except ClientError as e:
                logger.error(
                    "Failed to get current image URI for %s: %s. Skipping.",
                    function_arn,
                    e,
                )
                return False

            if not image_uri:
                logger.error(
                    "No image URI found for %s. Skipping refresh.", function_arn
                )
                return False

            logger.info("Refresh %s with current image: %s", function_arn, image_uri)

        # Update function code with the (same or locked) image URI
        success = self._update_lambda(lambda_client, function_arn, image_uri)
        if not success:
            return False

        # Tag the Lambda with refresh metadata
        self._tag_lambda_refresh(lambda_client, function_arn)
        return True

    def _tag_lambda_refresh(
        self,
        lambda_client: Any,
        function_arn: str,
    ) -> None:
        """
        Tag Lambda with LastImageRefresh timestamp and
        RefreshedBy=deployment-pipeline.

        Args:
            lambda_client: boto3 Lambda client
            function_arn: Lambda function ARN
        """
        try:
            refresh_timestamp = datetime.now(tz=UTC).isoformat() + "Z"
            lambda_client.tag_resource(
                Resource=function_arn,
                Tags={
                    "LastImageRefresh": refresh_timestamp,
                    "RefreshedBy": "deployment-pipeline",
                },
            )
            logger.info(
                "Tagged %s with refresh timestamp: %s",
                function_arn,
                refresh_timestamp,
            )
        except ClientError as e:
            logger.warning("Failed to tag %s: %s", function_arn, e)
        except Exception as e:
            logger.warning("Unexpected error tagging %s: %s", function_arn, e)

    # ------------------------------------------------------------------
    # Config-driven update mode (Task 4.1)
    # ------------------------------------------------------------------

    def _run_config_mode(self) -> Dict[str, Any]:
        """
        Run in config-driven mode: iterate images and their lambda_deployments.

        For each deployment entry:
        - Discover Lambdas via manifest (ssm_namespace) or resolve via
          ssm_parameter (legacy)
        - Resolve tags with optional locked versions
        - Build image URI and call update_function_code (or refresh)
        - Wrap each deployment in try/except for resilience (Task 4.5)

        Returns:
            Results dict with per-image deployment results.
        """
        config = self._load_config()
        self.config = config

        images = config.get("images", [])
        results: Dict[str, Any] = {"images": []}
        has_errors = False

        for image_config in images:
            repo_name = image_config.get("repo_name", "")
            if not repo_name:
                logger.warning("Skipping image entry with no repo_name")
                continue

            # Filter by image_name if specified
            if self.image_name and self.image_name not in repo_name:
                continue

            deployments = image_config.get("lambda_deployments", [])
            if not deployments:
                logger.info("No lambda_deployments for %s", repo_name)
                continue

            image_result: Dict[str, Any] = {
                "repo_name": repo_name,
                "deployments": [],
            }

            # Reset processed ARNs per image to avoid cross-deployment duplicates
            self._processed_arns = set()

            for idx, deployment in enumerate(deployments):
                # Task 4.5: Wrap each deployment entry in try/except
                try:
                    dep_result = self._process_deployment_entry(
                        deployment, repo_name, idx
                    )
                    image_result["deployments"].append(dep_result)
                    if dep_result.get("failed", 0) > 0:
                        has_errors = True
                except Exception as e:
                    logger.error(
                        "Failed to process deployment [%d] for image '%s': %s. "
                        "Continuing with remaining deployments.",
                        idx,
                        repo_name,
                        e,
                    )
                    image_result["deployments"].append(
                        {
                            "account": deployment.get("account", "unknown"),
                            "region": deployment.get("region", "unknown"),
                            "error": str(e),
                            "discovered": 0,
                            "updated": 0,
                            "failed": 1,
                            "skipped": 0,
                            "details": [],
                        }
                    )
                    has_errors = True

            results["images"].append(image_result)

        results["has_errors"] = has_errors
        return results

    def _process_deployment_entry(
        self,
        deployment: Dict[str, Any],
        repo_name: str,
        deployment_index: int,
    ) -> Dict[str, Any]:
        """
        Process a single deployment entry from docker-images.json.

        Args:
            deployment: Deployment entry dict
            repo_name: Parent image ECR repo name
            deployment_index: Index of this deployment in the array

        Returns:
            Deployment result dict with counts and details.
        """
        # Skip disabled deployments
        enabled = deployment.get("enabled", True)
        if not enabled:
            label = (
                deployment.get("ssm_prefix")
                or deployment.get("ssm_namespace")
                or deployment.get("ssm_parameter")
                or "unknown"
            )
            logger.warning(
                "Skipping disabled deployment [%d] for image '%s': %s",
                deployment_index,
                repo_name,
                label,
            )
            return {
                "account": deployment.get("account", "unknown"),
                "region": deployment.get("region", "unknown"),
                "discovered": 0,
                "updated": 0,
                "failed": 0,
                "skipped": 1,
                "details": [],
                "status": "disabled",
            }

        # Validate the deployment entry
        validation_error = self._validate_deployment_entry(
            deployment, repo_name, deployment_index
        )
        if validation_error:
            logger.error(validation_error)
            return {
                "account": deployment.get("account", "unknown"),
                "region": deployment.get("region", "unknown"),
                "error": validation_error,
                "discovered": 0,
                "updated": 0,
                "failed": 1,
                "skipped": 0,
                "details": [],
            }

        account = deployment.get("account", self.account or "")
        region = deployment.get("region", self.region)
        tag = deployment.get("tag", "latest")
        role_name = deployment.get("role_name")
        ecr_account = deployment.get("ecr_account")

        # Get clients for this deployment's account/region
        ssm_client = self._get_ssm_client(account, region, role_name=role_name)
        lambda_client = self._get_lambda_client(account, region, role_name=role_name)

        # Load per-deployment locked versions if specified
        locked_versions = self.locked_versions
        dep_locked_path = deployment.get("locked_versions")
        if dep_locked_path:
            locked_versions = self._load_locked_versions(dep_locked_path)
        elif self.locked_versions_path and locked_versions is None:
            locked_versions = self._load_locked_versions(self.locked_versions_path)
            self.locked_versions = locked_versions

        # Determine ECR account: per-deployment override → caller account
        if not ecr_account:
            ecr_account = self._get_caller_account()

        # Discover Docker Lambdas
        ssm_prefix = self._get_ssm_prefix_from_deployment(deployment)
        lambda_arns: List[Dict[str, Any]] = []

        if ssm_prefix:
            # ECR-keyed auto-discovery
            discovered = self._discover_docker_lambdas(
                ssm_client,
                ssm_prefix,
                repo_name,
                account=account,
                region=region,
            )
            for entry in discovered:
                lambda_arns.append(
                    {
                        "arn": entry["arn"],
                        "name": entry["name"],
                        "param_path": entry["param_path"],
                    }
                )
        else:
            # Legacy ssm_parameter direct resolution
            ssm_parameter = deployment.get("ssm_parameter", "")
            arn_value = self._resolve_ssm_parameter(ssm_client, ssm_parameter)
            if arn_value:
                parts = ssm_parameter.rstrip("/").rsplit("/", 2)
                lambda_name = (
                    parts[-2] if len(parts) >= 2 and parts[-1] == "arn" else parts[-1]
                )
                lambda_arns.append(
                    {
                        "arn": arn_value,
                        "name": lambda_name,
                        "param_path": ssm_parameter,
                    }
                )

        # Process each discovered Lambda
        dep_result: Dict[str, Any] = {
            "account": account,
            "region": region,
            "ssm_prefix": ssm_prefix,
            "discovered": len(lambda_arns),
            "updated": 0,
            "failed": 0,
            "skipped": 0,
            "details": [],
        }

        for lambda_info in lambda_arns:
            function_arn = lambda_info["arn"]
            lambda_name = lambda_info["name"]

            # Skip if this Lambda ARN was already processed in this run
            if function_arn in self._processed_arns:
                logger.info(
                    "Skipping %s (ARN already processed in this run)", lambda_name
                )
                dep_result["skipped"] += 1
                dep_result["details"].append(
                    {
                        "lambda_name": lambda_name,
                        "function_arn": function_arn,
                        "tag": "",
                        "tag_source": "duplicate",
                        "status": "skipped",
                    }
                )
                continue
            self._processed_arns.add(function_arn)

            # Resolve tag (with optional locked versions)
            resolved_tag, tag_source = self._resolve_tag(
                lambda_name, tag, locked_versions
            )

            if tag_source == "skipped":
                logger.info("Skipping %s (locked version has empty tag)", lambda_name)
                dep_result["skipped"] += 1
                dep_result["details"].append(
                    {
                        "lambda_name": lambda_name,
                        "function_arn": function_arn,
                        "tag": "",
                        "tag_source": tag_source,
                        "status": "skipped",
                    }
                )
                continue

            # Build image URI
            new_image_uri = (
                f"{ecr_account}.dkr.ecr.{region}.amazonaws.com/"
                f"{repo_name}:{resolved_tag}"
            )

            # Task 4.4: Dry-run mode — display info but don't update
            if self.dry_run:
                print(
                    f"  🔍 DRY RUN: {lambda_name}\n"
                    f"     ARN: {function_arn}\n"
                    f"     Image URI: {new_image_uri}\n"
                    f"     Tag: {resolved_tag} (source: {tag_source})"
                )
                dep_result["details"].append(
                    {
                        "lambda_name": lambda_name,
                        "function_arn": function_arn,
                        "tag": resolved_tag,
                        "tag_source": tag_source,
                        "status": "dry_run",
                    }
                )
                continue

            # Perform update or refresh
            if self.refresh:
                success = self._refresh_lambda(
                    lambda_client,
                    function_arn,
                    locked_tag=(resolved_tag if tag_source == "locked" else None),
                    ecr_account=ecr_account,
                    region=region,
                    repo_name=repo_name,
                )
            else:
                success = self._update_lambda(
                    lambda_client, function_arn, new_image_uri
                )

            status = "success" if success else "failed"
            dep_result["details"].append(
                {
                    "lambda_name": lambda_name,
                    "function_arn": function_arn,
                    "tag": resolved_tag,
                    "tag_source": tag_source,
                    "status": status,
                }
            )
            if success:
                dep_result["updated"] += 1
            else:
                dep_result["failed"] += 1

        # Dry-run summary per namespace
        if self.dry_run and namespaces:
            for ns in namespaces:
                count = sum(
                    1 for d in dep_result["details"] if d["status"] == "dry_run"
                )
                print(f"  📊 Namespace '{ns}': " f"{count} Docker Lambda(s) discovered")

        return dep_result

    # ------------------------------------------------------------------
    # Direct namespace mode (Task 4.2)
    # ------------------------------------------------------------------

    def _run_namespace_mode(self) -> Dict[str, Any]:
        """
        Run in direct namespace/prefix mode: discover all Docker Lambdas
        registered under the ECR subtree.

        Scans /{ssm_prefix}/ecr/ recursively to find all /arn params.
        When --refresh is set, re-deploys with current image URI.
        When --refresh is not set, requires image_name to build new image URI.

        Returns:
            Results dict with deployment details.
        """
        ssm_prefix = self.ssm_namespace  # ssm_prefix via CLI or env var
        account = self.account or self._get_caller_account()
        region = self.region

        ssm_client = self._get_ssm_client(account, region)
        lambda_client = self._get_lambda_client(account, region)

        # Load locked versions if path provided
        locked_versions = self.locked_versions
        if self.locked_versions_path and locked_versions is None:
            locked_versions = self._load_locked_versions(self.locked_versions_path)
            self.locked_versions = locked_versions

        # Discover all Docker Lambda ARN parameters under /{prefix}/ecr/
        arn_params: List[Dict[str, Any]] = []
        ecr_path = f"/{ssm_prefix}/ecr"

        try:
            paginator = ssm_client.get_paginator("get_parameters_by_path")
            for page in paginator.paginate(Path=ecr_path, Recursive=True):
                for param in page.get("Parameters", []):
                    if param["Name"].endswith("/arn"):
                        arn_params.append(param)
        except ClientError as e:
            logger.error(
                "Failed to discover parameters under %s (account=%s, region=%s): %s",
                ecr_path,
                account,
                region,
                e,
            )
            return {
                "ssm_prefix": ssm_prefix,
                "error": str(e),
                "discovered": 0,
                "updated": 0,
                "failed": 1,
                "skipped": 0,
                "details": [],
            }

        if not arn_params:
            logger.warning(
                "No Docker Lambda parameters found under %s (account=%s, region=%s)",
                ecr_path,
                account,
                region,
            )

        result: Dict[str, Any] = {
            "ssm_prefix": ssm_prefix,
            "account": account,
            "region": region,
            "discovered": len(arn_params),
            "updated": 0,
            "failed": 0,
            "skipped": 0,
            "details": [],
        }

        # When not in refresh mode, require image_name to build new
        # image URI
        if not self.refresh and not self.image_name:
            logger.error(
                "Direct namespace mode without --refresh requires "
                "--image-name to build the new image URI."
            )
            result["error"] = "Missing --image-name for non-refresh namespace mode"
            result["failed"] = len(arn_params)
            return result

        ecr_account = self._get_caller_account()

        for param in arn_params:
            function_arn = param["Value"]
            param_name = param["Name"]

            # Extract lambda name: /ns/.../lambda-name/arn → lambda-name
            parts = param_name.rstrip("/").rsplit("/", 2)
            lambda_name = parts[-2] if len(parts) >= 2 else param_name

            # Skip if this Lambda ARN was already processed in this run
            if function_arn in self._processed_arns:
                logger.info(
                    "Skipping %s (ARN already processed in this run)", lambda_name
                )
                result["skipped"] += 1
                result["details"].append(
                    {
                        "lambda_name": lambda_name,
                        "function_arn": function_arn,
                        "tag": "",
                        "tag_source": "duplicate",
                        "status": "skipped",
                    }
                )
                continue
            self._processed_arns.add(function_arn)

            # Dry-run mode (Task 4.4)
            if self.dry_run:
                resolved_tag = "current"
                tag_source = "current"

                if self.refresh:
                    print(
                        f"  🔍 DRY RUN (refresh): {lambda_name}\n"
                        f"     ARN: {function_arn}\n"
                        f"     Mode: refresh (re-deploy with current image)"
                    )
                else:
                    tag = "latest"
                    if locked_versions:
                        resolved_tag, tag_source = self._resolve_tag(
                            lambda_name, tag, locked_versions
                        )
                    else:
                        resolved_tag, tag_source = tag, "deployment"

                    new_image_uri = (
                        f"{ecr_account}.dkr.ecr.{region}.amazonaws.com/"
                        f"{self.image_name}:{resolved_tag}"
                    )
                    print(
                        f"  🔍 DRY RUN: {lambda_name}\n"
                        f"     ARN: {function_arn}\n"
                        f"     Image URI: {new_image_uri}\n"
                        f"     Tag: {resolved_tag} (source: {tag_source})"
                    )

                result["details"].append(
                    {
                        "lambda_name": lambda_name,
                        "function_arn": function_arn,
                        "tag": resolved_tag,
                        "tag_source": tag_source,
                        "status": "dry_run",
                    }
                )
                continue

            # Perform update or refresh
            resolved_tag = "current"
            tag_source = "current"

            if self.refresh:
                # Resolve locked tag if available
                locked_tag = None
                if locked_versions:
                    resolved_tag, tag_source = self._resolve_tag(
                        lambda_name, "latest", locked_versions
                    )
                    if tag_source == "skipped":
                        logger.info(
                            "Skipping %s (locked version has empty tag)",
                            lambda_name,
                        )
                        result["skipped"] += 1
                        result["details"].append(
                            {
                                "lambda_name": lambda_name,
                                "function_arn": function_arn,
                                "tag": "",
                                "tag_source": "skipped",
                                "status": "skipped",
                            }
                        )
                        continue
                    if tag_source == "locked":
                        locked_tag = resolved_tag

                success = self._refresh_lambda(
                    lambda_client,
                    function_arn,
                    locked_tag=locked_tag,
                    ecr_account=ecr_account,
                    region=region,
                    repo_name=self.image_name,
                )
            else:
                # Non-refresh: build new image URI
                tag = "latest"
                if locked_versions:
                    resolved_tag, tag_source = self._resolve_tag(
                        lambda_name, tag, locked_versions
                    )
                    if tag_source == "skipped":
                        logger.info(
                            "Skipping %s (locked version has empty tag)",
                            lambda_name,
                        )
                        result["skipped"] += 1
                        result["details"].append(
                            {
                                "lambda_name": lambda_name,
                                "function_arn": function_arn,
                                "tag": "",
                                "tag_source": "skipped",
                                "status": "skipped",
                            }
                        )
                        continue
                else:
                    resolved_tag = tag
                    tag_source = "deployment"

                new_image_uri = (
                    f"{ecr_account}.dkr.ecr.{region}.amazonaws.com/"
                    f"{self.image_name}:{resolved_tag}"
                )
                success = self._update_lambda(
                    lambda_client, function_arn, new_image_uri
                )

            status = "success" if success else "failed"
            result["details"].append(
                {
                    "lambda_name": lambda_name,
                    "function_arn": function_arn,
                    "tag": resolved_tag,
                    "tag_source": tag_source,
                    "status": status,
                }
            )
            if success:
                result["updated"] += 1
            else:
                result["failed"] += 1

        # Dry-run summary
        if self.dry_run:
            count = sum(1 for d in result["details"] if d["status"] == "dry_run")
            print(
                f"  📊 Namespace '{namespace}': " f"{count} Docker Lambda(s) discovered"
            )

        return result

    # ------------------------------------------------------------------
    # Run method with summary output and exit codes (Task 6.3)
    # ------------------------------------------------------------------

    def run(self) -> int:
        """
        Execute the updater based on the configured mode.

        Determines mode:
        - config_path set → config-driven mode (_run_config_mode)
        - ssm_namespace set → direct namespace mode (_run_namespace_mode)

        Writes a summary to stdout with counts of Docker Lambdas
        discovered, updated, and failed.

        Returns:
            0 on success (all updates succeeded or dry-run completed),
            1 on failure (one or more updates failed or fatal config error).
        """
        try:
            if self.config_path:
                results = self._run_config_mode()
                # Aggregate counts across all images and deployments
                total_discovered = 0
                total_updated = 0
                total_failed = 0
                for image_result in results.get("images", []):
                    for dep in image_result.get("deployments", []):
                        total_discovered += dep.get("discovered", 0)
                        total_updated += dep.get("updated", 0)
                        total_failed += dep.get("failed", 0)
                has_errors = results.get("has_errors", False)
            elif self.ssm_namespace:
                result = self._run_namespace_mode()
                total_discovered = result.get("discovered", 0)
                total_updated = result.get("updated", 0)
                total_failed = result.get("failed", 0)
                has_errors = total_failed > 0 or "error" in result
            else:
                print(
                    "Error: No config_path or ssm_namespace provided.",
                    file=sys.stderr,
                )
                return 1

            # Write summary to stdout
            print(
                f"\n📋 Summary: "
                f"{total_discovered} discovered, "
                f"{total_updated} updated, "
                f"{total_failed} failed"
            )

            return 1 if has_errors else 0

        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        except Exception as e:
            logger.exception("Unexpected error during run")
            print(f"Error: {e}", file=sys.stderr)
            return 1


# ------------------------------------------------------------------
# CLI argument parser and main entry point (Tasks 6.1, 6.2)
# ------------------------------------------------------------------


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """
    Parse CLI arguments for the Docker Lambda Updater.

    Applies environment variable fallbacks for pipeline integration:
    - SSM_DOCKER_LAMBDAS_PATH → --ssm-namespace
    - AWS_ACCOUNT_NUMBER → --account
    - AWS_REGION → --region
    - CROSS_ACCOUNT_ROLE_ARN → --cross-account-role

    CLI arguments take precedence over environment variables.

    Args:
        argv: Optional argument list (defaults to sys.argv[1:])

    Returns:
        Parsed argparse.Namespace
    """
    parser = argparse.ArgumentParser(
        prog="docker_lambda_updater",
        description=(
            "Unified Docker Lambda Update Tool with SSM Auto-Discovery. "
            "Supports repo-triggered updates via docker-images.json and "
            "post-deployment refresh via SSM namespace."
        ),
    )

    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to docker-images.json configuration file",
    )
    parser.add_argument(
        "--ssm-namespace",
        type=str,
        default=None,
        help="Direct SSM namespace for post-deployment mode",
    )
    parser.add_argument(
        "--account",
        type=str,
        default=None,
        help="Target AWS account ID",
    )
    parser.add_argument(
        "--region",
        type=str,
        default=None,
        help="Target AWS region",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        default=False,
        help="Enable Refresh_Mode (re-deploy with current image URI)",
    )
    parser.add_argument(
        "--locked-versions",
        type=str,
        default=None,
        help="Path to .docker-locked-versions.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview mode — show what would be updated without making changes",
    )
    parser.add_argument(
        "--image-name",
        type=str,
        default=None,
        help="Filter to a specific ECR repo name",
    )
    parser.add_argument(
        "--cross-account-role",
        type=str,
        default=None,
        help="IAM role name for cross-account access",
    )

    args = parser.parse_args(argv)

    # Task 6.2: Apply environment variable fallbacks
    # CLI arguments take precedence over env vars
    if args.ssm_namespace is None:
        args.ssm_namespace = os.environ.get("SSM_DOCKER_LAMBDAS_PATH")

    if args.account is None:
        args.account = os.environ.get("AWS_ACCOUNT_NUMBER")

    if args.region is None:
        args.region = os.environ.get("AWS_REGION")

    if args.cross_account_role is None:
        args.cross_account_role = os.environ.get("CROSS_ACCOUNT_ROLE_ARN")

    # When env vars are set and no CLI args → operate in direct namespace
    # Refresh_Mode (implicit refresh when only env vars drive the config)
    if (
        args.config is None
        and args.ssm_namespace is not None
        and not args.refresh
        and os.environ.get("SSM_DOCKER_LAMBDAS_PATH")
    ):
        args.refresh = True

    return args


def main(argv: Optional[List[str]] = None) -> None:
    """
    CLI entry point: parse args, create DockerLambdaUpdater, call run(),
    and sys.exit with the appropriate code.

    Args:
        argv: Optional argument list (defaults to sys.argv[1:])
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    args = parse_args(argv)

    # Validate at least one of --config or --ssm-namespace is provided
    if args.config is None and args.ssm_namespace is None:
        print(
            "Error: At least one of --config or --ssm-namespace "
            "(or SSM_DOCKER_LAMBDAS_PATH env var) is required.",
            file=sys.stderr,
        )
        sys.exit(1)

    updater = DockerLambdaUpdater(
        config_path=args.config,
        ssm_namespace=args.ssm_namespace,
        account=args.account,
        region=args.region,
        dry_run=args.dry_run,
        refresh=args.refresh,
        image_name=args.image_name,
        locked_versions_path=args.locked_versions,
        cross_account_role=args.cross_account_role,
    )

    exit_code = updater.run()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
