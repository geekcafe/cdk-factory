"""SSM version publisher utility.

Provides functions to resolve SSM parameter names from templates and
publish version strings to AWS Systems Manager Parameter Store with
retry logic for transient errors.
"""

from __future__ import annotations

import random
import time
from typing import Any, Dict

from botocore.exceptions import ClientError

from cdk_factory.pipeline.conventions.template_render import render_template


def resolve_version_parameter_name(
    *,
    template: str,
    values: Dict[str, Any],
) -> str:
    """Resolve an SSM parameter name by rendering a template with values.

    Args:
        template: A string containing ``{{PLACEHOLDER}}`` patterns.
        values: A mapping of placeholder names to replacement values.

    Returns:
        The resolved parameter name (must start with ``/``).

    Raises:
        ValueError: If the resolved name does not start with ``/``.
    """
    name = render_template(template, values).strip()
    if not name.startswith("/"):
        raise ValueError("SSM parameter name must start with '/'")
    return name


def put_parameter_with_retry(
    *,
    ssm_client: Any,
    name: str,
    value: str,
    max_retries: int = 8,
) -> None:
    """Write an SSM parameter with exponential backoff retry on transient errors.

    Retries on ``ThrottlingException`` and ``TooManyUpdates`` error codes
    using exponential backoff with jitter, capped at 60 seconds.

    Args:
        ssm_client: A boto3 SSM client instance.
        name: The SSM parameter name.
        value: The parameter value to write.
        max_retries: Maximum number of retry attempts (default 8).

    Raises:
        ClientError: If a non-retryable error occurs or retries are exhausted.
    """
    retry_count = 0
    while True:
        try:
            ssm_client.put_parameter(
                Name=name,
                Value=value,
                Type="String",
                Overwrite=True,
            )
            return
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if (
                code in ("ThrottlingException", "TooManyUpdates")
                and retry_count < max_retries
            ):
                retry_count += 1
                base = min(2**retry_count, 60)
                sleep_time = base + random.uniform(0, base * 0.5)
                time.sleep(sleep_time)
            else:
                raise


def publish_version_to_ssm(
    *,
    ssm_client: Any,
    version: str,
    parameter_name_template: str,
    template_values: Dict[str, Any],
    max_retries: int = 8,
) -> str:
    """Publish a version string to SSM Parameter Store.

    Resolves the parameter name from the template and values, then writes
    the version using :func:`put_parameter_with_retry`.

    Args:
        ssm_client: A boto3 SSM client instance.
        version: The version string to publish.
        parameter_name_template: Template with ``{{PLACEHOLDER}}`` patterns.
        template_values: Values to substitute into the template.
        max_retries: Maximum retry attempts for the put operation.

    Returns:
        The resolved SSM parameter name that was written to.
    """
    name = resolve_version_parameter_name(
        template=parameter_name_template,
        values=template_values,
    )
    put_parameter_with_retry(
        ssm_client=ssm_client,
        name=name,
        value=version,
        max_retries=max_retries,
    )
    return name
