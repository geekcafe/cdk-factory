# Static Website Stack v0.39.0 Release Notes

## Overview

Extended `StaticWebSiteStack` with flexible configuration options to support CDN-only deployments, traditional static websites, and hybrid scenarios - all from the same stack module.

## New Features

### 1. Optional Bucket Creation

**Before:** Always created a new S3 bucket  
**After:** Can use existing buckets via import

```json
{
  "bucket": {
    "create": false,              // Don't create, use existing
    "name": "my-existing-bucket"  // Import by name
  }
}
```

**Use Cases:**
- CDN distributions serving existing buckets
- Shared buckets across multiple distributions
- Buckets managed by separate stacks or processes

### 2. Optional Asset Deployment

**Before:** Always deployed assets from source directory  
**After:** Asset deployment is optional

```json
{
  "assets": {
    "deploy": false,              // Skip asset deployment
    "enable_versioning": false    // No version directories
  }
}
```

**Use Cases:**
- CDN distributions where content is managed separately
- Buckets populated by application CI/CD pipelines
- Content uploaded manually or via other processes

### 3. Optional Versioning

**Before:** Always used versioned subdirectories  
**After:** Versioning can be disabled

```json
{
  "assets": {
    "deploy": true,
    "enable_versioning": false,   // Deploy to bucket root
    "path": "www"
  }
}
```

**Use Cases:**
- Simple deployments without rollback requirements
- Applications that manage versioning differently
- Buckets with single "live" content set

### 4. Optional CloudFront Invalidation

**Before:** Always invalidated CloudFront on deployment  
**After:** Invalidation can be disabled

```json
{
  "cloudfront": {
    "invalidate_on_deploy": false  // No automatic invalidation
  }
}
```

**Use Cases:**
- CDN-only distributions without asset deployment
- Faster deployments when cache invalidation not needed
- Manual invalidation triggered by other processes

## Backward Compatibility

✅ **100% Backward Compatible**

All existing configurations work without changes:
- Default behavior unchanged (create bucket, deploy versioned assets, invalidate cache)
- Legacy `src.path` still supported as fallback
- All new options default to previous behavior

## Configuration Examples

### Traditional Static Website (Unchanged)
```json
{
  "name": "website",
  "module": "static_website_stack",
  "src": {"path": "www"},
  "dns": {...},
  "cert": {...}
}
```
**Result:** Same behavior as before - creates bucket, deploys versioned assets, invalidates cache

### CDN-Only Distribution (NEW)
```json
{
  "name": "cdn",
  "module": "static_website_stack",
  "bucket": {"create": false, "name": "existing-bucket"},
  "assets": {"deploy": false},
  "cloudfront": {"invalidate_on_deploy": false},
  "dns": {"aliases": ["cdn.example.com"]},
  "cert": {"domain_name": "cdn.example.com"}
}
```
**Result:** CloudFront distribution only - no bucket creation or asset deployment

### Hybrid: Existing Bucket, Deploy Assets (NEW)
```json
{
  "name": "app",
  "module": "static_website_stack",
  "bucket": {"create": false, "name": "shared-bucket"},
  "assets": {"deploy": true, "enable_versioning": false, "path": "build"},
  "dns": {...}
}
```
**Result:** Uses existing bucket but deploys assets to it (non-versioned)

## Files Created

### Implementation
- ✅ Updated `/src/cdk_factory/stack_library/websites/static_website_stack.py`
  - Added optional bucket creation logic
  - Added optional asset deployment logic
  - Added optional versioning logic
  - Added optional CloudFront invalidation logic

### Documentation
- ✅ `/docs/STATIC_WEBSITE_STACK_CONFIGURATION.md` - Comprehensive configuration guide
- ✅ `/samples/static-website-cdn-only-sample.json` - CDN-only example
- ✅ `/samples/static-website-traditional-sample.json` - Traditional website example
- ✅ `/samples/static-website-hybrid-sample.json` - Hybrid deployment example

### Project Configurations
- ✅ `/source-code/trav-talks-real-estate-iac/config-00-main.json` - CDN pipeline config
- ✅ `/source-code/trav-talks-real-estate-iac/config-00-stage-01-cdn.json` - CDN stack config

## Implementation Details

### Bucket Creation Logic
```python
if bucket_config.get("create", True):
    # Create new bucket (default)
    construct = S3BucketConstruct(...)
else:
    # Import existing bucket
    if bucket_name:
        return s3.Bucket.from_bucket_name(...)
    elif bucket_arn:
        return s3.Bucket.from_bucket_arn(...)
```

### Asset Deployment Logic
```python
deploy_assets = assets_config.get("deploy", True)
enable_versioning = assets_config.get("enable_versioning", True)

if deploy_assets and assets_path:
    deployment_kwargs = {...}
    
    if enable_versioning:
        deployment_kwargs["destination_key_prefix"] = version
    
    if invalidate_on_deploy:
        deployment_kwargs["distribution"] = distribution
        deployment_kwargs["distribution_paths"] = ["/*"]
    
    aws_s3_deployment.BucketDeployment(**deployment_kwargs)
```

## Validation

### Tests
```
✅ 353 tests passed
⏭️  5 skipped
⚠️  1 warning
```

### Syntax Validation
```
✅ Python import successful
✅ Type hints valid
✅ No runtime errors
```

## Migration Path

### Existing Deployments
No action required - all existing configurations continue to work as-is.

### New CDN Deployments
1. Set `bucket.create=false` and provide existing bucket name
2. Set `assets.deploy=false` to skip asset deployment
3. Set `cloudfront.invalidate_on_deploy=false` for faster deploys
4. Configure DNS and certificate as usual

### Gradual Adoption
- Can migrate existing static websites one at a time
- Mix traditional and CDN-only deployments in same pipeline
- Test new options in development before production

## Benefits

### Flexibility
- ✅ Single stack supports multiple use cases
- ✅ No need for separate stack types
- ✅ Gradual adoption of new features

### Maintainability
- ✅ One codebase to maintain
- ✅ Consistent behavior across use cases
- ✅ Shared bug fixes and improvements

### Developer Experience
- ✅ Clear configuration options
- ✅ Comprehensive documentation
- ✅ Helpful logging messages
- ✅ Sample configurations provided

## Breaking Changes

**None** - 100% backward compatible with v0.38.0 and earlier

## Known Limitations

1. **Bucket Permissions:** When using existing bucket, ensure CDK has proper IAM permissions
2. **Version File:** When versioning enabled, requires `version.txt` in assets directory
3. **CloudFront Region:** Certificates must be in `us-east-1` (handled automatically)

## Future Enhancements

Potential future additions:
- Support for Lambda@Edge functions
- Custom origin configurations
- Multiple origins
- Behavior path patterns
- Custom error pages

## Support

- **Documentation:** `/docs/STATIC_WEBSITE_STACK_CONFIGURATION.md`
- **Samples:** `/samples/static-website-*.json`
- **Issues:** Create GitHub issue with `static_website_stack` label

---

**Version:** 0.39.0  
**Release Date:** November 18, 2025  
**Breaking Changes:** None  
**Migration Required:** No
