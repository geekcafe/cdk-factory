# JSON Imports Guide - CDK Factory v0.8.2+

## Overview

CDK Factory now supports the `__imports__` keyword for importing configuration from external files or nested sections. This is the preferred and more intuitive replacement for the legacy `__inherits__` keyword.

**Backward Compatibility**: Both `__imports__` and `__inherits__` are supported. Existing configurations using `__inherits__` continue to work without any changes.

## Why `__imports__`?

- **More Intuitive**: Better describes the action - importing configuration
- **Consistent with Code**: Matches `import` statements in programming languages
- **Clearer Intent**: Makes config files more readable and maintainable
- **Better Tooling**: IDEs can better understand the concept of "imports"

## Basic Usage

### Single File Import

Import configuration from a single external file:

```json
{
  "__imports__": "./base-config.json",
  "name": "my-specific-config"
}
```

**How it works:**
1. Loads `base-config.json`
2. Merges its properties into the current config
3. Properties in the current file override imported ones

### Multiple File Imports

Import and merge multiple configuration files (processed in order):

```json
{
  "__imports__": [
    "./base.json",
    "./environment/prod.json",
    "./overrides.json"
  ],
  "custom_property": "value"
}
```

**Merge Order:**
1. `base.json` is loaded first
2. `environment/prod.json` is merged (overrides base)
3. `overrides.json` is merged (overrides previous)
4. Current file properties applied last (highest priority)

## Import Types

### 1. File Path Import

Import from a relative file path:

```json
{
  "__imports__": "./configs/base-lambda.json"
}
```

**Rules:**
- Must end with `.json`
- Relative to the importing file's directory
- Supports nested directories: `"../../shared/config.json"`

### 2. Directory Import

Import all JSON files from a directory:

```json
{
  "__imports__": "./configs/"
}
```

**Behavior:**
- Loads all `.json` files in the directory
- Merges them into an array
- Useful for loading multiple related configs

### 3. Nested Reference Import

Import from a nested section in the same configuration:

```json
{
  "workload": {
    "defaults": {
      "lambda": {
        "runtime": "python3.13",
        "memory": 128
      }
    },
    "stacks": [
      {
        "__imports__": "workload.defaults.lambda",
        "name": "my-lambda"
      }
    ]
  }
}
```

