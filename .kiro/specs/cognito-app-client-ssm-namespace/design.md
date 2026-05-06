# Design Document: Per-Client SSM Namespace for Cognito App Clients

## Overview

This feature extends the Cognito CDK stack to support an optional `ssm_namespace` field on each app client configuration entry. When specified, the client's SSM parameter exports (client ID, secret ARN) are written under the client-specific namespace instead of the pool-level namespace. This allows multiple consuming applications sharing a single Cognito User Pool to discover their credentials under isolated, application-specific SSM paths.

The change is additive and backward-compatible: existing configurations without `ssm_namespace` on app clients continue to behave identically.

## Architecture

The feature modifies two layers of the existing Cognito stack:

1. **Configuration Layer** (`CognitoConfig`): Exposes the optional `ssm_namespace` field from each app client dict entry.
2. **Stack Layer** (`CognitoStack`): During SSM export, resolves the effective namespace per client — using the client-level namespace when present, falling back to the pool-level namespace.

```mermaid
flowchart TD
    A[Stack Config JSON] --> B[CognitoConfig Parser]
    B --> C{app_client has ssm_namespace?}
    C -->|Yes| D[Use Client_Level_Namespace]
    C -->|No| E[Use Pool_Level_Namespace]
    D --> F[Export SSM: /{client_ns}/app_client_{safe_name}_id]
    E --> G[Export SSM: /{pool_ns}/app_client_{safe_name}_id]
    
    H[Pool-level resources] --> I[Always use Pool_Level_Namespace]
    I --> J[Export SSM: /{pool_ns}/user_pool_id, etc.]
```

## Components and Interfaces

### CognitoConfig Changes

No new class is needed. The existing `app_clients` property already returns raw dicts. A helper method will be added to extract the `ssm_namespace` from a client config dict:

```python
# In CognitoConfig or as a utility used by CognitoStack
def get_client_ssm_namespace(client_config: dict) -> str | None:
    """Return the client-level SSM namespace, or None if not specified."""
    return client_config.get("ssm_namespace")
```

### CognitoStack Changes

The `_export_ssm_parameters` and `_store_client_secret_in_secrets_manager` methods are modified to resolve the effective namespace per client:

```python
def _resolve_client_namespace(self, client_config: dict) -> str:
    """
    Resolve the effective SSM namespace for an app client.
    Returns client-level namespace if specified, otherwise pool-level namespace.
    Raises ValueError if client namespace is an empty string.
    """
    client_ns = client_config.get("ssm_namespace")
    if client_ns is not None:
        if not client_ns.strip():
            raise ValueError(
                f"App client '{client_config.get('name')}': "
                f"'ssm_namespace' must be a non-empty string or omitted entirely."
            )
        return client_ns
    return self.stack_config.ssm_namespace
```

### SSM Path Construction

A pure function for building the SSM parameter path:

```python
def build_client_ssm_path(namespace: str, safe_client_name: str, attribute: str) -> str:
    """Build the full SSM parameter path for a client attribute."""
    return f"/{namespace}/app_client_{safe_client_name}_{attribute}"
```

### Safe Client Name Transformation

Existing logic (already in the codebase):

```python
def make_safe_client_name(client_name: str) -> str:
    """Sanitize client name for SSM path usage."""
    return client_name.replace("-", "_").replace(" ", "_")
```

### Validation

When `ssm.auto_export` is `false` and no explicit exports are configured, but a client specifies `ssm_namespace`, the stack logs a warning:

```python
logger.warning(
    f"App client '{client_name}' has 'ssm_namespace' configured but "
    f"ssm.auto_export is disabled and no explicit exports are configured. "
    f"The client-level namespace will be ignored."
)
```

## Data Models

### App Client Configuration Schema (JSON)

```json
{
  "app_clients": [
    {
      "name": "acme-web-app",
      "ssm_namespace": "acme-web/beta/auth",
      "generate_secret": false,
      "auth_flows": { "user_srp": true }
    },
    {
      "name": "admin-portal",
      "generate_secret": true,
      "auth_flows": { "user_srp": true }
    }
  ]
}
```

