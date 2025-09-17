"""
Live SSM Parameter Resolver for CDK Factory
Provides real-time SSM parameter resolution during CDK synthesis
"""

import os
import time
from typing import Dict, Any, Optional, Union
from aws_lambda_powertools import Logger
from boto3_assist.ssm.parameter_store.parameter_store import ParameterStore

logger = Logger(service="LiveSsmResolver")


class LiveSsmResolver:
    """
    Resolves SSM parameters with live AWS API calls during CDK synthesis.

    Use cases:
    - Cross-stack deployments where infrastructure creates parameters first
    - IAM policy generation requiring concrete values (not CDK tokens)
    - Resource name resolution for cross-references
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get("live_resolution", {})
        self.enabled = self.config.get("enabled", False)
        self.mode = self.config.get(
            "mode", "fallback"
        )  # "always", "fallback", "disabled"
        self.cache_ttl = self.config.get("cache_ttl", 300)
        self.retry_attempts = self.config.get("retry_attempts", 3)

        # Initialize cache
        self._cache: Dict[str, Dict[str, Any]] = {}

        # Initialize SSM client with boto3_assist
        self._ssm_client = None
        if self.enabled:
            self._init_ssm_client()

    def _init_ssm_client(self):
        """Initialize SSM client using boto3_assist with profile support"""
        try:
            profile = self.config.get("profile") or os.getenv("AWS_PROFILE")
            region = self.config.get("region") or os.getenv("AWS_REGION", "us-east-1")

            self._ssm_client = ParameterStore(profile_name=profile, region_name=region)
            logger.info(
                f"Initialized live SSM resolver with profile: {profile}, region: {region}"
            )
        except Exception as e:
            logger.warning(f"Failed to initialize SSM client: {e}")
            self.enabled = False

    def resolve_parameter(
        self, parameter_path: str, fallback_value: Optional[str] = None
    ) -> Optional[str]:
        """
        Resolve SSM parameter with live API call.

        Args:
            parameter_path: SSM parameter path (e.g., /workload/dev/cognito/user-pool/user-pool-arn)
            fallback_value: Value to return if live resolution fails

        Returns:
            Parameter value or fallback_value
        """
        if not self.enabled or self.mode == "disabled":
            return fallback_value

        # Check cache first
        cached_value = self._get_cached_value(parameter_path)
        if cached_value is not None:
            return cached_value

        # Attempt live resolution
        try:
            value = self._fetch_parameter_value(parameter_path)
            if value:
                self._cache_value(parameter_path, value)
                logger.info(f"Live resolved SSM parameter: {parameter_path}")
                return value
        except Exception as e:
            logger.warning(f"Live SSM resolution failed for {parameter_path}: {e}")

        # Return fallback if live resolution fails
        if fallback_value:
            logger.info(f"Using fallback value for {parameter_path}")

        return fallback_value

    def resolve_parameters_batch(
        self, parameter_paths: list[str]
    ) -> Dict[str, Optional[str]]:
        """
        Resolve multiple SSM parameters in batch for efficiency.

        Args:
            parameter_paths: List of SSM parameter paths

        Returns:
            Dictionary mapping parameter paths to their values
        """
        results = {}

        if not self.enabled or self.mode == "disabled":
            return {path: None for path in parameter_paths}

        # Check cache for all parameters
        uncached_paths = []
        for path in parameter_paths:
            cached_value = self._get_cached_value(path)
            if cached_value is not None:
                results[path] = cached_value
            else:
                uncached_paths.append(path)

        # Batch fetch uncached parameters
        if uncached_paths:
            try:
                batch_results = self._fetch_parameters_batch(uncached_paths)
                for path, value in batch_results.items():
                    if value:
                        results[path] = value
                        self._cache_value(path, value)
                    else:
                        results[path] = None
            except Exception as e:
                logger.warning(f"Batch SSM resolution failed: {e}")
                # Set all uncached to None
                for path in uncached_paths:
                    results[path] = None

        return results

    def _fetch_parameter_value(self, parameter_path: str) -> Optional[str]:
        """Fetch single parameter value with retry logic"""
        for attempt in range(self.retry_attempts):
            try:
                response = self._ssm_client.get_parameter(parameter_path)
                return response.get("Parameter", {}).get("Value")
            except Exception as e:
                if attempt == self.retry_attempts - 1:
                    raise e
                time.sleep(0.5 * (attempt + 1))  # Exponential backoff
        return None

    def _fetch_parameters_batch(
        self, parameter_paths: list[str]
    ) -> Dict[str, Optional[str]]:
        """Fetch multiple parameters using get_parameters API"""
        results = {}

        # SSM get_parameters has a limit of 10 parameters per call
        batch_size = 10
        for i in range(0, len(parameter_paths), batch_size):
            batch_paths = parameter_paths[i : i + batch_size]

            try:
                response = self._ssm_client.get_parameters(batch_paths)

                # Process successful parameters
                for param in response.get("Parameters", []):
                    results[param["Name"]] = param["Value"]

                # Mark invalid parameters as None
                for invalid_param in response.get("InvalidParameters", []):
                    results[invalid_param] = None

            except Exception as e:
                logger.warning(f"Batch fetch failed for paths {batch_paths}: {e}")
                # Mark all as None on failure
                for path in batch_paths:
                    results[path] = None

        return results

    def _get_cached_value(self, parameter_path: str) -> Optional[str]:
        """Get cached parameter value if still valid"""
        if parameter_path not in self._cache:
            return None

        cache_entry = self._cache[parameter_path]
        if time.time() - cache_entry["timestamp"] > self.cache_ttl:
            # Cache expired
            del self._cache[parameter_path]
            return None

        return cache_entry["value"]

    def _cache_value(self, parameter_path: str, value: str):
        """Cache parameter value with timestamp"""
        self._cache[parameter_path] = {"value": value, "timestamp": time.time()}

    def clear_cache(self):
        """Clear all cached parameter values"""
        self._cache.clear()
        logger.info("Cleared SSM parameter cache")

    def is_token_value(self, value: str) -> bool:
        """Check if a value is a CDK token that needs live resolution"""
        if not isinstance(value, str):
            return False
        return value.startswith("${Token[") and value.endswith("]}")

    def should_use_live_resolution(self, cdk_token_value: Optional[str] = None) -> bool:
        """
        Determine if live resolution should be used based on mode and context.

        Args:
            cdk_token_value: The CDK token value (if any)

        Returns:
            True if live resolution should be attempted
        """
        if not self.enabled:
            return False

        if self.mode == "always":
            return True
        elif self.mode == "fallback":
            # Use live resolution if we have a CDK token (indicating cross-stack dependency)
            return cdk_token_value is not None and self.is_token_value(cdk_token_value)
        else:  # disabled
            return False
