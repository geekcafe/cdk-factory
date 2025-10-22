# Bug Fix: SSM Imports Processing Metadata Fields as Parameters

## Issue Summary

**Error:** `Unable to fetch parameters [geekcafe,prod] from parameter store for this account`

**Root Cause:** The SSM imports configuration processor was treating metadata fields (`workload`, `environment`) as actual parameters to import, causing CloudFormation to try fetching non-existent SSM parameters named "geekcafe" and "prod".

## The Bug

### Configuration Example
```json
{
  "ssm": {
    "imports": {
      "workload": "geekcafe",       // ❌ Incorrectly treated as parameter to import
      "environment": "prod",         // ❌ Incorrectly treated as parameter to import
      "user_pool_arn": "auto"       // ✅ Actual parameter to import
    }
  }
}
```

### What Was Happening
The code in `enhanced_ssm_config.py` (line 140) iterated through ALL keys in the `imports` dict:

```python
for attribute, import_value in self.ssm_imports.items():
    # This was processing workload, environment, AND user_pool_arn
    definitions.append(...)
```

This caused it to try to import:
1. ❌ SSM parameter named "geekcafe" (from `workload` key)
2. ❌ SSM parameter named "prod" (from `environment` key)
3. ✅ SSM parameter for `user_pool_arn` (the actual import)

CloudFormation then failed trying to fetch parameters "[geekcafe,prod]" which don't exist.

## The Fix

### Code Change
**File:** `src/cdk_factory/configurations/enhanced_ssm_config.py`
**Lines:** 140-146

```python
# Handle dict format: {"attribute": "auto" or path}
# Skip metadata fields that are not actual imports
metadata_fields = {"workload", "environment", "organization"}

for attribute, import_value in self.ssm_imports.items():
    # Skip metadata fields - they specify context, not what to import
    if attribute in metadata_fields:
        continue
    
    # Process actual imports...
```

### What Changed
- Added a set of `metadata_fields` that should be skipped
- Added a check to skip these fields before processing
- Now only actual resource imports (like `user_pool_arn`) are processed

## Testing

### Test File
`tests/unit/test_cognito_ssm_path_resolution.py`

### Test Verification
```python
ssm_imports={
    "workload": "geekcafe",      # Should be SKIPPED
    "environment": "prod",        # Should be SKIPPED  
    "user_pool_arn": "auto"      # Should be processed
}

import_defs = config.get_import_definitions()
assert len(import_defs) == 1  # Only user_pool_arn, not workload/environment
```

## Impact

### Before Fix
- ❌ CloudFormation deployment failed with "Unable to fetch parameters [geekcafe,prod]"
- ❌ Auto-import feature (`"user_pool_arn": "auto"`) was broken
- ❌ Users had to use explicit paths as workaround

### After Fix
- ✅ CloudFormation deployment succeeds
- ✅ Auto-import feature works correctly
- ✅ Metadata fields are correctly recognized as context, not imports
- ✅ Only actual resource imports are processed

## Related Issues

This fix resolves the issue where API Gateway could not auto-import Cognito User Pool ARN from SSM Parameter Store, even though:
1. The path resolution logic was correct (`/geekcafe/prod/cognito/user-pool/user-pool-arn`)
2. The SSM parameter existed in AWS
3. The configuration looked correct

The bug was subtle - the metadata fields used to specify WHERE to look were being processed as WHAT to import.

## Migration Notes

No configuration changes required. Existing configurations will work correctly after this fix. The metadata fields (`workload`, `environment`) can remain in the `imports` section - they will now be properly filtered out.

## Files Changed

1. `src/cdk_factory/configurations/enhanced_ssm_config.py` - Core fix
2. `tests/unit/test_cognito_ssm_path_resolution.py` - New test
3. `tests/unit/test_api_gateway_cognito_auto_import.py` - Diagnostic test

## Verified Scenarios

- ✅ API Gateway auto-importing Cognito User Pool ARN
- ✅ Lambda auto-importing DynamoDB table names
- ✅ RDS auto-importing VPC IDs
- ✅ Mixed explicit paths and auto-discovery

## Version

Fixed in: Next release
Issue reported: 2025-10-10
