"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Hashable


def permission_key(entry: dict | str) -> Hashable:
    """Extract a hashable key from any permission format for deduplication.

    Supported formats:
        - Structured DynamoDB: {"dynamodb": "read", "table": "t"} → ("dynamodb", "read", "t")
        - Structured S3: {"s3": "write", "bucket": "b"} → ("s3", "write", "b")
        - String: "parameter_store_read" → "parameter_store_read"
        - Inline IAM: {"actions": [...], "resources": [...]} → (frozenset(actions), frozenset(resources))
    """
    if isinstance(entry, str):
        return entry

    if isinstance(entry, dict):
        # Structured DynamoDB
        if "dynamodb" in entry:
            return ("dynamodb", entry["dynamodb"], entry.get("table", ""))

        # Structured S3
        if "s3" in entry:
            return ("s3", entry["s3"], entry.get("bucket", ""))

        # Structured Parameter Store
        if "parameter_store" in entry:
            return ("parameter_store", entry["parameter_store"], entry.get("path", ""))

        # Inline IAM
        if "actions" in entry and "resources" in entry:
            return (
                frozenset(entry["actions"]),
                frozenset(entry["resources"]),
            )

    # Fallback: return the entry itself (works for strings, may not be ideal for dicts)
    return str(entry)


def merge_permissions(
    resource_permissions: list[dict | str],
    stack_permissions: list[dict | str],
) -> list[dict | str]:
    """Return resource_permissions + stack_permissions entries that don't match any resource entry.

    Two permissions "match" when they share the same key as computed by ``permission_key()``.
    Resource-level entries are never modified or removed.
    """
    resource_keys = {permission_key(p) for p in resource_permissions}
    merged = list(resource_permissions)
    for sp in stack_permissions:
        if permission_key(sp) not in resource_keys:
            merged.append(sp)
    return merged


def merge_environment_variables(
    resource_env_vars: list[dict],
    stack_env_vars: list[dict],
) -> list[dict]:
    """Return resource_env_vars + stack_env_vars entries whose ``name`` doesn't exist in resource_env_vars.

    Matching is based on the ``name`` field of each entry.
    Resource-level entries are never modified or removed.
    """
    resource_names = {ev["name"] for ev in resource_env_vars}
    merged = list(resource_env_vars)
    for sev in stack_env_vars:
        if sev["name"] not in resource_names:
            merged.append(sev)
    return merged


def merge_stack_defaults_into_resources(
    resources: list[dict],
    additional_permissions: list[dict | str],
    additional_environment_variables: list[dict],
) -> None:
    """Mutate each resource dict in-place, merging stack-level defaults.

    Skips resources where ``skip_stack_defaults`` is ``true``.
    Initializes missing ``permissions`` or ``environment_variables`` keys to ``[]`` before merging.
    """
    if not additional_permissions and not additional_environment_variables:
        return

    for resource in resources:
        if resource.get("skip_stack_defaults") is True:
            continue

        if additional_permissions:
            resource_perms = resource.get("permissions", [])
            resource["permissions"] = merge_permissions(
                resource_perms, additional_permissions
            )

        if additional_environment_variables:
            resource_env = resource.get("environment_variables", [])
            resource["environment_variables"] = merge_environment_variables(
                resource_env, additional_environment_variables
            )
