# CDK Factory v0.8.3 Release Notes

Released: October 9, 2025

## Bug Fixes

### 1. Fixed Lambda Build Warning: "__pycache__ already exists"

**Issue**: During CDK synth/deploy, pip would display warnings:
```
WARNING: Target directory /var/folders/.../lambda-builds/my-lambda/__pycache__ already exists. 
Specify --upgrade to force replacement.
```

**Root Cause**: 
- Lambda source code was copied to the build directory, including `__pycache__` directories
- Pip would then complain about existing `__pycache__` directories when installing dependencies

**Fix**:
1. **Excluded build artifacts during copy** (`lambda_function_utilities.py`)
   - Added `ignore_patterns` function to `__validate_directories()`
   - Excludes: `__pycache__`, `.pyc`, `.pyo`, `.pytest_cache`, `.mypy_cache`
   - Prevents build artifacts from being copied to Lambda build directory

2. **Added --upgrade flag to pip install**
   - Changed: `pip install -r {requirement} -t {output_dir}`
   - To: `pip install -r {requirement} -t {output_dir} --upgrade`
   - Forces pip to replace any existing packages without warnings

**Impact**:
- ✅ Eliminates pip warnings during Lambda builds
- ✅ Cleaner build output
- ✅ Faster builds (no unnecessary `__pycache__` copies)
- ✅ More reliable builds

**Example Before:**
```bash
cdk synth
# Output:
WARNING: Target directory /var/folders/2p/.../lambda-builds/my-lambda/__pycache__ already exists.
WARNING: Target directory /var/folders/2p/.../lambda-builds/my-lambda/.pytest_cache already exists.
```

**Example After:**
```bash
cdk synth
# Output: Clean, no warnings
```

### 2. Enhanced Lambda Route Naming in API Gateway

**Issue**: Multiple routes to the same path with different HTTP methods would cause naming conflicts.

**Fix**:
- Routes now support explicit `name` field for unique identification
- Auto-generated names include HTTP method for uniqueness: `{method}-{path}`
- Example: `GET /api/users` → `get-api-users`, `POST /api/users` → `post-api-users`

**Before:**
```json
{
  "routes": [
    {"path": "/users", "method": "GET"},   // Could conflict
    {"path": "/users", "method": "POST"}   // Could conflict
  ]
}
```

**After (Auto-named):**
```json
{
  "routes": [
    {"path": "/users", "method": "GET"},   // Auto-named: get-users
    {"path": "/users", "method": "POST"}   // Auto-named: post-users
  ]
}
```

**After (Explicit naming):**
```json
{
  "routes": [
    {"path": "/users", "method": "GET", "name": "list-users"},
    {"path": "/users", "method": "POST", "name": "create-user"}
  ]
}
```

## Carried Forward from v0.8.2

All features and fixes from v0.8.2 are included:

### Features
- ✅ **`__imports__` keyword** - More intuitive configuration imports
- ✅ **Backward compatible** - `__inherits__` still works

### Bug Fixes
- ✅ **SSM Export Configuration** - Type validation
- ✅ **Cognito SSM Integration** - Auto-discovery support
- ✅ **Authorizer Creation** - Only created when needed
- ✅ **SSM Deprecation Warnings** - Eliminated

## Test Coverage

- **167 tests passing** ✅
- All existing tests maintained
- No new tests needed (internal improvements)

## Breaking Changes

**None** - All changes are backward compatible

## Upgrade Instructions

```bash
pip install --upgrade cdk-factory
```

Verify:
```bash
python -c "import cdk_factory; print(cdk_factory.__version__)"
# Output: 0.8.3
```

## Technical Details

### Files Modified

**src/cdk_factory/utilities/lambda_function_utilities.py:**
1. Added `ignore_patterns()` function in `__validate_directories()`
   - Filters out `__pycache__`, `.pyc`, `.pyo`, `.pytest_cache`, `.mypy_cache`
   - Applied to `shutil.copytree()` operation

2. Modified pip install command
   - Added `--upgrade` flag to force replacement of existing packages

**src/cdk_factory/stack_library/api_gateway/api_gateway_stack.py:**
1. Enhanced `_setup_single_lambda_route()` naming logic
   - Supports explicit `name` field in route config
   - Auto-generates unique names with HTTP method prefix

### Excluded Patterns

The following patterns are now excluded when copying Lambda source code:
- `__pycache__/` - Python bytecode cache
- `*.pyc` - Compiled Python files
- `*.pyo` - Optimized Python files
- `.pytest_cache/` - Pytest cache
- `.mypy_cache/` - MyPy cache

## Performance Improvements

- **Faster Lambda builds** - Fewer files copied (excludes cache directories)
- **Smaller Lambda packages** - Build artifacts not included
- **Cleaner logs** - No pip warnings

## Migration Guide

### No Migration Required

This release is 100% backward compatible. Simply upgrade and continue using:

```bash
pip install --upgrade cdk-factory==0.8.3
```

### Optional: Clean Old Build Directories

If you want to clean up old build directories manually:

```bash
# Find temp build directories
find /tmp/cdk-factory/lambda-builds -type d -name "__pycache__" -exec rm -rf {} +
find /var/folders -name "cdk-factory" -type d 2>/dev/null

# Or remove all Lambda builds
rm -rf /tmp/cdk-factory/lambda-builds
rm -rf "$TMPDIR/cdk-factory/lambda-builds"
```

The next `cdk synth` will create fresh, clean build directories.

## Verification

After upgrading, verify the fix:

```bash
# Deploy or synth
cdk synth

# Should NOT see these warnings anymore:
# ❌ WARNING: Target directory .../__pycache__ already exists
# ✅ Clean output
```

## Known Issues

None

## Contributors

- Eric Wilson (@geekcafe)

## Related Issues

- Fixes pip warnings during Lambda function builds
- Improves Lambda package cleanliness
- Enhances API Gateway route naming flexibility

---

## Summary

v0.8.3 is a maintenance release that eliminates annoying pip warnings during Lambda builds and enhances route naming in API Gateway. No breaking changes, just cleaner builds and better DX (Developer Experience).

**Key improvements:**
- ✅ No more `__pycache__` warnings
- ✅ Cleaner build output  
- ✅ Faster Lambda builds
- ✅ Better route naming in API Gateway
- ✅ 100% backward compatible

Happy deploying! 🚀
