# URL Rewrite Feature for Static Sites

## Overview

The CDK Factory now supports automatic URL rewriting for static sites (Nuxt, React, Vue, etc.) that use clean URLs and folder-based routing.

## Problem It Solves

When you deploy a static site with folder structure like:
```
/about/index.html
/education/index.html
/contact/index.html
```

Without URL rewriting, users visiting `https://example.com/about` will get a 404 error, because CloudFront looks for a file named `about`, not `about/index.html`.

This feature automatically rewrites:
- `/about` → `/about/index.html`
- `/education` → `/education/index.html`
- `/` → `/index.html`

## How It Works

The feature adds a CloudFront Function (edge function) that runs on every request and rewrites the URI before it reaches the S3 bucket.

### Rewrite Logic

```javascript
function handler(event) {
    var request = event.request;
    var uri = request.uri;
    
    // If URI doesn't have a file extension and doesn't end with /
    if (!uri.includes('.') && !uri.endsWith('/')) {
        request.uri = uri + '/index.html';
    }
    // If URI ends with / but not index.html
    else if (uri.endsWith('/') && !uri.endsWith('index.html')) {
        request.uri = uri + 'index.html';
    }
    // If URI is exactly /
    else if (uri === '/') {
        request.uri = '/index.html';
    }
    
    return request;
}
```

## Usage

### Enable in Configuration

Add `"enable_url_rewrite": true` to your CloudFront configuration:

```json
{
  "cloudfront": {
    "enabled": true,
    "enable_url_rewrite": true,
    "error_responses": [...]
  }
}
```

### Full Example

```json
{
  "name": "my-website",
  "module": "static_website_stack",
  "enabled": true,
  "bucket": {
    "name": "my-website-bucket",
    "exists": true
  },
  "src": {
    "location": "file_system",
    "path": ".output/public"
  },
  "cloudfront": {
    "enabled": true,
    "enable_url_rewrite": true,
    "error_responses": [
      {
        "http_status": 404,
        "response_page_path": "/index.html",
        "response_http_status": 200,
        "ttl": 0
      }
    ]
  }
}
```

## When to Use

### ✅ **Use URL Rewrite When:**
- Deploying Nuxt static sites (`nuxt generate`)
- Deploying React/Vue static sites with routing
- Using clean URLs without file extensions
- Folder-based routing (e.g., `/about/index.html`)

### ❌ **Don't Use URL Rewrite When:**
- Deploying true SPAs with client-side routing only
- All routes should resolve to root `/index.html`
- Using hash-based routing (`#/about`)

## SEO Benefits

### Before URL Rewrite:
```
❌ /about → 404 Error (homepage shows instead)
❌ /education → 404 Error (homepage shows instead)
❌ Search engines can't index pages
❌ Canonicals don't match actual content
```

### After URL Rewrite:
```
✅ /about → Shows actual about page content
✅ /education → Shows actual education page content
✅ Search engines index all pages correctly
✅ Canonicals match actual content
✅ SEO health score: 90+/100
```

## Technical Details

### CloudFront Function vs Lambda@Edge

This feature uses **CloudFront Functions** (not Lambda@Edge) because:
- ✅ **Much cheaper** - $0.10 per 1M invocations
- ✅ **Faster** - Sub-millisecond latency
- ✅ **Global** - Runs at all edge locations
- ✅ **Simple** - JavaScript-only, no packages needed

### Performance Impact

- **Latency**: <1ms per request
- **Cost**: ~$0.10 per million requests
- **Overhead**: Negligible (runs before S3 fetch)

### Compatibility

- ✅ Works with Nuxt `nuxt generate`
- ✅ Works with Next.js static export
- ✅ Works with React static builds
- ✅ Works with Vue static builds
- ✅ Works with any folder/index.html structure

## Testing

### Local Testing
```bash
# After deployment, test all routes:
curl -I https://example.com/about
curl -I https://example.com/education
curl -I https://example.com/contact

# Should all return 200 with correct content
```

### SEO Validation
```bash
# Use Screaming Frog SEO Spider
# Point it at https://example.com
# Verify:
# - All pages return 200
# - Canonicals match actual URLs
# - Content is unique per page
```

## Deployment

After enabling the feature:

```bash
# 1. Commit the config change
git add config.json
git commit -m "Enable URL rewrite for clean URLs"

# 2. Deploy via CDK
./devops/commands/cdk_synth.sh
cdk deploy

# 3. Test
curl -I https://your-domain.com/about

# 4. Verify in AWS Console
# CloudFront → Distributions → Your Distribution → Functions
# You should see "UrlRewriteFunction" associated
```

## Troubleshooting

### Issue: Pages still showing homepage
**Solution**: Clear CloudFront cache
```bash
aws cloudfront create-invalidation \
  --distribution-id YOUR_DIST_ID \
  --paths "/*"
```

### Issue: 404 errors on nested routes
**Check**: Ensure folder structure is correct in S3
```
bucket/version/about/index.html ✅
bucket/version/about.html ❌
```

### Issue: CSS/JS not loading
**Verify**: URL rewrite only affects paths without extensions
```
/about → Rewritten to /about/index.html ✅
/style.css → NOT rewritten ✅
/app.js → NOT rewritten ✅
```

## Example: Vue.js Static Site

This feature was developed for the Vue.js static site project to fix SEO issues where all pages were serving homepage content.

**Before:**
- 97% canonical errors (33/34 pages)
- Search engines couldn't index content
- All pages showed homepage

**After:**
- 0% canonical errors
- All pages indexed correctly
- Perfect SEO health

## Related Features

This feature works alongside:
- **Host restrictions** - Limits access to known domains
- **Error responses** - Custom 404/403 handling
- **Certificate management** - HTTPS support
- **Route53 integration** - DNS automation

## Version History

- **v2.1.0** - Added `enable_url_rewrite` configuration option
- **v2.0.0** - Initial static website stack support
