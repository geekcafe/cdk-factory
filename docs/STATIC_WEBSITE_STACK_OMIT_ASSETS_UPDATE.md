# Static Website Stack - Omit Assets Section Update

## Overview

Improved handling of missing `assets` configuration section to provide cleaner CDN-only configurations.

## What Changed

### Code Changes

**Before:**
- Required explicit `{"assets": {"deploy": false}}` for CDN-only mode
- Accessed `assets_config` properties before checking if it exists (potential bug)

**After:**
- Can **omit entire `assets` section** for CDN-only mode
- Checks if `assets_config` exists before accessing properties (bug fix)
- Cleaner, more intuitive configuration

### Bug Fix

Fixed order of operations in `__get_website_assets_path`:

```python
# BEFORE (buggy):
assets_config = stack_config.dictionary.get("assets")
deploy_assets = assets_config.get("deploy", True)  # ❌ Fails if assets_config is None

if not assets_config:
    return None

# AFTER (fixed):
assets_config = stack_config.dictionary.get("assets")

if not assets_config:  # ✅ Check existence first
    logger.info("No assets configuration found - skipping asset path resolution")
    return None

deploy_assets = assets_config.get("deploy", True)  # ✅ Safe to access now
```

### Configuration Improvements

**CDN-Only Mode - Old Way (Still Works):**
```json
{
  "name": "cdn",
  "module": "static_website_stack",
  "bucket": {"create": false, "name": "my-bucket"},
  "assets": {
    "deploy": false,
    "enable_versioning": false
  }
}
```

**CDN-Only Mode - New Way (Cleaner):**
```json
{
  "name": "cdn",
  "module": "static_website_stack",
  "bucket": {"create": false, "name": "my-bucket"}
  // No "assets" section needed!
}
```

## Files Updated

### Code
- ✅ `static_website_stack.py` - Fixed bug, added null checks
  - Added `@register_stack("cdn_stack")` decorator for convenience

### Documentation
- ✅ `STATIC_WEBSITE_STACK_CONFIGURATION.md` - Updated with omit section approach
- ✅ `samples/static-website-cdn-only-sample.json` - Shows cleaner approach
- ✅ `config-00-stage-01-cdn.json` - Your project config updated

### Key Documentation Updates

1. **Special Case section added:**
   > If the entire `assets` configuration is omitted, the stack defaults to **CDN-only mode** (no asset deployment).

2. **Behavior section updated:**
   > When **assets section omitted entirely** (recommended for CDN-only):
   > - No asset deployment
   > - CloudFront serves existing bucket content
   > - Cleanest configuration approach

3. **Examples updated:**
   - Shows both explicit `deploy=false` and omitted section approaches
   - Recommends omitting for cleaner configs

## Benefits

### Cleaner Configuration
```json
// Before: 5 lines
"assets": {
  "deploy": false,
  "enable_versioning": false
},

// After: 0 lines (just omit it!)
```

### More Intuitive
- "No assets section" clearly means "no asset deployment"
- Less configuration = less confusion
- Self-documenting intent

### Backward Compatible
- ✅ All existing configurations still work
- ✅ Both approaches supported (omit or explicit `deploy=false`)
- ✅ No breaking changes

## Implementation Details

### Logic Flow

```python
# 1. Get assets config (may be None)
assets_config = stack_config.dictionary.get("assets")

# 2. Check if section provided
if assets_config:
    # Section provided - use configured values
    deploy_assets = assets_config.get("deploy", True)
    enable_versioning = assets_config.get("enable_versioning", True)
else:
    # Section omitted - default to CDN-only mode
    deploy_assets = False
    enable_versioning = False
```

### Logging

The stack provides clear logging for each scenario:

```
# When assets section omitted:
[INFO] No assets configuration found - skipping asset path resolution

# When deploy=false:
[INFO] Asset deployment disabled - skipping asset path resolution

# When deploying assets:
[INFO] Deploying assets from /path/to/www to S3
```

## Use Cases

### Traditional Website
```json
{
  "assets": {
    "deploy": true,
    "enable_versioning": true,
    "path": "www"
  }
}
```
Still requires explicit configuration.

### CDN-Only Distribution
```json
{
  // Just omit the entire assets section!
  "bucket": {"create": false, "name": "existing-bucket"}
}
```
Cleaner, more obvious intent.

### No Versioning
```json
{
  "assets": {
    "deploy": true,
    "enable_versioning": false,
    "path": "www"
  }
}
```
Still requires explicit configuration when deploying.

## Migration

### No Migration Required!

Both approaches work:
- ✅ Omit `assets` section (recommended for CDN-only)
- ✅ Set `"deploy": false` (still supported)

Choose whichever is clearer for your use case.

## Testing

```bash
✅ 353 tests passed
✅ No breaking changes
✅ Import validation passed
```

## Recommendation

**For CDN-only distributions:** Omit the entire `assets` section - it's cleaner and more intuitive.

**For asset deployment:** Continue using explicit `assets` configuration with `deploy: true`.

---

**Updated:** November 18, 2025  
**Version:** 0.39.0  
**Breaking Changes:** None  
**Migration Required:** No (optional cleanup)
