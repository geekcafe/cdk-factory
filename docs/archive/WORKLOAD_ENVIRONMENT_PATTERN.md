# Workload-Level Environment Pattern

## Architecture Principle

**One Workload Deployment = One Environment**

Each workload deployment configuration represents a **single environment**. This eliminates confusion, prevents cross-environment contamination, and makes deployments explicit and predictable.

## Configuration Structure

### ✅ Best Practice (Recommended)

Define `environment` at the **workload level**:

```json
{
  "workload": {
    "name": "my-application",
    "environment": "dev",  ← Single source of truth
    "devops": {
      "account": "123456789012",
      "region": "us-east-1"
    }
  },
  "stacks": [...]
}
```

### 🔄 Backward Compatible (Legacy)

For backward compatibility, these locations are still supported:

```json
{
  "workload": {
    "name": "my-application",
    "deployment": {
      "environment": "dev"  ← Legacy location (still works)
    }
  }
}
```

Or via environment variable:
```bash
export ENVIRONMENT=dev
```

## Why This Pattern?

### Problem: Old Multi-Environment Pattern

The old pattern allowed multiple environments in one workload config:

```json
{
  "workload": {...},
  "environments": {
    "dev": {...},
    "prod": {...}
  }
}
```

**Issues:**
- ❌ Generated multiple `cdk.out` builds (wasteful)
- ❌ Unclear which environment was being deployed
- ❌ Risk of accidentally deploying wrong environment
- ❌ Environment scattered across config files

### Solution: Single-Environment Workload

Each workload configuration = one environment:

```
Template Files (reusable)
  ├── config-template.json
  └── stacks-template.json
        ↓
Workload Instances (environment-specific)
  ├── workload-dev.json    (environment: "dev")
  ├── workload-staging.json (environment: "staging")
  └── workload-prod.json   (environment: "prod")
```

**Benefits:**
- ✅ **Explicit**: Clear which environment you're deploying
- ✅ **Safe**: Can't accidentally use dev resources in prod
- ✅ **Efficient**: One `cdk.out` build per deployment
- ✅ **Simple**: Environment in one obvious location
- ✅ **Template reuse**: Same config structure, different values

## Implementation Details

### Priority Order

The system checks for environment in this order:

1. `workload["environment"]` - **STANDARD** (preferred)
2. `workload["deployment"]["environment"]` - Legacy (backward compat)
3. `deployment_config["environment"]` - Legacy (backward compat)
4. `config["ssm"]["environment"]` - Legacy (backward compat)
5. `${ENVIRONMENT}` - Environment variable (with validation)

**No default to 'dev'** - The system **fails explicitly** if no environment is found.

### Error Messages

If environment is missing:

```
ValueError: Environment must be explicitly specified at workload level.
Cannot default to 'dev' as this may cause cross-environment resource contamination.
Best practice: Add 'environment' to your workload config:
  {"workload": {"name": "...", "environment": "dev|prod"}}
```

If environment variable is not set:

```
ValueError: Environment variable 'ENVIRONMENT' is not set.
Cannot default to 'dev' as this may cause cross-environment contamination.
Best practice: Set 'environment' at workload level in your config.
Alternatively, set the ENVIRONMENT environment variable.
```

## Migration Guide

### For New Projects

Start with workload-level environment from day one:

```json
{
  "workload": {
    "name": "my-new-app",
    "environment": "dev"
  }
}
```

### For Existing Projects

You have two options:

#### Option 1: Keep Current Pattern (Backward Compatible)

If you're currently using `deployment.environment` or environment variables, **no changes required**. The system supports backward compatibility.

#### Option 2: Migrate to Best Practice (Recommended)

1. Move environment to workload level:

**Before:**
```json
{
  "workload": {
    "name": "my-app",
    "deployment": {
      "environment": "dev"
    }
  }
}
```

**After:**
```json
{
  "workload": {
    "name": "my-app",
    "environment": "dev"
  }
}
```

2. Remove from other locations (optional cleanup)
3. Test deployment
4. Update documentation

## Examples

### Example 1: Static Website (Dev)

**File:** `workload-dev.json`

```json
{
  "workload": {
    "name": "my-website",
    "environment": "dev",
    "devops": {
      "account": "123456789012",
      "region": "us-east-1"
    }
  },
  "stacks": [
    {
      "name": "my-website-dev-site",
      "module": "static_website_stack",
      "enabled": true
    }
  ]
}
```

### Example 2: Static Website (Prod)

**File:** `workload-prod.json`

```json
{
  "workload": {
    "name": "my-website",
    "environment": "prod",  ← Only difference!
    "devops": {
      "account": "987654321098",  ← Different account
      "region": "us-east-1"
    }
  },
  "stacks": [
    {
      "name": "my-website-prod-site",
      "module": "static_website_stack",
      "enabled": true
    }
  ]
}
```

### Example 3: With Lambda@Edge

```json
{
  "workload": {
    "name": "gated-site",
    "environment": "dev",
    "devops": {...}
  },
  "stacks": [
    {
      "name": "gated-site-dev-ip-gate",
      "module": "lambda_edge_library_module",
      "lambda_edge": {
        "name": "gated-site-dev-ip-gate",
        "ssm_exports": {
          "function_version_arn": "/dev/gated-site/lambda-edge/version-arn"
        }
      }
    },
    {
      "name": "gated-site-dev-site",
      "module": "static_website_stack",
      "dependencies": ["gated-site-dev-ip-gate"],  ← Explicit dependency
      "cloudfront": {
        "enable_ip_gating": true
      }
    }
  ]
}
```

## Safety Features

### No Dangerous Defaults

The system **never defaults to 'dev'** to prevent cross-environment contamination:

```python
# ❌ OLD (DANGEROUS)
environment = config.get("environment", "dev")  # Prod might use dev!

# ✅ NEW (SAFE)
environment = workload_config.get("environment")
if not environment:
    raise ValueError("Environment must be explicitly set")
```

### Explicit Failures

If environment is missing, the deployment **fails immediately** with a clear error message, preventing:

- ❌ Prod using dev Lambda functions
- ❌ Wrong SSM parameters
- ❌ Cross-environment contamination
- ❌ Silent configuration errors

### Stack Dependencies

Combined with explicit stack dependencies, ensures correct deployment order:

```json
{
  "stacks": [
    {
      "name": "lambda-edge-stack",
      "dependencies": []
    },
    {
      "name": "cloudfront-stack",
      "dependencies": ["lambda-edge-stack"]  ← Enforced order
    }
  ]
}
```

## Related Patterns

- **Stack Dependencies**: `docs/STACK_DEPENDENCIES.md`
- **SSM Parameter Validation**: `docs/SSM_PARAMETER_VALIDATION.md`
- **Lambda@Edge Deployment**: `docs/LAMBDA_EDGE_PATTERN.md`

## Version History

- **v0.13.8**: Introduced workload-level environment pattern with backward compatibility
- **v0.13.7**: Added SSM parameter validation to prevent missing parameters
- **v0.13.6**: Fixed Lambda@Edge region prefix issue

## Summary

**Architecture:** One workload deployment = One environment

**Best Practice:**
```json
{"workload": {"name": "...", "environment": "dev|prod"}}
```

**Benefits:**
- ✅ Explicit, clear, and self-documenting
- ✅ Safe - no cross-environment contamination
- ✅ Simple - single source of truth
- ✅ Efficient - one build per deployment
- ✅ Template reuse - same structure, different values

**Migration:** Fully backward compatible - migrate at your own pace!
