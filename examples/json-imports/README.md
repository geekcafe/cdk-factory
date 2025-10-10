# JSON Imports Example

This example demonstrates the new `__imports__` keyword introduced in CDK Factory v0.8.2.

## Overview

The `__imports__` keyword allows you to compose configuration files by importing from:
- External JSON files
- Multiple files (merged in order)
- Nested sections within the same config
- Directories of JSON files

## Example Structure

```
examples/json-imports/
├── README.md                    # This file
├── configs/
│   ├── base/
│   │   ├── lambda-defaults.json      # Base Lambda configuration
│   │   ├── api-defaults.json         # Base API Gateway configuration
│   │   └── common-env-vars.json      # Shared environment variables
│   ├── environments/
│   │   ├── dev.json                  # Development overrides
│   │   ├── staging.json              # Staging overrides
│   │   └── prod.json                 # Production overrides
│   └── stacks/
│       ├── lambda-stack-dev.json     # Dev Lambda stack
│       ├── lambda-stack-prod.json    # Prod Lambda stack
│       ├── api-gateway-dev.json      # Dev API Gateway
│       └── api-gateway-prod.json     # Prod API Gateway
└── workload.json                # Main workload config with nested references
```

## Files

### Base Configuration Files

#### `configs/base/lambda-defaults.json`
```json
{
  "runtime": "python3.13",
  "memory": 128,
  "timeout": 30,
  "architecture": "x86_64",
  "tracing_config": {
    "mode": "Active"
  }
}
```

#### `configs/base/api-defaults.json`
```json
{
  "api_type": "REST",
  "stage_name": "prod",
  "deploy_options": {
    "metrics_enabled": true,
    "tracing_enabled": true,
    "throttling_rate_limit": 1000,
    "throttling_burst_limit": 2000
  }
}
```

#### `configs/base/common-env-vars.json`
```json
[
  {"name": "AWS_REGION", "value": "us-east-1"},
  {"name": "LOG_LEVEL", "value": "INFO"},
  {"name": "POWERTOOLS_SERVICE_NAME", "value": "my-service"}
]
```

### Environment Overrides

#### `configs/environments/dev.json`
```json
{
  "memory": 256,
  "timeout": 60,
  "environment_variables": [
    {"name": "ENVIRONMENT", "value": "development"},
    {"name": "DEBUG", "value": "true"}
  ]
}
```

#### `configs/environments/prod.json`
```json
{
  "memory": 512,
  "timeout": 120,
  "reserved_concurrent_executions": 10,
  "environment_variables": [
    {"name": "ENVIRONMENT", "value": "production"},
    {"name": "DEBUG", "value": "false"}
  ]
}
```

### Stack Configurations

#### `configs/stacks/lambda-stack-dev.json`
```json
{
  "name": "my-app-dev-lambda-stack",
  "module": "lambda_stack",
  "resources": [
    {
      "__imports__": [
        "../base/lambda-defaults.json",
        "../environments/dev.json"
      ],
      "name": "data-processor",
      "handler": "processor.handle",
      "src": "./lambdas/processor",
      "environment_variables": {
        "__imports__": "../base/common-env-vars.json"
      }
    },
    {
      "__imports__": [
        "../base/lambda-defaults.json",
        "../environments/dev.json"
      ],
      "name": "api-handler",
      "handler": "api.handle",
      "src": "./lambdas/api",
      "memory": 512,
      "environment_variables": {
        "__imports__": "../base/common-env-vars.json"
      }
    }
  ]
}
```

