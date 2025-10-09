# SSM Export Configuration Bug Fix

## The Problem

The documentation incorrectly showed this pattern:

```json
"ssm": {
  "enabled": true,
  "workload": "my-app",
  "environment": "prod",
  "exports": {
    "enabled": true  // ❌ WRONG - causes AttributeError
  }
}
```

**Error:** `AttributeError: 'bool' object has no attribute 'startswith'`

**Root Cause:** The `exports` field expects attribute names mapped to paths (or "auto"), not a nested `enabled` field. The code tried to call `true.startswith("/")` which failed.

## The Fix

### Code Fix (v0.8.0+)

The `get_parameter_path()` method now validates that `custom_path` is a string:

```python
# Before (would crash)
if custom_path and custom_path.startswith("/"):
    return custom_path

# After (safe)
if custom_path and isinstance(custom_path, str) and custom_path.startswith("/"):
    return custom_path
```

### Configuration Fix - Use One of These Patterns

#### ✅ Option 1: Use `auto_export` (Recommended)

```json
{
  "api_gateway": {
    "ssm": {
      "enabled": true,
      "auto_export": true,  // ✅ Correct - enables auto-discovery
      "workload": "my-app",
      "environment": "prod"
    }
  }
}
```

This automatically exports: `api_id`, `api_arn`, `api_url`, `root_resource_id`, `authorizer_id`

#### ✅ Option 2: Explicit Attribute Exports

```json
{
  "api_gateway": {
    "ssm": {
      "enabled": true,
      "auto_export": false,  // Disable auto-discovery
      "workload": "my-app",
      "environment": "prod",
      "exports": {
        "api_id": "auto",               // ✅ Correct - attribute name
        "api_url": "auto",
        "root_resource_id": "auto",
        "authorizer_id": "/custom/path"
      }
    }
  }
}
```

#### ✅ Option 3: Mix Auto + Explicit

```json
{
  "api_gateway": {
    "ssm": {
      "enabled": true,
      "auto_export": true,   // Auto-discover standard attributes
      "workload": "my-app",
      "environment": "prod",
      "exports": {
        "custom_attribute": "/custom/path/value"  // Add custom ones
      }
    }
  }
}
```

## Update Your geek-cafe Project

In `/Users/eric.wilson/Projects/geek-cafe/geek-cafe-web/geek-cafe-lambdas/cdk`, change:

```json
// Before (WRONG)
"exports": {
  "enabled": true
}

// After (CORRECT)
"auto_export": true
```

**Remove the entire `"exports": {...}` block** and add `"auto_export": true` at the SSM level.

## Complete Example

**Lambda Stack:**
```json
{
  "name": "my-app-prod-lambdas",
  "module": "lambda_stack",
  "ssm": {
    "enabled": true,
    "workload": "my-app",
    "environment": "prod"
  },
  "resources": [...]
}
```

**API Gateway Stack:**
```json
{
  "name": "my-app-prod-api-gateway",
  "module": "api_gateway_stack",
  "api_gateway": {
    "name": "my-app-prod-api",
    "api_type": "REST",
    "stage_name": "prod",
    "ssm": {
      "enabled": true,
      "auto_export": true,        // ✅ Export API Gateway info
      "workload": "my-app",
      "environment": "prod",
      "imports": {
        "workload": "my-app",     // Import Lambda ARNs
        "environment": "prod"
      }
    },
    "routes": [
      {
        "path": "/health",
        "method": "GET",
        "lambda_name": "my-app-prod-health"  // Auto-discovers from SSM
      }
    ]
  }
}
```

## SSM Paths Created

With `auto_export: true`, API Gateway exports:

```
/my-app/prod/api-gateway/my-app-prod-api/api-id
/my-app/prod/api-gateway/my-app-prod-api/api-arn
/my-app/prod/api-gateway/my-app-prod-api/api-url
/my-app/prod/api-gateway/my-app-prod-api/root-resource-id
/my-app/prod/api-gateway/my-app-prod-api/authorizer-id
```

Lambda stack exports:

```
/my-app/prod/lambda/my-app-prod-health/arn
/my-app/prod/lambda/my-app-prod-health/function-name
```

## Test Coverage

New tests added in `tests/unit/test_api_gateway_export_config.py`:

- ✅ Auto-export pattern validation
- ✅ Explicit exports with custom paths
- ✅ Protection against incorrect `{"enabled": true}` pattern
- ✅ Mixed auto + explicit exports
- ✅ Empty exports dict handling

Run tests: `pytest tests/unit/test_api_gateway_export_config.py -v`
