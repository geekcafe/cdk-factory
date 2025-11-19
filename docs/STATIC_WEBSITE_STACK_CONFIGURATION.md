# Static Website Stack Configuration Guide

**Version:** 0.39.0  
**Module:** `static_website_stack`  
**Stack Class:** `StaticWebSiteStack`

## Overview

The Static Website Stack provides flexible deployment options for CloudFront distributions, supporting multiple use cases from traditional static websites to CDN-only distributions.

## Use Cases

### 1. Traditional Static Website (Default Behavior)
Create bucket, deploy versioned assets, CloudFront distribution, and optional DNS/certificate.

### 2. CDN-Only Distribution
Use existing bucket, skip asset deployment, create CloudFront distribution and certificate.

### 3. Hybrid Deployment
Use existing bucket but deploy assets to it, with optional versioning.

---

## Configuration Options

### Bucket Configuration

Controls S3 bucket creation and usage.

```json
{
  "bucket": {
    "create": true,              // Create new bucket (default: true)
    "name": "existing-bucket",   // Import existing bucket by name
    "import_arn": "arn:..."      // Or import by ARN
  }
}
```

**Options:**
- `create` (boolean, default: `true`) - Whether to create a new bucket
- `name` (string, conditional) - Existing bucket name to import (required if `create=false`)
- `import_arn` (string, alternative) - Existing bucket ARN to import (alternative to `name`)

**Behavior:**
- When `create=true` (default): Creates new S3 bucket using `S3BucketConstruct`
- When `create=false`: Imports existing bucket by name or ARN
- Must provide either `name` or `import_arn` when `create=false`

**Example - Create New Bucket (Default):**
```json
{
  "bucket": {
    "create": true
  }
}
```

**Example - Use Existing Bucket:**
```json
{
  "bucket": {
    "create": false,
    "name": "my-cdn-assets-bucket"
  }
}
```

---

### Assets Configuration

Controls asset deployment, versioning, and source path.

```json
{
  "assets": {
    "deploy": true,               // Deploy assets (default: true if section present)
    "enable_versioning": true,    // Version assets (default: true if section present)
    "path": "www"                 // Path to assets directory
  }
}
```

**Options:**
- `deploy` (boolean, default: `true` if assets section present) - Whether to deploy assets to S3
- `enable_versioning` (boolean, default: `true` if assets section present) - Use version subdirectories
- `path` (string, conditional) - Path to assets directory (required if `deploy=true`)

**Special Case - Omit Entire Section:**
If the entire `assets` configuration is omitted, the stack defaults to **CDN-only mode** (no asset deployment). This is equivalent to `{"assets": {"deploy": false}}`.

**Behavior:**
- When **assets section omitted entirely** (recommended for CDN-only):
  - No asset deployment
  - CloudFront serves existing bucket content
  - Cleanest configuration approach

- When `deploy=true` and `enable_versioning=true`:
  - Reads `version.txt` from assets directory
  - Deploys to `s3://bucket/{version}/`
  - CloudFront origin points to versioned subdirectory
  
- When `deploy=true` and `enable_versioning=false`:
  - Deploys to bucket root
  - CloudFront origin points to bucket root
  - No version subdirectories
  
- When `deploy=false` (explicit):
  - Skips asset deployment entirely
  - CloudFront serves whatever exists in bucket
  - `path` not required
  - Alternative to omitting section

**Legacy Support:**
- Still supports `src.path` as fallback for backward compatibility
- Prefer `assets.path` for new configurations

**Example - Traditional Versioned Deployment:**
```json
{
  "assets": {
    "deploy": true,
    "enable_versioning": true,
    "path": "www"
  }
}
```

**Example - Non-Versioned Deployment:**
```json
{
  "assets": {
    "deploy": true,
    "enable_versioning": false,
    "path": "www"
  }
}
```

**Example - CDN-Only (No Deployment - Explicit):**
```json
{
  "assets": {
    "deploy": false,
    "enable_versioning": false
  }
}
```

**Example - CDN-Only (No Deployment - Omit Section):**
```json
{
  // Simply omit the entire "assets" section
  // This is the cleanest approach for CDN-only distributions
}
```

---

### CloudFront Configuration

Controls CloudFront distribution behavior.

```json
{
  "cloudfront": {
    "invalidate_on_deploy": true,      // Invalidate on deploy
    "restrict_to_known_hosts": true    // Restrict to configured aliases
  }
}
```

**Options:**
- `invalidate_on_deploy` (boolean, default: same as `assets.deploy`) - Trigger CloudFront invalidation
- `restrict_to_known_hosts` (boolean, default: `true`) - Restrict access to configured domain aliases

**Behavior:**
- When `invalidate_on_deploy=true`:
  - Triggers CloudFront cache invalidation on deployment
  - Deployment takes ~5 minutes to complete
  - All paths (`/*`) are invalidated
  