#### `configs/stacks/lambda-stack-prod.json`
```json
{
  "name": "my-app-prod-lambda-stack",
  "module": "lambda_stack",
  "resources": [
    {
      "__imports__": [
        "../base/lambda-defaults.json",
        "../environments/prod.json"
      ],
      "name": "data-processor",
      "handler": "processor.handle",
      "src": "./lambdas/processor",
      "environment_variables": {
        "__imports__": "../base/common-env-vars.json"
      }
    },
    {
      "__imports__": [
        "../base/lambda-defaults.json",
        "../environments/prod.json"
      ],
      "name": "api-handler",
      "handler": "api.handle",
      "src": "./lambdas/api",
      "memory": 1024,
      "timeout": 300,
      "environment_variables": {
        "__imports__": "../base/common-env-vars.json"
      }
    }
  ]
}
```

### Workload Configuration with Nested References

#### `workload.json`
```json
{
  "workload": {
    "name": "my-app",
    "description": "Example app using JSON imports",
    "devops": {
      "account": "123456789012",
      "region": "us-east-1"
    },
    "defaults": {
      "lambda_config": {
        "runtime": "python3.13",
        "memory": 128,
        "timeout": 30
      },
      "api_config": {
        "api_type": "REST",
        "throttling_rate_limit": 1000
      }
    },
    "stacks": [
      {
        "__imports__": "./configs/stacks/lambda-stack-prod.json"
      },
      {
        "name": "api-gateway-stack",
        "module": "api_gateway_stack",
        "api_gateway": {
          "__imports__": "workload.defaults.api_config",
          "name": "my-api",
          "stage_name": "prod",
          "routes": [
            {
              "path": "/process",
              "method": "POST",
              "lambda_name": "data-processor"
            },
            {
              "path": "/api",
              "method": "GET",
              "lambda_name": "api-handler"
            }
          ]
        }
      }
    ]
  }
}
```

## How It Works

### 1. Simple File Import

**lambda-stack-dev.json** imports base defaults:
```json
{
  "__imports__": "../base/lambda-defaults.json",
  "name": "my-lambda"
}
```

**Resolves to:**
```json
{
  "runtime": "python3.13",
  "memory": 128,
  "timeout": 30,
  "architecture": "x86_64",
  "tracing_config": {"mode": "Active"},
  "name": "my-lambda"
}
```

### 2. Multiple File Import (Merge in Order)

```json
{
  "__imports__": [
    "../base/lambda-defaults.json",
    "../environments/prod.json"
  ],
  "handler": "index.handler"
}
```

**Resolves to:**
```json
{
  "runtime": "python3.13",
  "memory": 512,              // From prod.json (overrides base)
  "timeout": 120,             // From prod.json (overrides base)
  "architecture": "x86_64",   // From base
  "tracing_config": {"mode": "Active"},  // From base
  "reserved_concurrent_executions": 10,  // From prod.json
  "environment_variables": [...],        // From prod.json
  "handler": "index.handler"  // From current file
}
```

### 3. Nested Section Reference

```json
{
  "api_gateway": {
    "__imports__": "workload.defaults.api_config",
    "name": "my-api"
  }
}
```

Imports from the same file's `workload.defaults.api_config` section.

### 4. Nested Imports

```json
{
  "name": "my-lambda",
  "environment_variables": {
    "__imports__": "../base/common-env-vars.json"
  }
}
```

Imports environment variables from external file into nested section.

## Running This Example

### Prerequisites

```bash
pip install cdk-factory>=0.8.2
```

### Test Configuration Loading

Create a simple Python script to test:

```python
# test_config.py
from cdk_factory.utilities.json_loading_utility import JsonLoadingUtility
import json

# Load the workload configuration
loader = JsonLoadingUtility("./workload.json")
config = loader.load()

# Print resolved configuration
print(json.dumps(config, indent=2))
```

Run it:
```bash
python test_config.py
```

### Deploy with CDK

```bash
# Synthesize templates
cdk synth --all

# Deploy
cdk deploy --all
```

## Key Takeaways

1. **Reusability**: Define base configurations once, reuse across environments
2. **DRY Principle**: Don't repeat yourself - import common configs
3. **Layer Overrides**: Stack imports in order, later imports override earlier ones
4. **Nested Imports**: Import at any level of your configuration
5. **Backward Compatible**: Works alongside existing `__inherits__` keyword

