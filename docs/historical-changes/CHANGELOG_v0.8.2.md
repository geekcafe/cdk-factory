# CDK Factory v0.8.2 Release Notes

Released: 2025-10-09

## New Features

### 1. `__imports__` Keyword for JSON Configuration Files
**The preferred and more intuitive way to import configuration files!**

**Why**: The `__imports__` keyword is more intuitive and better describes what it does - importing configuration from other files or sections.

**Backward Compatibility**: `__inherits__` continues to work for existing configurations. Both keywords are supported, with `__imports__` taking precedence if both are present.

#### Usage Examples

**Single File Import:**
```json
{
  "__imports__": "./base-lambda-config.json",
  "name": "my-specific-lambda",
  "memory": 512
}
```

**Multiple File Imports (merged in order):**
```json
{
  "__imports__": [
    "./base-config.json",
    "./environment/prod.json",
    "./overrides.json"
  ],
  "handler": "index.handler"
}
```

**Nested Section Import:**
```json
{
  "lambda": {
    "__imports__": ["./common-env-vars.json", "./api-keys.json"],
    "timeout": 60
  }
}
```

**Nested Reference Import:**
```json
{
  "__imports__": "workload.defaults.lambda_config",
  "name": "my-lambda"
}
```

#### Key Benefits

1. **More Intuitive**: "imports" better describes the action than "inherits"
2. **Consistent with Programming**: Matches `import` statements in code
3. **Backward Compatible**: Existing `__inherits__` configs continue to work
4. **Precedence**: `__imports__` takes precedence if both keywords are present
5. **Better Error Messages**: Clear examples shown when invalid syntax is used

#### Migration Guide

**Not required!** Your existing configurations using `__inherits__` will continue to work. However, for new configurations, we recommend using `__imports__`:

**Before (still works):**
```json
{
  "__inherits__": "./base.json",
  "name": "my-app"
}
```

**After (recommended):**
```json
{
  "__imports__": "./base.json",
  "name": "my-app"
}
```

## Bug Fixes from v0.8.1

### 1. Fixed SSM Export Configuration Bug
**Issue**: Documentation showed incorrect pattern `"exports": {"enabled": true}` which caused `AttributeError: 'bool' object has no attribute 'startswith'`

**Fix**: 
- Added type validation in `enhanced_ssm_config.py`
- Updated documentation to show correct pattern: `"auto_export": true`

**Impact**: Prevents crashes when using incorrect SSM export configuration

### 2. Fixed Cognito User Pool SSM Import for API Gateway
**Issue**: API Gateway couldn't find Cognito User Pool ARN, causing `ValueError: User pool ID is required for API Gateway authorizer`

**Fix**:
- Enhanced SSM-based import pattern for `user_pool_arn`
- Added auto-discovery support via `"user_pool_arn": "auto"`

**Impact**: Enables seamless cross-stack Cognito + API Gateway integration

### 3. Fixed Authorizer Creation When Not Needed
**Issue**: API Gateway authorizer was created even when all routes were public (`authorization_type: "NONE"`), causing CDK validation error: `ValidationError: Authorizer must be attached to a RestApi`

**Fix**:
- Modified `_setup_cognito_authorizer()` to only create authorizer when at least one route requires it
- Added `cognito_configured` flag to maintain security validation context
- Security warnings still emitted for public endpoints when Cognito is available

**Impact**: 
- Prevents CDK synthesis errors for public-only APIs
- Maintains security validation without creating unused resources

### 4. Removed Deprecated SSM Parameter Types
**Issue**: Using deprecated `ssm.ParameterType.STRING`, `ssm.ParameterType.STRING_LIST`, and `type` parameter caused AWS CDK deprecation warnings

**Fix**:
- Replaced deprecated `ParameterType` enum with appropriate CDK constructs
- Updated `enhanced_ssm_parameter_mixin.py` to use CDK v2 best practices

**Impact**: 
- Eliminates deprecation warnings
- Future-proofs code for CDK v3

## Test Coverage

- **161 tests passing** ✅ (up from 153)
- New test coverage:
  - `test_json_loading_utility.py` - 8 new tests for `__imports__` functionality
  - All existing tests for `__inherits__` maintained for backward compatibility

## Documentation Updates

### New Documentation
1. **docs/JSON_IMPORTS_GUIDE.md** - Comprehensive guide for `__imports__` usage
2. **CHANGELOG_v0.8.2.md** - This file

### Updated Documentation
- **docs/SSM_EXPORT_FIX.md** - SSM export configuration bug fix guide
- **docs/API_GATEWAY_COGNITO_SSM.md** - Cognito + API Gateway SSM integration
- **README.md** - Updated with v0.8.2 features

## Breaking Changes

**None** - All changes are backward compatible

## Configuration Examples