The `ssm_namespace` field:
- Type: `string | undefined`
- Optional: yes (no default value)
- Constraints: must be non-empty if present
- Effect: overrides pool-level `ssm.namespace` for that client's SSM exports

### SSM Parameter Outputs

| Client Config | Exported Path |
|---|---|
| `ssm_namespace: "acme-web/beta/auth"`, name: `acme-web-app` | `/acme-web/beta/auth/app_client_nca_web_app_id` |
| No `ssm_namespace`, name: `admin-portal`, pool ns: `acme/beta/cognito` | `/acme/beta/cognito/app_client_admin_portal_id` |

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Client namespace config parsing

*For any* app client configuration dict, if `ssm_namespace` is present as a non-empty string, the parsed value SHALL equal the input string; if `ssm_namespace` is absent, the parsed value SHALL be `None`.

**Validates: Requirements 1.1, 1.2, 1.3, 5.2**

### Property 2: SSM path resolution uses correct namespace

*For any* app client with a valid name and an optional `ssm_namespace`, the resolved SSM parameter path SHALL use the client-level namespace when `ssm_namespace` is a non-empty string, and SHALL use the pool-level namespace when `ssm_namespace` is absent or `None`.

**Validates: Requirements 2.1, 2.3, 4.1, 4.2**

### Property 3: Safe client name transformation is idempotent

*For any* client name string, applying the safe-name transformation (replacing hyphens and spaces with underscores) twice SHALL produce the same result as applying it once.

**Validates: Requirements 2.1, 2.2, 2.3**

### Property 4: Empty string namespace rejection

*For any* app client configuration where `ssm_namespace` is a string composed entirely of whitespace (including empty string), the namespace resolution SHALL raise a `ValueError`.

**Validates: Requirements 6.2**

## Error Handling

| Condition | Behavior |
|---|---|
| `ssm_namespace` is empty string or whitespace-only | Raise `ValueError` with descriptive message naming the client |
| `ssm_namespace` set but `auto_export` is false and no explicit exports | Log warning, skip client-level export |
| `ssm.namespace` (pool-level) missing when auto_export is true and client has no `ssm_namespace` | Raise `ValueError` (existing behavior, unchanged) |
| Client name is missing | Raise `ValueError` (existing behavior, unchanged) |

## Testing Strategy

### Property-Based Tests (using Hypothesis)

Each correctness property is implemented as a property-based test with minimum 100 iterations:

1. **Config parsing property**: Generate random dicts with/without `ssm_namespace` keys, verify parsing behavior.
2. **Path resolution property**: Generate random (client_name, client_namespace, pool_namespace) tuples, verify correct namespace selection.
3. **Safe name idempotence**: Generate random client name strings, verify `f(f(x)) == f(x)`.
4. **Empty namespace rejection**: Generate whitespace-only strings, verify `ValueError` is raised.

Tag format: `Feature: cognito-app-client-ssm-namespace, Property {N}: {description}`

Library: `hypothesis` (already available in the Python ecosystem for this project)

Configuration: Each test runs with `@settings(max_examples=100)`.

### Unit Tests (example-based)

- Verify warning is logged when `ssm_namespace` is set but `auto_export` is false (Requirement 6.1)
- Verify pool-level parameters (`user_pool_id`, `user_pool_arn`, `user_pool_name`) are exported under pool namespace even when clients have custom namespaces (Requirement 3.1)
- Verify backward compatibility: stack with no `ssm_namespace` on any client produces identical output to current behavior (Requirement 5.1)

### Integration Tests (CDK assertion-based)

- Synthesize a stack with mixed client namespaces and assert correct SSM `AWS::SSM::Parameter` resources in the CloudFormation template
- Verify no duplicate parameters are created
- Verify secret ARN export path when `generate_secret` is true with a client namespace (Requirement 2.2)