## Comparison: Before vs After

### Before (Duplicate Configuration)

**lambda-dev.json:**
```json
{
  "name": "my-lambda-dev",
  "runtime": "python3.13",
  "memory": 256,
  "timeout": 60,
  "handler": "index.handler",
  "environment_variables": [
    {"name": "AWS_REGION", "value": "us-east-1"},
    {"name": "LOG_LEVEL", "value": "INFO"},
    {"name": "ENVIRONMENT", "value": "dev"}
  ]
}
```

**lambda-prod.json:**
```json
{
  "name": "my-lambda-prod",
  "runtime": "python3.13",
  "memory": 512,
  "timeout": 120,
  "handler": "index.handler",
  "environment_variables": [
    {"name": "AWS_REGION", "value": "us-east-1"},
    {"name": "LOG_LEVEL", "value": "INFO"},
    {"name": "ENVIRONMENT", "value": "prod"}
  ]
}
```

**Problems:**
- ❌ Duplicate runtime, handler definitions
- ❌ Duplicate common env vars
- ❌ Hard to maintain consistency
- ❌ Changes need to be replicated

### After (With Imports)

**base.json:**
```json
{
  "runtime": "python3.13",
  "handler": "index.handler"
}
```

**common-env.json:**
```json
[
  {"name": "AWS_REGION", "value": "us-east-1"},
  {"name": "LOG_LEVEL", "value": "INFO"}
]
```

**lambda-dev.json:**
```json
{
  "__imports__": "./base.json",
  "name": "my-lambda-dev",
  "memory": 256,
  "timeout": 60,
  "environment_variables": {
    "__imports__": ["./common-env.json"],
    "additional": [{"name": "ENVIRONMENT", "value": "dev"}]
  }
}
```

**lambda-prod.json:**
```json
{
  "__imports__": "./base.json",
  "name": "my-lambda-prod",
  "memory": 512,
  "timeout": 120,
  "environment_variables": {
    "__imports__": ["./common-env.json"],
    "additional": [{"name": "ENVIRONMENT", "value": "prod"}]
  }
}
```

**Benefits:**
- ✅ Single source of truth for common config
- ✅ Easy to maintain
- ✅ Consistent across environments
- ✅ Changes in one place

## Advanced Patterns

### Pattern 1: Environment-Specific Overrides

```
base.json → dev.json → lambda-dev.json
         → prod.json → lambda-prod.json
```

### Pattern 2: Component Libraries

```
components/
  ├── lambda-defaults.json
  ├── api-defaults.json
  └── database-defaults.json
```

Import as needed in your stacks.

### Pattern 3: Team-Specific Configs

```
team-configs/
  ├── frontend-team.json
  ├── backend-team.json
  └── data-team.json
```

Each team maintains their defaults.

## Tips & Best Practices

1. **Organize by Purpose**: Group base configs, environment configs, and stack configs
2. **Use Descriptive Names**: `lambda-defaults.json` vs `config1.json`
3. **Document Import Chain**: Comment your config structure
4. **Limit Depth**: Keep import chains to 2-3 levels max
5. **Test Imports**: Use the test script to verify resolved configs

## Troubleshooting

### Issue: Import not resolving

**Check:**
- File path is relative to importing file
- File has `.json` extension
- JSON syntax is valid

### Issue: Wrong values after import

**Remember:**
- Later imports override earlier ones
- Current file properties override all imports
- Arrays are replaced, not merged (in most cases)

## Learn More

- [JSON Imports Guide](../../docs/JSON_IMPORTS_GUIDE.md)
- [Migration Guide](../../docs/MIGRATION_v0.8.2.md)
- [Full Changelog](../../CHANGELOG_v0.8.2.md)

---

Happy configuring! 🚀
