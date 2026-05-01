"""AWS resource introspector for discovered Lambda functions.

Connects to an AWS account via profile and resolves live resources
(CloudWatch log groups, SQS queue URLs) for Lambda functions discovered
from CDK configuration. Produces a ``workflow_service_map.json``-compatible
service map for consumption by SmartFlowService and summary_trace tools.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3
import botocore.exceptions

from cdk_factory.introspection.service_graph import ServiceGraph

logger = logging.getLogger(__name__)

# Retry configuration for AWS API throttling
_MAX_RETRIES = 3
_BASE_BACKOFF_SECONDS = 1.0


@dataclass
class ResolvedLambda:
    """A Lambda with its resolved AWS resources."""

    name: str
    log_group: Optional[str] = None
    log_group_stored_bytes: int = 0
    queue_urls: Dict[str, str] = field(default_factory=dict)
    dlq_urls: Dict[str, str] = field(default_factory=dict)
    unresolved: bool = False


class AwsCredentialError(Exception):
    """Raised when AWS credentials are missing or expired."""

    pass


class AwsIntrospector:
    """Resolves live AWS resources for discovered Lambda functions.

    Creates a boto3 session with the given profile and region, initializes
    CloudWatch Logs, SQS, and SSM clients, and provides methods to resolve
    log groups, queue URLs, and generate service maps.
    """

    def __init__(
        self,
        profile_name: Optional[str] = None,
        region: str = "us-east-1",
    ) -> None:
        """Initialize with AWS profile and region.

        Args:
            profile_name: AWS CLI profile name (e.g. ``"nca-development"``).
                If ``None``, uses the default credential chain.
            region: AWS region (default ``"us-east-1"``).

        Raises:
            AwsCredentialError: If credentials are expired or missing.
        """
        self._profile_name = profile_name
        self._region = region

        try:
            self._session = boto3.Session(
                profile_name=profile_name,
                region_name=region,
            )
        except botocore.exceptions.ProfileNotFound as exc:
            raise AwsCredentialError(
                f"AWS profile '{profile_name}' not found. "
                f"Available profiles can be listed with: aws configure list-profiles"
            ) from exc

        # Initialize clients
        self._logs_client = self._session.client("logs")
        self._sqs_client = self._session.client("sqs")
        self._ssm_client = self._session.client("ssm")

        # In-memory caches for the lifetime of this instance
        self._log_group_cache: Dict[str, ResolvedLambda] = {}
        self._queue_url_cache: Dict[str, str] = {}

        # Validate credentials eagerly
        self._validate_credentials()

    def _validate_credentials(self) -> None:
        """Validate AWS credentials via STS.

        Raises:
            AwsCredentialError: If credentials are expired or missing.
        """
        try:
            sts = self._session.client("sts")
            sts.get_caller_identity()
        except botocore.exceptions.ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in ("ExpiredToken", "ExpiredTokenException"):
                profile_flag = (
                    f" --profile {self._profile_name}" if self._profile_name else ""
                )
                raise AwsCredentialError(
                    f"AWS SSO token has expired. Please run:\n"
                    f"  aws sso login{profile_flag}\n"
                    f"Then retry the command."
                ) from exc
            raise AwsCredentialError(f"AWS credential error: {exc}") from exc
        except botocore.exceptions.NoCredentialsError as exc:
            profile_hint = (
                f"Ensure profile '{self._profile_name}' is configured correctly."
                if self._profile_name
                else "No AWS credentials found. Configure a profile with: aws configure"
            )
            raise AwsCredentialError(profile_hint) from exc

    # ------------------------------------------------------------------
    # Retry helper
    # ------------------------------------------------------------------

    @staticmethod
    def _retry_with_backoff(func, *args, max_retries=_MAX_RETRIES, **kwargs):
        """Execute *func* with exponential backoff on throttling errors.

        Retries up to *max_retries* times when the API returns a
        ``Throttling`` error code.
        """
        for attempt in range(max_retries + 1):
            try:
                return func(*args, **kwargs)
            except botocore.exceptions.ClientError as exc:
                error_code = exc.response.get("Error", {}).get("Code", "")
                if error_code == "Throttling" and attempt < max_retries:
                    wait = _BASE_BACKOFF_SECONDS * (2**attempt)
                    logger.warning(
                        "Throttled by AWS API, retrying in %.1fs (attempt %d/%d)",
                        wait,
                        attempt + 1,
                        max_retries,
                    )
                    time.sleep(wait)
                else:
                    raise

    # ------------------------------------------------------------------
    # SSM-based Lambda resolution
    # ------------------------------------------------------------------

    def resolve_lambda_functions_from_ssm(
        self,
        ssm_namespace: str,
    ) -> Dict[str, str]:
        """Resolve actual Lambda function names from SSM Parameter Store.

        cdk-factory exports Lambda function names to SSM at:
        ``/{ssm_namespace}/{lambda-name}/function-name``

        This method queries all parameters under the namespace and
        returns a mapping from config Lambda name to actual deployed
        function name.

        Args:
            ssm_namespace: The SSM namespace prefix
                (e.g. ``"aplos-nca-saas/development/lambda"``).

        Returns:
            Mapping from config Lambda name to actual function name.
        """
        prefix = f"/{ssm_namespace}/"
        logger.info("Resolving Lambda functions from SSM path: %s", prefix)

        name_map: Dict[str, str] = {}

        try:
            paginator_params: Dict[str, Any] = {
                "Path": prefix,
                "Recursive": True,
                "WithDecryption": False,
            }

            while True:
                response = self._retry_with_backoff(
                    self._ssm_client.get_parameters_by_path,
                    **paginator_params,
                )

                for param in response.get("Parameters", []):
                    param_name = param.get("Name", "")
                    param_value = param.get("Value", "")

                    # We want the /function-name parameters
                    if param_name.endswith("/function-name"):
                        # Extract the lambda config name from the path
                        # e.g. /aplos-nca-saas/development/lambda/file-system-archive/function-name
                        #   → file-system-archive
                        parts = param_name.split("/")
                        if len(parts) >= 2:
                            lambda_config_name = parts[-2]
                            name_map[lambda_config_name] = param_value
                            logger.debug(
                                "SSM resolved: %s → %s",
                                lambda_config_name,
                                param_value,
                            )

                next_token = response.get("NextToken")
                if not next_token:
                    break
                paginator_params["NextToken"] = next_token

        except botocore.exceptions.ClientError as exc:
            logger.warning("Failed to query SSM parameters at '%s': %s", prefix, exc)

        logger.info("Resolved %d Lambda functions from SSM", len(name_map))
        return name_map

    # ------------------------------------------------------------------
    # Log group resolution
    # ------------------------------------------------------------------

    def resolve_log_groups(
        self,
        graph: ServiceGraph,
        ssm_namespace: Optional[str] = None,
    ) -> Dict[str, ResolvedLambda]:
        """Resolve CloudWatch log groups for all Lambdas in the graph.

        When *ssm_namespace* is provided, first resolves actual Lambda
        function names from SSM Parameter Store, then uses those names
        to find CloudWatch log groups. This handles CDK auto-generated
        names with hash suffixes.

        When *ssm_namespace* is ``None``, falls back to searching
        CloudWatch directly using the config Lambda name as a prefix.

        Results are cached in-memory for the lifetime of this instance.

        Args:
            graph: The service graph containing Lambda nodes.
            ssm_namespace: Optional SSM namespace prefix
                (e.g. ``"aplos-nca-saas/development/lambda"``).

        Returns:
            Mapping from Lambda name to :class:`ResolvedLambda`.
        """
        # Step 1: Resolve actual function names from SSM if namespace provided
        ssm_name_map: Dict[str, str] = {}
        if ssm_namespace:
            ssm_name_map = self.resolve_lambda_functions_from_ssm(ssm_namespace)

        resolved: Dict[str, ResolvedLambda] = {}

        for lambda_name, node in graph.nodes.items():
            # Return cached result if available
            if lambda_name in self._log_group_cache:
                resolved[lambda_name] = self._log_group_cache[lambda_name]
                continue

            # Determine the actual function name to search for
            actual_function_name = ssm_name_map.get(lambda_name)

            if actual_function_name:
                # Use the exact function name from SSM
                prefix = f"/aws/lambda/{actual_function_name}"
            else:
                # Fall back to config name prefix search
                prefix = f"/aws/lambda/{lambda_name}"

            log_group, stored_bytes = self._find_best_log_group(prefix)

            resolved_lambda = ResolvedLambda(
                name=lambda_name,
                log_group=log_group,
                log_group_stored_bytes=stored_bytes,
                unresolved=log_group is None,
            )

            if log_group is None:
                logger.warning(
                    "No log group found for Lambda '%s' (searched prefix: %s)",
                    lambda_name,
                    prefix,
                )

            # Cache the result
            self._log_group_cache[lambda_name] = resolved_lambda
            resolved[lambda_name] = resolved_lambda

        return resolved

    def _find_best_log_group(self, prefix: str) -> tuple:
        """Query CloudWatch for log groups matching *prefix*.

        Returns:
            Tuple of (log_group_name, stored_bytes) for the best match,
            or (None, 0) if no match found.
        """
        try:
            candidates = self._describe_log_groups_with_prefix(prefix)
        except botocore.exceptions.ClientError as exc:
            logger.warning(
                "Failed to query log groups with prefix '%s': %s", prefix, exc
            )
            return None, 0

        if not candidates:
            return None, 0

        return select_best_log_group(candidates)

    def _describe_log_groups_with_prefix(self, prefix: str) -> List[Dict[str, Any]]:
        """Paginate through ``describe_log_groups`` for the given prefix.

        Returns:
            List of log group dicts from the CloudWatch API.
        """
        all_groups: List[Dict[str, Any]] = []
        paginator_params: Dict[str, Any] = {
            "logGroupNamePrefix": prefix,
        }

        while True:
            response = self._retry_with_backoff(
                self._logs_client.describe_log_groups,
                **paginator_params,
            )
            all_groups.extend(response.get("logGroups", []))

            next_token = response.get("nextToken")
            if not next_token:
                break
            paginator_params["nextToken"] = next_token

        return all_groups

    # ------------------------------------------------------------------
    # Queue URL resolution
    # ------------------------------------------------------------------

    def resolve_queue_urls(
        self,
        graph: ServiceGraph,
    ) -> Dict[str, str]:
        """Resolve SQS queue URLs for all queues in the graph.

        Collects all unique queue names from graph edges (including DLQ
        queues) and resolves each to a full SQS URL using the
        ``get_queue_url`` API.

        Args:
            graph: The service graph containing queue edges.

        Returns:
            Mapping from queue_name to queue_url.
        """
        # Collect all unique queue names from edges and DLQ map
        queue_names: set = set()
        for edge in graph.edges:
            queue_names.add(edge.queue_name)
        for primary_queue, dlq_queue in graph.dlq_map.items():
            queue_names.add(primary_queue)
            queue_names.add(dlq_queue)

        resolved: Dict[str, str] = {}
        for queue_name in sorted(queue_names):
            # Return cached result if available
            if queue_name in self._queue_url_cache:
                resolved[queue_name] = self._queue_url_cache[queue_name]
                continue

            url = self._resolve_single_queue_url(queue_name)
            if url is not None:
                self._queue_url_cache[queue_name] = url
                resolved[queue_name] = url

        return resolved

    def _resolve_single_queue_url(self, queue_name: str) -> Optional[str]:
        """Resolve a single SQS queue URL by name.

        Returns:
            The queue URL, or ``None`` if the queue cannot be found.
        """
        try:
            response = self._retry_with_backoff(
                self._sqs_client.get_queue_url,
                QueueName=queue_name,
            )
            return response.get("QueueUrl")
        except botocore.exceptions.ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code == "AWS.SimpleQueueService.NonExistentQueue":
                logger.warning("SQS queue not found: %s", queue_name)
            elif error_code == "AccessDenied":
                logger.warning(
                    "Access denied when resolving SQS queue '%s', skipping",
                    queue_name,
                )
            else:
                logger.warning("Failed to resolve SQS queue '%s': %s", queue_name, exc)
            return None

    # ------------------------------------------------------------------
    # Queue attributes
    # ------------------------------------------------------------------

    def get_queue_attributes(
        self,
        queue_url: str,
    ) -> Dict[str, Any]:
        """Get SQS queue attributes.

        Retrieves ``ApproximateNumberOfMessages``,
        ``ApproximateNumberOfMessagesNotVisible``,
        ``ApproximateNumberOfMessagesDelayed``, and
        ``RedrivePolicy`` attributes.

        Args:
            queue_url: The full SQS queue URL.

        Returns:
            Dict of queue attribute name → value.
        """
        try:
            response = self._retry_with_backoff(
                self._sqs_client.get_queue_attributes,
                QueueUrl=queue_url,
                AttributeNames=[
                    "ApproximateNumberOfMessages",
                    "ApproximateNumberOfMessagesNotVisible",
                    "ApproximateNumberOfMessagesDelayed",
                    "RedrivePolicy",
                ],
            )
            return response.get("Attributes", {})
        except botocore.exceptions.ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code == "AccessDenied":
                logger.warning(
                    "Access denied when getting attributes for queue '%s'",
                    queue_url,
                )
            else:
                logger.warning(
                    "Failed to get attributes for queue '%s': %s", queue_url, exc
                )
            return {}

    # ------------------------------------------------------------------
    # Service map generation
    # ------------------------------------------------------------------

    def generate_service_map(
        self,
        graph: ServiceGraph,
        resolved: Dict[str, ResolvedLambda],
        environment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a ``workflow_service_map.json``-compatible dict.

        Produces output matching the existing schema used by
        SmartFlowService and summary_trace tools.

        Args:
            graph: The service graph.
            resolved: Mapping from Lambda name to ResolvedLambda
                (from :meth:`resolve_log_groups`).
            environment: Optional environment name (e.g.
                ``"development-dev"``) used as the key in the
                ``log_groups`` dict for each service. When ``None``,
                the key ``"resolved"`` is used.

        Returns:
            A dict matching the ``workflow_service_map.json`` schema.
        """
        services: Dict[str, Any] = {}

        for lambda_name, node in graph.nodes.items():
            # Derive a short service key from the Lambda name
            service_key = _derive_service_key(lambda_name)

            resolved_lambda = resolved.get(
                lambda_name, ResolvedLambda(name=lambda_name)
            )

            # Build log_groups dict if resolved
            log_groups: Dict[str, str] = {}
            if resolved_lambda.log_group:
                log_group_key = environment if environment else "resolved"
                log_groups[log_group_key] = resolved_lambda.log_group

            # Determine emits_to_queue and consumes_from_queue
            emits_to_queue: Optional[str] = None
            if node.producer_queues:
                emits_to_queue = node.producer_queues[0]

            consumes_from_queue: Optional[str] = None
            if node.consumer_queue:
                consumes_from_queue = node.consumer_queue

            # Determine next_services from graph edges
            downstream = graph.get_downstream(lambda_name)
            next_services = [_derive_service_key(d) for d in downstream]

            service_entry: Dict[str, Any] = {
                "description": node.description,
                "timeout_seconds": node.timeout,
                "lambda_name_template": lambda_name,
                "cdk_function_name": lambda_name,
                "log_groups": log_groups,
                "next_services": next_services,
            }

            # Only include queue fields when they have values
            if emits_to_queue:
                service_entry["emits_to_queue"] = emits_to_queue
            if consumes_from_queue:
                service_entry["consumes_from_queue"] = consumes_from_queue

            # Add log_group_pattern for pattern-based matching
            service_entry["log_group_pattern"] = f"/aws/lambda/*{lambda_name}*"

            services[service_key] = service_entry

        # Derive execution flows from graph
        raw_flows = graph.derive_execution_flows()
        execution_flows: Dict[str, Any] = {}
        for flow_name, flow_lambdas in raw_flows.items():
            execution_flows[flow_name] = {
                "description": f"Auto-derived flow: {flow_name}",
                "typical_flow": [_derive_service_key(l) for l in flow_lambdas],
            }

        return {
            "description": "Auto-generated from CDK configuration",
            "version": "2.0.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "cdk-factory introspection",
            "services": services,
            "execution_flows": execution_flows,
        }


