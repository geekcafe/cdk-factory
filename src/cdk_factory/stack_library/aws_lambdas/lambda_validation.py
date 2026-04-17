"""
Lambda Validation Functions for CDK-Factory

Standalone validation functions for Lambda configurations.
These are used at synth time to catch configuration errors early.
"""

from typing import List, Set


# Known string-based permission identifiers supported by PolicyDocuments.
# Dict-based permissions (with explicit actions/resources) are always valid.
KNOWN_PERMISSION_STRINGS: Set[str] = {
    "dynamodb_read",
    "dynamodb_write",
    "dynamodb_delete",
    "dynamodb_app_read",
    "dynamodb_app_write",
    "dynamodb_app_delete",
    "audit_logging",
    "s3_read_workload",
    "s3_write_workload",
    "s3_delete_workload",
    "s3_read_transient",
    "s3_write_transient",
    "dynamodb_read_transient",
    "dynamodb_write_transient",
    "s3_read_upload",
    "s3_write_upload",
    "s3_read_upload_v3",
    "s3_write_upload_v3",
    "parameter_store_read",
    "cognito_user_pool_read",
    "cognito_user_pool_client_read",
    "cognito_user_pool_group_read",
    "cognito_admin",
}


def validate_permission_strings(
    permissions: List[str | dict],
    lambda_name: str,
) -> None:
    """Validate that all string-based permission identifiers are known.

    Dict-based permissions (with explicit actions/resources) are always
    considered valid since they define their own IAM statements.

    Args:
        permissions: List of permission entries — either string identifiers
            or dict-based inline permission definitions.
        lambda_name: Name of the Lambda function (for error messages).

    Raises:
        ValueError: If any string permission is not in KNOWN_PERMISSION_STRINGS.
    """
    unknown: List[str] = []

    for perm in permissions:
        if isinstance(perm, str) and perm not in KNOWN_PERMISSION_STRINGS:
            unknown.append(perm)

    if unknown:
        raise ValueError(
            f"Unknown permission(s) {unknown} on Lambda '{lambda_name}'. "
            f"Valid string permissions: {sorted(KNOWN_PERMISSION_STRINGS)}"
        )
