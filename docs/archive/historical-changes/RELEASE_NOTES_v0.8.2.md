# CDK Factory v0.8.2 - Release Notes

**Release Date:** October 9, 2025  
**Status:** Stable  
**Breaking Changes:** None ✅

## Quick Summary

CDK Factory v0.8.2 introduces the more intuitive `__imports__` keyword for configuration file composition, fixes critical bugs from v0.8.1, and removes all AWS CDK deprecation warnings.

## 🎉 New Features

### `__imports__` Keyword
Replace `__inherits__` with the more intuitive `__imports__` keyword. Both work - full backward compatibility maintained.

**Before:**
```json
{"__inherits__": "./base.json"}
```

**Now (recommended):**
```json
{"__imports__": "./base.json"}
```

## 🐛 Bug Fixes

### From v0.8.1

1. **SSM Export Configuration**
   - Fixed `AttributeError` when using incorrect export syntax
   - Added type validation

2. **Cognito SSM Integration**
   - API Gateway can now auto-discover Cognito User Pool ARN via SSM
   - Use `"user_pool_arn": "auto"` in imports

3. **Authorizer Creation**
   - Only creates authorizer when routes actually need it
   - Prevents "must be attached to RestApi" errors

4. **SSM Deprecation Warnings**
   - Removed all `ParameterType` deprecation warnings
   - Uses CDK v2 best practices

## 📊 Test Coverage

- **167 tests passing** (up from 153 in v0.8.1)
- 8 new tests for `__imports__` functionality
- All backward compatibility tests maintained

## 📚 Documentation

### New Docs
- `docs/JSON_IMPORTS_GUIDE.md` - Comprehensive imports guide
- `docs/MIGRATION_v0.8.2.md` - Step-by-step migration guide
- `CHANGELOG_v0.8.2.md` - Detailed changelog

### Updated Docs
- All examples updated with `__imports__` usage
- API Gateway + Cognito integration guide
- SSM configuration best practices

## 🚀 Upgrade Instructions

```bash
# Simple upgrade
pip install --upgrade cdk-factory

# Verify
python -c "import cdk_factory; print(cdk_factory.__version__)"
# Output: 0.8.2
```

**That's it!** No code changes required. All existing configurations work as-is.

## 💡 Quick Start with `__imports__`

**Create reusable configs:**

```bash
# base-lambda.json
{
  "runtime": "python3.13",
  "memory": 128,
  "timeout": 30
}

# my-lambda.json
{
  "__imports__": "./base-lambda.json",
  "name": "my-lambda",
  "handler": "index.handler"
}
```

**Works with multiple files:**
```json
{
  "__imports__": [
    "./base.json",
    "./env-prod.json",
    "./overrides.json"
  ]
}
```

## 🎯 Who Should Upgrade?

### Must Upgrade If:
- ❌ Getting SSM export `AttributeError` errors
- ❌ API Gateway can't find Cognito User Pool
- ❌ Getting "Authorizer must be attached" errors
- ❌ Seeing AWS CDK deprecation warnings

### Should Upgrade:
- ✅ Want more intuitive config syntax (`__imports__`)
- ✅ Want better error messages
- ✅ Want to future-proof against CDK v3
- ✅ Want enhanced SSM integration

### Can Wait:
- 😊 Everything working fine with v0.8.1 or earlier
- 😊 Happy with `__inherits__` keyword

## 🔄 Migration Effort

| Current Version | Effort | Time | Notes |
|----------------|--------|------|-------|
| v0.8.1 | Minimal | 5 min | Just `pip install --upgrade` |
| v0.8.0 | Low | 15 min | Apply SSM fixes + upgrade |
| v0.7.x | Medium | 30 min | Review breaking changes first |

## 📝 Configuration Changes Required

### If Using Incorrect SSM Syntax

**Change:**
```diff
{
  "ssm": {
-   "exports": {"enabled": true}
+   "auto_export": true
  }
}
```

### If Using Cognito + API Gateway

**Add:**
```diff
{
  "api_gateway": {
+   "ssm": {
+     "imports": {
+       "user_pool_arn": "auto"
+     }
+   }
  }
}
```

## 🎨 Before & After Examples

### SSM Configuration
```json
// ❌ Before (broken in v0.8.0-0.8.1)
{
  "ssm": {
    "exports": {"enabled": true}
  }
}

// ✅ After
{
  "ssm": {
    "auto_export": true
  }
}
```

### Config Imports
```json
// 👴 Old way (still works)
{
  "__inherits__": "./base.json"
}

// ✨ New way (recommended)
{
  "__imports__": "./base.json"
}
```

### API Gateway + Cognito
```json
// 🔴 Before (manual ARN)
{
  "cognito_authorizer": {
    "user_pool_arn": "${COGNITO_USER_POOL_ARN}"
  }
}

// 🟢 After (auto-discovery)
{
  "ssm": {
    "imports": {
      "user_pool_arn": "auto"
    }
  },
  "cognito_authorizer": {
    "authorizer_name": "my-authorizer"
  }
}
```

## 🛡️ Backward Compatibility

| Feature | v0.8.2 | Notes |
|---------|---------|-------|
| `__inherits__` | ✅ Works | Maintained forever |
| `__imports__` | ✅ Works | New, preferred |
| Old SSM syntax | ⚠️ Warns | Use `auto_export` instead |
| Environment variables | ✅ Works | Still supported |

## 🧪 Quality Metrics

- **Test Coverage:** 167 tests (up from 153)
- **Documentation:** 3 new comprehensive guides
- **Deprecation Warnings:** 0 (down from 12+)
- **Breaking Changes:** 0
- **Bug Fixes:** 4 critical issues resolved

## 🔍 What's Not Changed

- ✅ All existing APIs remain the same
- ✅ Stack modules work identically
- ✅ Deployment behavior unchanged
- ✅ CDK version requirements unchanged (2.202.0)
- ✅ Python version support unchanged (3.10+)

## 📖 Documentation Links

- [Full Changelog](./CHANGELOG_v0.8.2.md)
- [Migration Guide](./docs/MIGRATION_v0.8.2.md)
- [JSON Imports Guide](./docs/JSON_IMPORTS_GUIDE.md)
- [API Gateway + Cognito](./docs/API_GATEWAY_COGNITO_SSM.md)

## 🤝 Contributing

Found a bug? Have a feature request?

- GitHub Issues: https://github.com/your-org/cdk-factory/issues
- Documentation: https://github.com/your-org/cdk-factory/wiki

## 👥 Credits

- **Eric Wilson** (@geekcafe) - Lead Developer
- **Contributors** - Community testing and feedback

## 🗓️ Release Timeline

- **v0.8.0** - August 2025 - Enhanced SSM, various features
- **v0.8.1** - October 2025 - Critical bug fixes
- **v0.8.2** - October 2025 - `__imports__`, deprecation fixes ⬅️ You are here

## 🔮 What's Next?

Looking ahead to v0.8.3:
- Enhanced CloudWatch monitoring integration
- Additional stack modules
- Performance optimizations
- More comprehensive examples

---

## TL;DR

```bash
pip install --upgrade cdk-factory
```

✅ No breaking changes  
✅ New `__imports__` keyword (optional, recommended)  
✅ 4 critical bugs fixed  
✅ 0 deprecation warnings  
✅ 167 tests passing  

Happy deploying! 🚀