# ======================================================================
# Pure helper functions (testable without AWS)
# ======================================================================


def select_best_log_group(
    candidates: List[Dict[str, Any]],
) -> tuple:
    """Select the log group with the highest ``storedBytes``.

    Args:
        candidates: Non-empty list of log group dicts from the
            CloudWatch ``describe_log_groups`` API. Each dict should
            have ``logGroupName`` and ``storedBytes`` keys.

    Returns:
        Tuple of (log_group_name, stored_bytes) for the best candidate.
    """
    if not candidates:
        return None, 0

    best = max(candidates, key=lambda g: g.get("storedBytes", 0))
    return best.get("logGroupName"), best.get("storedBytes", 0)


def _derive_service_key(lambda_name: str) -> str:
    """Derive a short service key from a Lambda function name.

    Strips common prefixes like ``analysis-`` and ``workflow-`` and
    converts hyphens to underscores to produce a key matching the
    style used in ``workflow_service_map.json``.

    Examples:
        >>> _derive_service_key("analysis-admission-handler")
        'admission_handler'
        >>> _derive_service_key("workflow-step-processor")
        'step_processor'
        >>> _derive_service_key("analysis-data-cleaning")
        'data_cleaning'
    """
    key = lambda_name

    # Strip common prefixes
    for prefix in ("analysis-", "workflow-"):
        if key.startswith(prefix):
            key = key[len(prefix) :]
            break

    # Convert hyphens to underscores
    key = key.replace("-", "_")

    return key