- When `invalidate_on_deploy=false`:
  - No automatic invalidation
  - Faster deployments
  - Cache must be cleared manually or wait for TTL expiration

**Default Logic:**
- Defaults to `true` when `assets.deploy=true`
- Defaults to `false` when `assets.deploy=false`

**Example - Enable Invalidation:**
```json
{
  "cloudfront": {
    "invalidate_on_deploy": true,
    "restrict_to_known_hosts": true
  }
}
```

**Example - Disable Invalidation:**
```json
{
  "cloudfront": {
    "invalidate_on_deploy": false,
    "restrict_to_known_hosts": false
  }
}
```

---

### DNS Configuration

Controls custom domain configuration and Route53 records.

```json
{
  "dns": {
    "hosted_zone_id": "Z1234567890ABC",
    "hosted_zone_name": "example.com",
    "aliases": [
      "cdn.example.com",
      "www.cdn.example.com"
    ]
  }
}
```

**Options:**
- `hosted_zone_id` (string, optional) - Route53 hosted zone ID
- `hosted_zone_name` (string, required if `hosted_zone_id` provided) - Hosted zone domain name
- `aliases` (array, required if `hosted_zone_id` provided) - Domain aliases for CloudFront

**Behavior:**
- When DNS configured: Creates Route53 A records pointing to CloudFront distribution
- When DNS omitted: CloudFront uses default `*.cloudfront.net` domain
- Requires certificate when using custom domains

---

### Certificate Configuration

Controls SSL/TLS certificate creation.

```json
{
  "cert": {
    "domain_name": "cdn.example.com",
    "alternate_names": [
      "*.cdn.example.com"
    ]
  }
}
```

**Options:**
- `domain_name` (string, required if DNS configured) - Primary domain for certificate
- `alternate_names` (array, optional) - Additional domains (SANs)

**Behavior:**
- Certificate created in `us-east-1` region (CloudFront requirement)
- Validated using DNS validation with Route53
- Supports wildcards and multiple SANs

---

### SSM Parameter Exports

Controls SSM Parameter Store exports for cross-stack references.

```json
{
  "ssm": {
    "exports": {
      "bucket_name": "/prod/app/cdn/bucket-name",
      "cloudfront_domain": "/prod/app/cdn/domain",
      "cloudfront_distribution_id": "/prod/app/cdn/distribution-id",
      "dns_alias": "/prod/app/cdn/alias"
    }
  }
}
```

**Available Exports:**
- `bucket_name` - S3 bucket name
- `cloudfront_domain` - CloudFront distribution domain (e.g., `d123.cloudfront.net` or custom domain)
- `cloudfront_distribution_id` - CloudFront distribution ID (for invalidations)
- `dns_alias` - Primary DNS alias (first in aliases list)

**Use Cases:**
- Application reads CDN domain for asset URLs
- Other stacks trigger CloudFront invalidations
- Monitoring/logging references distribution ID

---

## Complete Examples

### Example 1: Traditional Static Website

Full-featured static website with versioned assets.

```json
{
  "name": "prod-myapp-website",
  "module": "static_website_stack",
  "enabled": true,
  
  "bucket": {
    "create": true
  },
  
  "assets": {
    "deploy": true,
    "enable_versioning": true,
    "path": "www"
  },
  
  "cloudfront": {
    "invalidate_on_deploy": true,
    "restrict_to_known_hosts": true
  },
  
  "dns": {
    "hosted_zone_id": "Z1234567890ABC",
    "hosted_zone_name": "example.com",
    "aliases": [
      "www.example.com",
      "example.com"
    ]
  },
  
  "cert": {
    "domain_name": "*.example.com",
    "alternate_names": ["example.com"]
  },
  
  "ssm": {
    "exports": {
      "bucket_name": "/prod/myapp/website/bucket-name",
      "cloudfront_domain": "/prod/myapp/website/domain",
      "cloudfront_distribution_id": "/prod/myapp/website/distribution-id"
    }
  }
}
```

### Example 2: CDN-Only Distribution

CloudFront distribution for existing S3 bucket without asset deployment.

```json
{
  "name": "prod-myapp-cdn",
  "module": "static_website_stack",
  "enabled": true,
  
  "bucket": {
    "create": false,
    "name": "prod-myapp-cdn-assets"
  },
  
  "_note": "Assets section omitted - enables CDN-only mode (no deployment)",
  
  "cloudfront": {
    "invalidate_on_deploy": false,
    "restrict_to_known_hosts": true
  },
  
  "dns": {
    "hosted_zone_id": "Z1234567890ABC",
    "hosted_zone_name": "example.com",
    "aliases": [
      "cdn.example.com"
    ]
  },
  
  "cert": {
    "domain_name": "cdn.example.com"
  },
  
  "ssm": {
    "exports": {
      "cloudfront_domain": "/prod/myapp/cdn/domain",
      "cloudfront_distribution_id": "/prod/myapp/cdn/distribution-id",
      "dns_alias": "/prod/myapp/cdn/alias"
    }
  }
}
```