### Example 1: Lambda Stack with Imports

**base-lambda-config.json:**
```json
{
  "runtime": "python3.13",
  "memory": 128,
  "timeout": 30,
  "environment_variables": [
    {"name": "LOG_LEVEL", "value": "INFO"}
  ]
}
```

**prod-lambda.json:**
```json
{
  "__imports__": "./base-lambda-config.json",
  "name": "my-prod-lambda",
  "memory": 512,
  "timeout": 60,
  "handler": "index.handler"
}
```

**Result**: Lambda inherits base config but overrides memory and timeout.

### Example 2: Multiple Config Layers

**base.json:**
```json
{
  "api_version": "v1",
  "cors": {
    "origins": ["*"],
    "methods": ["GET", "POST"]
  }
}
```

**environment/prod.json:**
```json
{
  "cors": {
    "origins": ["https://myapp.com"]
  },
  "throttling": {
    "rate_limit": 1000,
    "burst_limit": 2000
  }
}
```

**my-api.json:**
```json
{
  "__imports__": ["./base.json", "./environment/prod.json"],
  "name": "my-api",
  "stage_name": "prod"
}
```

**Result**: Deep merge of base config + environment config + specific config.

### Example 3: Nested Section Imports

**common-env-vars.json:**
```json
[
  {"name": "AWS_REGION", "value": "us-east-1"},
  {"name": "LOG_LEVEL", "value": "INFO"}
]
```

**lambda-config.json:**
```json
{
  "name": "my-lambda",
  "runtime": "python3.13",
  "environment_variables": {
    "__imports__": "./common-env-vars.json"
  }
}
```

### Example 4: Backward Compatibility

**Still works with `__inherits__`:**
```json
{
  "__inherits__": "./base.json",
  "name": "legacy-config"
}
```

## Deployment Flow (v0.8.2)

```
1. Cognito Stack       → Exports user_pool_arn to SSM
2. Lambda Stack        → Exports Lambda ARNs to SSM  
3. API Gateway Stack   → Imports via SSM, creates authorizer only if needed
```

## API Gateway Configuration Best Practices

### For Public APIs
```json
{
  "api_gateway": {
    "name": "my-public-api",
    "routes": [
      {
        "path": "/public",
        "method": "GET",
        "authorization_type": "NONE",
        "allow_public_override": true
      }
    ]
  }
}
```

### For Secured APIs with Cognito
```json
{
  "api_gateway": {
    "name": "my-secure-api",
    "ssm": {
      "enabled": true,
      "auto_export": true,
      "imports": {
        "user_pool_arn": "auto"
      }
    },
    "cognito_authorizer": {
      "authorizer_name": "my-authorizer"
    },
    "routes": [
      {
        "path": "/secure",
        "method": "GET"
        // No authorization_type means defaults to COGNITO_USER_POOLS
      }
    ]
  }
}
```

## Upgrade Instructions

### From v0.8.1 to v0.8.2

1. **Update package:**
   ```bash
   pip install --upgrade cdk-factory
   ```

2. **Optional - Migrate to `__imports__`:**
   
   Find all `__inherits__` usage:
   ```bash
   grep -r "__inherits__" ./configs/
   ```
   
   Replace with `__imports__` (optional):
   ```bash
   sed -i '' 's/"__inherits__"/"__imports__"/g' ./configs/*.json
   ```

3. **No code changes required** - All existing configurations continue to work!

### From v0.8.0 or earlier to v0.8.2

Follow the v0.8.1 migration guide first, then upgrade to v0.8.2.

**Critical v0.8.1 fixes to apply:**

1. **Fix SSM export config:**
   ```json
   // Change from:
   "exports": {"enabled": true}
   
   // To:
   "auto_export": true
   ```

2. **Add Cognito SSM import:**
   ```json
   "api_gateway": {
     "ssm": {
       "imports": {
         "user_pool_arn": "auto"
       }
     }
   }
   ```

## Known Issues

None

## Performance Improvements

- JSON loading with multiple imports is optimized for merge operations
- SSM parameter lookups use enhanced caching

## Security Enhancements

- Maintained secure-by-default API Gateway authorization
- Improved validation warnings for public endpoints when Cognito is available
- Better error messages for misconfigurations

## Contributors

- Eric Wilson (@geekcafe)

## Next Steps

Check out the new `__imports__` feature in your configurations! It makes config management much more intuitive.

**Try it out:**
```bash
# Create a base config
cat > base-lambda.json <<EOF
{
  "runtime": "python3.13",
  "memory": 128,
  "timeout": 30
}
EOF

# Use imports in your stack config
cat > my-lambda.json <<EOF
{
  "__imports__": "./base-lambda.json",
  "name": "my-lambda",
  "handler": "index.handler"
}
EOF
```

Happy deploying! 🚀
