# Migration Guide to v0.8.2

## Overview

CDK Factory v0.8.2 introduces the `__imports__` keyword and fixes several critical bugs. **All changes are backward compatible** - no immediate action required!

## What's New in v0.8.2

1. ✨ **New `__imports__` keyword** - More intuitive than `__inherits__`
2. 🐛 **Bug fixes from v0.8.1** - SSM exports, Cognito integration, authorizer creation
3. 📝 **Improved documentation** - Comprehensive guides and examples
4. ✅ **167 tests passing** - Increased test coverage

## Migration Steps

### Step 1: Update Package

```bash
pip install --upgrade cdk-factory
```

Verify version:
```bash
python -c "import cdk_factory; print(cdk_factory.__version__)"
# Should output: 0.8.2
```

### Step 2: (Optional) Migrate to `__imports__`

The `__imports__` keyword is **recommended** for new configurations but **not required**. Your existing `__inherits__` configurations will continue to work.

#### Find All Uses

```bash
# Find all __inherits__ usage
find ./configs -name "*.json" -exec grep -l "__inherits__" {} \;
```

#### Replace (Optional)

**Manual replacement (safest):**
Open each file and replace `"__inherits__"` with `"__imports__"`

**Automated replacement (verify first!):**
```bash
# Dry run - see what would change
find ./configs -name "*.json" -exec grep -H "__inherits__" {} \;

# Backup first
cp -r ./configs ./configs.backup

# Replace
find ./configs -name "*.json" -exec sed -i '' 's/"__inherits__"/"__imports__"/g' {} +

# Verify
diff -r ./configs ./configs.backup
```

**Test after replacement:**
```bash
cdk synth  # Or your normal build command
```

### Step 3: Apply Bug Fixes (If Affected)

#### Fix 1: SSM Export Configuration

**If you have this pattern:**
```json
{
  "ssm": {
    "enabled": true,
    "exports": {
      "enabled": true  // ❌ Incorrect
    }
  }
}
```

**Change to:**
```json
{
  "ssm": {
    "enabled": true,
    "auto_export": true  // ✅ Correct
  }
}
```

**Find affected files:**
```bash
grep -r '"exports".*:.*{' ./configs/
```

#### Fix 2: Cognito User Pool SSM Import

**If API Gateway can't find Cognito User Pool:**

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

#### Fix 3: Authorizer Creation (Automatic Fix)

**No action needed!** The fix automatically prevents authorizer creation when all routes are public.

**Before (v0.8.1):**
- Created authorizer even if unused
- CDK validation error

**After (v0.8.2):**
- Only creates authorizer if at least one route needs it
- No validation errors

## Verification Checklist

After migration, verify:

- [ ] Package version is 0.8.2
- [ ] `cdk synth` completes without errors
- [ ] No deprecation warnings about SSM ParameterType
- [ ] API Gateway deploys successfully
- [ ] Cognito integration works (if used)
- [ ] All tests pass (if you have custom tests)

## Example Migrations

### Example 1: Simple Config Migration

**Before:**
```json
{
  "__inherits__": "./base-lambda.json",
  "name": "my-lambda",
  "handler": "index.handler"
}
```

**After (recommended):**
```json
{
  "__imports__": "./base-lambda.json",
  "name": "my-lambda",
  "handler": "index.handler"
}
```

### Example 2: Multiple Imports

**Before:**
```json
{
  "__inherits__": ["./base.json", "./prod.json"],
  "custom_property": "value"
}
```

**After (recommended):**
```json
{
  "__imports__": ["./base.json", "./prod.json"],
  "custom_property": "value"
}
```

### Example 3: SSM Configuration Fix

**Before (broken):**
```json
{
  "name": "lambda-stack",
  "module": "lambda_stack",
  "ssm": {
    "enabled": true,
    "exports": {
      "enabled": true,
      "organization": "myapp",
      "environment": "prod"
    }
  }
}
```