### Example 3: Hybrid Deployment

Use existing bucket but deploy non-versioned assets.

```json
{
  "name": "prod-myapp-app",
  "module": "static_website_stack",
  "enabled": true,
  
  "bucket": {
    "create": false,
    "name": "shared-assets-bucket"
  },
  
  "assets": {
    "deploy": true,
    "enable_versioning": false,
    "path": "build/app"
  },
  
  "cloudfront": {
    "invalidate_on_deploy": true,
    "restrict_to_known_hosts": false
  },
  
  "dns": {
    "hosted_zone_id": "Z1234567890ABC",
    "hosted_zone_name": "example.com",
    "aliases": [
      "app.example.com"
    ]
  },
  
  "cert": {
    "domain_name": "app.example.com"
  }
}
```

---

## Migration Guide

### From Legacy Configuration

**Old (Legacy):**
```json
{
  "name": "website",
  "module": "static_website_stack",
  "src": {
    "path": "www"
  },
  "dns": {...},
  "cert": {...}
}
```

**New (Recommended):**
```json
{
  "name": "website",
  "module": "static_website_stack",
  "assets": {
    "deploy": true,
    "enable_versioning": true,
    "path": "www"
  },
  "dns": {...},
  "cert": {...}
}
```

**Note:** Legacy `src.path` still works as fallback but prefer `assets.path`.

---

## Validation Rules

The stack validates configuration at runtime:

1. **When `bucket.create=false`**:
   - Must provide `bucket.name` OR `bucket.import_arn`
   - Cannot provide both

2. **When `assets.deploy=true`**:
   - Must provide `assets.path` or legacy `src.path`
   - Path must exist and be accessible

3. **When DNS configured**:
   - Must provide both `hosted_zone_id` and `hosted_zone_name`
   - Must provide `dns.aliases` (non-empty array)
   - Should provide `cert.domain_name` for custom domains

---

## Logging

The stack logs configuration decisions:

```
[INFO] Creating new S3 bucket for website
[INFO] 👉 WEBSITE VERSION NUMBER: 1.2.3
[INFO] Deploying assets from /path/to/www to S3
[INFO] CloudFront invalidation enabled - deployment will take ~5 minutes
```

```
[INFO] Importing existing S3 bucket by name: my-cdn-bucket
[INFO] Asset deployment disabled - skipping asset path resolution
[INFO] 👉 Asset deployment disabled - CloudFront will serve existing bucket content
[INFO] Skipping asset deployment - using existing bucket content
[INFO] CloudFront invalidation disabled
```

---

## Best Practices

### CDN-Only Distributions
- Set `assets.deploy=false` to avoid dependency on source code
- Set `cloudfront.invalidate_on_deploy=false` for faster deployments
- Manage bucket content separately (application CI/CD, manual upload, etc.)
- Export `cloudfront_distribution_id` to SSM for manual invalidations

### Traditional Static Websites
- Keep `assets.deploy=true` and `enable_versioning=true` for rollback capability
- Use `version.txt` file in assets directory for version tracking
- Enable `invalidate_on_deploy=true` for immediate cache updates

### Shared Buckets
- Use `bucket.create=false` to reference shared infrastructure
- Consider IAM permissions for bucket access
- Use prefixes or separate paths to avoid conflicts

### Security
- Enable `restrict_to_known_hosts=true` to prevent hotlinking
- Use CloudFront OAC (Origin Access Control) for S3 access
- Implement proper bucket policies

---

## Troubleshooting

### "Source path is required" Error
**Cause:** `assets.deploy=true` but no path provided  
**Solution:** Set `assets.path` or `src.path`, or set `assets.deploy=false`

### "When bucket.create=false, must provide..." Error
**Cause:** Trying to use existing bucket without specifying name or ARN  
**Solution:** Add `bucket.name` or `bucket.import_arn`

### Bucket Not Found
**Cause:** Referenced bucket doesn't exist or no permissions  
**Solution:** Verify bucket exists and CDK has permissions to access it

### Certificate Validation Timeout
**Cause:** DNS validation records not created or propagated  
**Solution:** Verify Route53 hosted zone is correct and DNS is propagating

---

## Related Stacks

- **S3 Bucket Stack** - Create buckets separately for CDN-only use case
- **Route53 Stack** - Manage DNS separately from CloudFront
- **ACM Stack** - Create certificates separately if needed

---

## Version History

- **v0.39.0** - Added optional bucket creation, asset deployment, and versioning flags
- **Earlier** - Traditional static website deployment only

---

## See Also

- [CloudFront Distribution Construct Documentation](../constructs/cloudfront/)
- [S3 Bucket Construct Documentation](../constructs/s3/)
- [Sample Configurations](../samples/)
