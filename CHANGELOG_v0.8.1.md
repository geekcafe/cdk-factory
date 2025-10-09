# CDK Factory v0.8.1 Release Notes

Released: 2025-10-09

## Bug Fixes

### 1. Fixed SSM Export Configuration Bug
**Issue**: Documentation showed incorrect pattern `"exports": {"enabled": true}` which caused `AttributeError: 'bool' object has no attribute 'startswith'`

**Fix**: 
- Added type validation in `enhanced_ssm_config.py` to handle non-string values
- Updated documentation to show correct pattern: `"auto_export": true`
- Created comprehensive documentation in `docs/SSM_EXPORT_FIX.md`

**Impact**: Prevents crashes when using incorrect SSM export configuration

### 2. Fixed Cognito User Pool SSM Import for API Gateway
**Issue**: API Gateway couldn't find Cognito User Pool ARN, causing `ValueError: User pool ID is required for API Gateway authorizer`

**Fix**:
- Enhanced SSM-based import pattern for `user_pool_arn`
- Created comprehensive guide in `docs/API_GATEWAY_COGNITO_SSM.md`
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
- Reduces AWS resource overhead

### 4. Removed Deprecated SSM Parameter Types
**Issue**: Using deprecated `ssm.ParameterType.STRING`, `ssm.ParameterType.STRING_LIST`, and `type` parameter caused AWS CDK deprecation warnings

**Fix**:
- Replaced deprecated `ParameterType` enum with appropriate CDK constructs:
  - `StringParameter` for regular strings (no `type` parameter needed)
  - `StringListParameter` for string lists
  - `CfnParameter` with `type="SecureString"` for secure strings
- Updated `enhanced_ssm_parameter_mixin.py` to use CDK v2 best practices

**Impact**: 
- Eliminates deprecation warnings
- Future-proofs code for CDK v3
- Follows AWS CDK v2 best practices

## Test Coverage

- **153 tests passing** ✅
- New test coverage:
  - `test_api_gateway_export_config.py` (6 tests)
  - `test_api_gateway_authorizer_ssm_integration.py` (5 tests)
  - `test_cross_stack_ssm_integration.py` (3 tests)
  - `test_api_gateway_enhanced_authorization_validation.py` (6 tests)

## Documentation Added

1. **docs/SSM_EXPORT_FIX.md** - SSM export configuration bug fix guide
2. **docs/API_GATEWAY_COGNITO_SSM.md** - Comprehensive Cognito + API Gateway SSM integration guide
3. **GEEK_CAFE_FIX.md** - Quick fix guide for geek-cafe project (example usage)

## Breaking Changes

None - all changes are backward compatible

## Migration Guide

### If you're using the old export pattern:

**Before (v0.8.0 - incorrect docs):**
```json
{
  "ssm": {
    "enabled": true,
    "exports": {
      "enabled": true  // ❌ Wrong
    }
  }
}
```

**After (v0.8.1):**
```json
{
  "ssm": {
    "enabled": true,
    "auto_export": true  // ✅ Correct
  }
}
```

### If you're getting Cognito User Pool errors:

Add to your API Gateway stack config:
```json
{
  "api_gateway": {
    "ssm": {
      "imports": {
        "user_pool_arn": "auto"  // ✅ Add this
      }
    }
  }
}
```

### If you have public-only API routes:

Your config should work without changes. The authorizer will only be created if needed:
```json
{
  "cognito_authorizer": {
    "authorizer_name": "my-authorizer"  // Config present but not used
  },
  "routes": [
    {
      "path": "/public",
      "method": "GET",
      "authorization_type": "NONE",  // ✅ Authorizer won't be created
      "allow_public_override": true
    }
  ]
}
```

## Deployment Flow (v0.8.1+)

```
1. Cognito Stack       → Exports user_pool_arn to SSM
2. Lambda Stack        → Exports Lambda ARNs to SSM
3. API Gateway Stack   → Imports both, creates authorizer only if needed
```

## Known Issues

None

## Contributors

- Eric Wilson (@geekcafe)