**Rules:**
- Use dot notation: `"parent.child.property"`
- References sections within the root config
- Useful for DRY (Don't Repeat Yourself) configurations

## Advanced Patterns

### Pattern 1: Layered Configuration

**Use Case**: Different environments with shared base config

**Structure:**
```
configs/
├── base.json           # Shared defaults
├── environments/
│   ├── dev.json       # Dev overrides
│   ├── staging.json   # Staging overrides
│   └── prod.json      # Prod overrides
└── my-stack.json      # Stack-specific config
```

**base.json:**
```json
{
  "api_version": "v1",
  "timeout": 30,
  "memory": 128,
  "cors": {
    "methods": ["GET", "POST"],
    "origins": ["*"]
  }
}
```

**environments/prod.json:**
```json
{
  "memory": 512,
  "timeout": 60,
  "cors": {
    "origins": ["https://myapp.com", "https://www.myapp.com"]
  }
}
```

**my-stack.json:**
```json
{
  "__imports__": [
    "./base.json",
    "./environments/prod.json"
  ],
  "name": "my-prod-stack",
  "handler": "index.handler"
}
```

**Result:**
```json
{
  "name": "my-prod-stack",
  "api_version": "v1",
  "timeout": 60,           // Overridden by prod
  "memory": 512,           // Overridden by prod
  "handler": "index.handler",
  "cors": {
    "methods": ["GET", "POST"],
    "origins": ["https://myapp.com", "https://www.myapp.com"]  // From prod
  }
}
```

### Pattern 2: Shared Environment Variables

**Use Case**: Reusable environment variable sets

**common-env-vars.json:**
```json
[
  {"name": "AWS_REGION", "value": "us-east-1"},
  {"name": "LOG_LEVEL", "value": "INFO"},
  {"name": "ENVIRONMENT", "value": "production"}
]
```

**database-env-vars.json:**
```json
[
  {"name": "DB_HOST", "value": "prod-db.example.com"},
  {"name": "DB_PORT", "value": "5432"}
]
```

**lambda-config.json:**
```json
{
  "name": "my-lambda",
  "runtime": "python3.13",
  "environment_variables": {
    "__imports__": [
      "./common-env-vars.json",
      "./database-env-vars.json"
    ]
  }
}
```

**Result**: All environment variables are merged into a single array.

### Pattern 3: Component Library

**Use Case**: Reusable component configurations

**components/api-gateway-defaults.json:**
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

**components/cognito-defaults.json:**
```json
{
  "cognito_authorizer": {
    "identity_source": "method.request.header.Authorization"
  }
}
```

**my-api-gateway.json:**
```json
{
  "__imports__": [
    "./components/api-gateway-defaults.json",
    "./components/cognito-defaults.json"
  ],
  "name": "my-custom-api",
  "routes": [
    {
      "path": "/users",
      "method": "GET",
      "lambda_name": "get-users"
    }
  ]
}
```

### Pattern 4: Template Override Pattern

**Use Case**: Override specific nested properties

**base-lambda.json:**
```json
{
  "runtime": "python3.13",
  "memory": 128,
  "timeout": 30,
  "environment_variables": [
    {"name": "LOG_LEVEL", "value": "INFO"}
  ],
  "vpc_config": {
    "subnet_ids": ["subnet-default"],
    "security_group_ids": ["sg-default"]
  }
}
```

**high-memory-lambda.json:**
```json
{
  "__imports__": "./base-lambda.json",
  "name": "processor-lambda",
  "memory": 1024,
  "timeout": 300,
  "environment_variables": [
    {"name": "LOG_LEVEL", "value": "DEBUG"},
    {"name": "PROCESSOR_MODE", "value": "batch"}
  ]
}
```

**Note**: Arrays are replaced, not merged. Use multiple imports if you need to merge arrays.

## Nested Section Imports

### Use Case: DRY Configuration

```json
{
  "workload": {
    "name": "my-app",
    "defaults": {
      "lambda_config": {
        "runtime": "python3.13",
        "memory": 128,
        "timeout": 30
      },
      "api_config": {
        "stage_name": "prod",
        "throttling_rate_limit": 1000
      }
    },
    "stacks": [
      {
        "name": "lambda-stack-1",
        "module": "lambda_stack",
        "resources": [
          {
            "__imports__": "workload.defaults.lambda_config",
            "name": "lambda-1",
            "handler": "handler1.main"
          },
          {
            "__imports__": "workload.defaults.lambda_config",
            "name": "lambda-2",
            "handler": "handler2.main",
            "memory": 256  // Override
          }
        ]
      },
      {
        "name": "api-stack",
        "module": "api_gateway_stack",
        "api_gateway": {
          "__imports__": "workload.defaults.api_config",
          "name": "my-api",
          "routes": [...]
        }
      }
    ]
  }
}
```

## Merge Behavior

### Dictionary Merge (Deep Merge)

Dictionaries are merged recursively:

**base.json:**
```json
{
  "vpc": {
    "cidr": "10.0.0.0/16",
    "subnets": ["subnet1"],
    "dns": true
  }
}
```

**override.json:**
```json
{
  "__imports__": "./base.json",
  "vpc": {
    "subnets": ["subnet2", "subnet3"],
    "nat_gateways": 2
  }
}
```

**Result:**
```json
{
  "vpc": {
    "cidr": "10.0.0.0/16",          // From base
    "subnets": ["subnet2", "subnet3"], // Overridden
    "dns": true,                     // From base
    "nat_gateways": 2                // Added
  }
}
```

### Array Concatenation

When importing arrays from multiple files:

**list1.json:**
```json
[
  {"name": "item1"},
  {"name": "item2"}
]
```

**list2.json:**
```json
[
  {"name": "item3"}
]
```

**main.json:**
```json
{
  "__imports__": ["./list1.json", "./list2.json"]
}
```

**Result:**
```json
[
  {"name": "item1"},
  {"name": "item2"},
  {"name": "item3"}
]
```

### Scalar Override

Scalar values (strings, numbers, booleans) are replaced:

```json
{
  "__imports__": "./base.json",
  "timeout": 60  // Replaces base.json's timeout
}
```

## Error Handling

### Invalid Type Error

```json
{
  "__imports__": 123  // ❌ Error
}
```

**Error Message:**
```
ValueError: __imports__ must be a string or list of paths, got <class 'int'>. 
Example: '__imports__': './base.json' or '__imports__': ['base.json', 'overrides.json']
```

### File Not Found

If an imported file doesn't exist:
```
FileNotFoundError: [Errno 2] No such file or directory: '/path/to/config/missing.json'
```

### Invalid JSON

If an imported file has invalid JSON:
```
json.decoder.JSONDecodeError: Expecting property name enclosed in double quotes
```

## Best Practices

### 1. Use Descriptive Names

**Good:**
```json
{
  "__imports__": [
    "./base-lambda-config.json",
    "./prod-environment.json"
  ]
}
```

**Avoid:**
```json
{
  "__imports__": [
    "./b.json",
    "./prod.json"
  ]
}
```

### 2. Organize by Purpose

```
configs/
├── base/
│   ├── lambda-defaults.json
│   ├── api-defaults.json
│   └── vpc-defaults.json
├── environments/
│   ├── dev.json
│   ├── staging.json
│   └── prod.json
└── stacks/
    ├── lambda-stack.json
    └── api-stack.json
```

### 3. Document Override Intent

Add comments (in documentation, not JSON) explaining why overrides exist:

```json
{
  "__imports__": "./base.json",
  "memory": 1024,  // Increased for large file processing
  "timeout": 300   // Extended for batch operations
}
```

### 4. Limit Import Depth

**Good:** 1-2 levels of imports
```json
// my-config.json imports base.json
// base.json is self-contained
```

**Avoid:** Deep import chains
```json
// my-config.json -> base.json -> super-base.json -> ultra-base.json
```

### 5. Use Relative Paths

**Good:**
```json
{
  "__imports__": "./base.json"
}
```

**Avoid absolute paths:**
```json
{
  "__imports__": "/Users/username/project/configs/base.json"  // ❌ Not portable
}
```

## Backward Compatibility

### Legacy `__inherits__` Support

All existing configurations using `__inherits__` continue to work:

```json
{
  "__inherits__": "./base.json",  // Still works!
  "name": "my-config"
}
```

### Mixed Usage (Not Recommended)

If both `__imports__` and `__inherits__` are present, `__imports__` takes precedence:

```json
{
  "__imports__": "./import.json",    // This is used
  "__inherits__": "./inherit.json",  // This is ignored
  "name": "config"
}
```

**Recommendation**: Use only one keyword per file.

### Migration Strategy

**Option 1: Do Nothing** - `__inherits__` will continue to work indefinitely

**Option 2: Gradual Migration** - Replace `__inherits__` with `__imports__` as you update configs

```bash
# Find all uses of __inherits__
grep -r "__inherits__" ./configs/

# Replace with __imports__ (verify first!)
find ./configs -name "*.json" -exec sed -i '' 's/"__inherits__"/"__imports__"/g' {} +
```

**Option 3: Standardize on `__imports__`** - Update all configs at once (safest with version control)

## Real-World Examples

### Example 1: Multi-Environment Lambda Deployment

```
configs/
├── lambda-base.json
├── env-dev.json
├── env-prod.json
└── my-lambda.json
```

**lambda-base.json:**
```json
{
  "runtime": "python3.13",
  "layers": ["arn:aws:lambda:us-east-1:123456789012:layer:common:1"]
}
```

**env-prod.json:**
```json
{
  "memory": 512,
  "timeout": 60,
  "environment_variables": [
    {"name": "ENVIRONMENT", "value": "production"}
  ]
}
```

**my-lambda.json:**
```json
{
  "__imports__": [
    "./lambda-base.json",
    "./env-prod.json"
  ],
  "name": "data-processor",
  "handler": "processor.handle"
}
```

### Example 2: Reusable API Gateway Routes

**routes/health-check.json:**
```json
{
  "path": "/health",
  "method": "GET",
  "authorization_type": "NONE",
  "allow_public_override": true
}
```

**routes/authenticated-routes.json:**
```json
[
  {
    "path": "/users",
    "method": "GET",
    "lambda_name": "get-users"
  },
  {
    "path": "/users",
    "method": "POST",
    "lambda_name": "create-user"
  }
]
```

**api-gateway-config.json:**
```json
{
  "name": "my-api",
  "api_type": "REST",
  "routes": {
    "__imports__": [
      "./routes/health-check.json",
      "./routes/authenticated-routes.json"
    ]
  }
}
```

## Troubleshooting

### Problem: Import not working

**Check:**
1. File path is correct and relative to the importing file
2. File has `.json` extension
3. JSON syntax is valid
4. File permissions allow reading

### Problem: Properties not overriding as expected

**Remember:**
- Import order matters (last import wins)
- Current file properties always have highest priority
- Arrays are replaced, not merged

### Problem: Circular import

**Error behavior**: Stack overflow or maximum recursion depth exceeded

**Solution**: Ensure imports don't create circular dependencies
```
a.json -> b.json -> a.json  // ❌ Circular dependency
```

## Summary

- ✅ Use `__imports__` for new configurations (more intuitive)
- ✅ `__inherits__` continues to work (backward compatible)
- ✅ Import single files, multiple files, or nested sections
- ✅ Properties merge deeply for objects, concatenate for arrays
- ✅ Current file properties always override imported ones
- ✅ Organize configs by purpose (base, environment, component)
- ✅ Keep import chains shallow (1-2 levels max)

Happy configuring! 🚀