**After (fixed):**
```json
{
  "name": "lambda-stack",
  "module": "lambda_stack",
  "ssm": {
    "enabled": true,
    "auto_export": true,
    "organization": "myapp",
    "environment": "prod"
  }
}
```

### Example 4: API Gateway with Cognito

**Before (incomplete):**
```json
{
  "name": "api-gateway-stack",
  "module": "api_gateway_stack",
  "api_gateway": {
    "name": "my-api",
    "cognito_authorizer": {
      "user_pool_arn": "${COGNITO_USER_POOL_ARN}"  // Environment variable
    }
  }
}
```

**After (using SSM auto-discovery):**
```json
{
  "name": "api-gateway-stack",
  "module": "api_gateway_stack",
  "api_gateway": {
    "name": "my-api",
    "ssm": {
      "enabled": true,
      "imports": {
        "user_pool_arn": "auto"  // ✅ Auto-discover from SSM
      }
    },
    "cognito_authorizer": {
      "authorizer_name": "my-authorizer"
    }
  }
}
```

## Rollback Plan

If you encounter issues after upgrading:

### Option 1: Rollback Package

```bash
pip install cdk-factory==0.8.1
```

### Option 2: Revert Configuration Changes

```bash
# If you backed up your configs
rm -rf ./configs
mv ./configs.backup ./configs
```

### Option 3: Git Revert

```bash
git revert HEAD  # Revert the migration commit
```

## Common Issues & Solutions

### Issue 1: Import Syntax Error

**Error:**
```
ValueError: __imports__ must be a string or list of paths
```

**Solution:**
Ensure `__imports__` is a string or array:
```json
// ✅ Correct
"__imports__": "./base.json"
"__imports__": ["./base.json", "./prod.json"]

// ❌ Wrong
"__imports__": 123
"__imports__": true
```

### Issue 2: SSM Export Error

**Error:**
```
AttributeError: 'bool' object has no attribute 'startswith'
```

**Solution:**
Change from `"exports": {"enabled": true}` to `"auto_export": true`

### Issue 3: Cognito User Pool Not Found

**Error:**
```
ValueError: User pool ID is required for API Gateway authorizer
```

**Solution:**
Add SSM imports configuration:
```json
{
  "ssm": {
    "imports": {
      "user_pool_arn": "auto"
    }
  }
}
```

### Issue 4: Authorizer Must Be Attached Error

**Error:**
```
ValidationError: Authorizer must be attached to a RestApi
```

**Solution:**
This is automatically fixed in v0.8.2. Ensure you're using version 0.8.2:
```bash
pip show cdk-factory | grep Version
```

## Testing Your Migration

### Basic Test

```bash
# Synthesize CDK templates
cdk synth

# Check for errors
echo $?  # Should be 0
```

### Comprehensive Test

```bash
# Run unit tests (if you have them)
pytest tests/

# Deploy to test environment
cdk deploy --all --require-approval never

# Verify functionality
# (your application-specific tests)
```

## Getting Help

If you encounter issues:

1. **Check Documentation:**
   - [CHANGELOG_v0.8.2.md](../CHANGELOG_v0.8.2.md)
   - [JSON_IMPORTS_GUIDE.md](./JSON_IMPORTS_GUIDE.md)
   - [API_GATEWAY_COGNITO_SSM.md](./API_GATEWAY_COGNITO_SSM.md)

2. **Review Examples:**
   - Check `examples/` directory for working configurations

3. **Check GitHub Issues:**
   - Search existing issues: https://github.com/your-org/cdk-factory/issues

4. **Create New Issue:**
   - Include CDK Factory version
   - Include error messages
   - Include relevant config snippets

## Summary

✅ **Backward Compatible** - No breaking changes
✅ **Optional Migration** - `__inherits__` still works
✅ **Bug Fixes Applied** - More stable and reliable
✅ **Better Documentation** - Comprehensive guides available
✅ **More Tests** - 167 tests ensure quality

**Recommendation:** Upgrade to v0.8.2 for bug fixes, optionally migrate to `__imports__` for better readability.

Happy deploying! 🚀
