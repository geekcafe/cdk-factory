# CloudFront Function Associations Management

## Overview

CloudFront has strict limits on function associations:
- **1 CloudFront Function** per event type per cache behavior
- **1 Lambda@Edge** per event type per cache behavior

This document explains how to manage function associations safely.

## Function Association Types

### CloudFront Functions (JavaScript, lightweight)
- Execution time: <1ms
- Max size: 10KB
- Use cases: Simple transformations, header manipulation
- Cost: $0.10 per 1M invocations

### Lambda@Edge (Python/Node, full Lambda)
- Execution time: Up to 5 seconds (viewer-request/response) or 30 seconds (origin-request/response)
- Max size: 50MB
- Use cases: Complex logic, external API calls, IP validation
- Cost: $0.60 per 1M invocations + duration charges

## Configuration Options That Create Functions

### cdk-factory Configuration Mapping

| Config Option | Creates | Function Type | Event Type |
|--------------|---------|---------------|------------|
| `enable_url_rewrite: true` | URL rewrite function | CloudFront Function | viewer-request |
| `restrict_to_known_hosts: true` | Host restriction function | CloudFront Function | viewer-request |
| `enable_ip_gating: true` | IP gating function | Lambda@Edge | viewer-request |
| Both `enable_url_rewrite` + `restrict_to_known_hosts` | Combined function | CloudFront Function | viewer-request |

### Valid Combinations

✅ **These work together** (different function types at same event):
```json
{
  "cloudfront": {
    "enable_url_rewrite": true,        // CloudFront Function
    "enable_ip_gating": true            // Lambda@Edge
  }
}
```

✅ **These are automatically combined** (same function type at same event):
```json
{
  "cloudfront": {
    "enable_url_rewrite": true,        // Combined into one
    "restrict_to_known_hosts": true    // CloudFront Function
  }
}
```

❌ **These conflict** (manual + automatic association):
```json
{
  "cloudfront": {
    "enable_ip_gating": true           // Auto creates viewer-request association
  },
  "lambda_edge": {
    "event_type": "viewer-request"     // Manual association - CONFLICT!
  }
}
```

## Safe Configuration Changes

### Scenario 1: Adding IP Gating to Existing Distribution

**Current:**
```json
{
  "cloudfront": {
    "enable_url_rewrite": true,
    "restrict_to_known_hosts": true
  }
}
```

**Goal:** Add IP gating

**Method 1: Direct (Usually Works)**
```json
{
  "cloudfront": {
    "enable_url_rewrite": true,
    "restrict_to_known_hosts": false,   // ← Disable to avoid complexity
    "enable_ip_gating": true            // ← Add Lambda@Edge
  }
}
```

Deploy once. This should work because:
- URL rewrite: CloudFront Function
- IP gating: Lambda@Edge
- Different function types can coexist

**Method 2: Staged (Safest)**

Step 1: Clear everything
```json
{
  "cloudfront": {
    "enable_url_rewrite": false,
    "restrict_to_known_hosts": false,
    "enable_ip_gating": false
  }
}
```
Deploy → Wait for success

Step 2: Add new features
```json
{
  "cloudfront": {
    "enable_url_rewrite": true,
    "enable_ip_gating": true
  }
}
```
Deploy → Wait for success

### Scenario 2: Changing Lambda@Edge Event Type

**Problem:** You cannot change a Lambda@Edge event type in-place.

**Current:**
```json
{
  "lambda_edge": {
    "event_type": "origin-request"
  }
}
```

**Goal:** Move to viewer-request

**Solution:**

Step 1: Remove Lambda@Edge completely
```json
{
  "lambda_edge": {
    // Remove event_type or set enabled: false
  }
}
```
Deploy → Wait for success

Step 2: Use convenience flag instead
```json
{
  "cloudfront": {
    "enable_ip_gating": true  // Auto creates at viewer-request
  }
}
```
Deploy → Wait for success

### Scenario 3: Switching Response Modes (No Redeploy!)

**Current:** Proxy mode
**Goal:** Redirect mode

**Best practice:** Use SSM parameters for runtime configuration:

```bash
# Change mode without redeploying Lambda@Edge
aws ssm put-parameter \
  --name "/dev/my-app/response-mode" \
  --value "redirect" \
  --overwrite

# Changes take effect in ~5 minutes (SSM cache expiration)
```

No CloudFront update needed!

## Troubleshooting Failed Updates

### Symptom: "Event type must be unique" Error

**Error message:**
```
Event type viewer-request cannot be associated with two functions: 
null and arn:aws:lambda:...
```

**Cause:** CloudFront is stuck trying to remove old function while adding new one.

**Solutions:**

#### Solution 1: Clear and Redeploy (Easiest)

```json
// Step 1: Disable everything
{
  "cloudfront": {
    "enable_url_rewrite": false,
    "restrict_to_known_hosts": false,
    "enable_ip_gating": false
  }
}
```
Deploy → Wait

```json
// Step 2: Enable what you want
{
  "cloudfront": {
    "enable_ip_gating": true
  }
}
```
Deploy → Success

#### Solution 2: Manual AWS CLI Cleanup (If CDK is stuck)

```bash
# 1. Get distribution config
DIST_ID="E3T9ODGTZTLF2N"
aws cloudfront get-distribution-config \
  --id $DIST_ID \
  > dist-config.json

# 2. Save ETag
ETAG=$(cat dist-config.json | jq -r '.ETag')

# 3. Clear function associations
cat dist-config.json | jq '
  .DistributionConfig |
  .DefaultCacheBehavior.FunctionAssociations = {"Quantity": 0} |
  .DefaultCacheBehavior.LambdaFunctionAssociations = {"Quantity": 0}
' > dist-config-clean.json

# 4. Update distribution
aws cloudfront update-distribution \
  --id $DIST_ID \
  --if-match $ETAG \
  --distribution-config file://dist-config-clean.json

# 5. Wait for deployment
aws cloudfront wait distribution-deployed --id $DIST_ID

# 6. Redeploy with CDK
./cdk-deploy-command.sh
```

### Symptom: CloudFront Functions Not Removed

**Cause:** CDK sometimes doesn't properly remove CloudFront Functions when feature flags are disabled.

**Check current state:**
```bash
aws cloudfront get-distribution-config \
  --id E3T9ODGTZTLF2N \
  --query "{
    LambdaEdge: DistributionConfig.DefaultCacheBehavior.LambdaFunctionAssociations.Quantity,
    CloudFrontFunctions: DistributionConfig.DefaultCacheBehavior.FunctionAssociations.Quantity
  }"
```

**Expected after disabling all features:**
```json
{
  "LambdaEdge": 0,
  "CloudFrontFunctions": 0
}
```

If not zero, use manual cleanup (Solution 2 above).

## Best Practices

### 1. Prefer Convenience Flags

✅ **Do this:**
```json
{
  "cloudfront": {
    "enable_ip_gating": true
  }
}
```

❌ **Avoid this:**
```json
{
  "lambda_edge": {
    "event_type": "viewer-request",
    "lambda_arn": "..."
  }
}
```

Why? Convenience flags:
- Handle associations automatically
- Pick the right event type
- Combine functions when needed
- Less error-prone

### 2. Use SSM for Runtime Config

Environment variables that might change → Store in SSM:

```json
{
  "lambda_edge": {
    "environment": {
      "GATE_ENABLED": "true",           // ← Could change
      "RESPONSE_MODE": "proxy",         // ← Could change
      "ALLOW_CIDRS": "1.2.3.4/32"      // ← Could change
    }
  }
}
```

These get exported to SSM automatically. Change them without redeploying:

```bash
aws ssm put-parameter \
  --name "/dev/my-app/gate-enabled" \
  --value "false" \
  --overwrite
```

### 3. Test in Lower Environments

Lambda@Edge is global and takes 20-30 minutes to propagate. Test changes in dev first:

```bash
# Deploy to dev
ENVIRONMENT=dev ./cdk-deploy-command.sh

# Wait 30 minutes, test thoroughly

# Then deploy to prod
ENVIRONMENT=prod ./cdk-deploy-command.sh
```

### 4. Monitor CloudFront Distribution Status

After deploy, verify status:

```bash
# Check distribution status
aws cloudfront get-distribution \
  --id $DIST_ID \
  --query 'Distribution.Status'

# Deployed = ready
# InProgress = still deploying
```

Wait until status is `Deployed` before making more changes.

### 5. Keep Function Logic Simple

**CloudFront Function limits:**
- 10KB max
- <1ms execution time
- No external calls

**Lambda@Edge viewer-request limits:**
- 5 second max
- 1MB response body
- Limited external API calls

If you need heavy processing:
- Use origin-request instead (30 second timeout)
- Or move logic to origin server

## Common Patterns

### Pattern 1: Development Lockdown

Lock dev/staging to specific IPs:

```json
{
  "cloudfront": {
    "enable_ip_gating": true
  },
  "lambda_edge": {
    "environment": {
      "GATE_ENABLED": "true",
      "ALLOW_CIDRS": "203.0.113.0/24",  // Office network
      "RESPONSE_MODE": "redirect"        // Clear denial
    }
  }
}
```

### Pattern 2: Scheduled Maintenance

Show maintenance page to all users:

```json
{
  "cloudfront": {
    "enable_ip_gating": true
  },
  "lambda_edge": {
    "environment": {
      "GATE_ENABLED": "false",           // Disable IP check
      "ALLOW_CIDRS": "",                 // Empty = block all
      "RESPONSE_MODE": "proxy"           // Keep URL same
    }
  }
}
```

Change via SSM at runtime:
```bash
# Enable maintenance mode
aws ssm put-parameter --name "/prod/app/gate-enabled" --value "false" --overwrite

# Disable maintenance mode (site back online)
aws ssm put-parameter --name "/prod/app/gate-enabled" --value "true" --overwrite
```

### Pattern 3: Progressive Rollout

Allow specific IPs during beta:

```json
{
  "lambda_edge": {
    "environment": {
      "GATE_ENABLED": "true",
      "ALLOW_CIDRS": "203.0.113.0/24,198.51.100.0/24",  // Beta users
      "RESPONSE_MODE": "redirect"
    }
  }
}
```

Add more IPs via SSM:
```bash
aws ssm put-parameter \
  --name "/prod/app/allow-cidrs" \
  --value "203.0.113.0/24,198.51.100.0/24,192.0.2.0/24" \
  --overwrite
```

## Migration Checklist

When changing CloudFront function associations:

- [ ] Identify current function associations
- [ ] Check which config options create functions
- [ ] Plan staged rollout if changing event types
- [ ] Use SSM for runtime config changes
- [ ] Test in dev environment first
- [ ] Verify distribution status after deploy
- [ ] Wait 30 minutes for Lambda@Edge propagation
- [ ] Keep manual cleanup commands handy

## Emergency Rollback

If deployment fails and site is down:

```bash
# 1. Disable IP gating immediately via SSM (if Lambda@Edge is deployed)
aws ssm put-parameter \
  --name "/prod/app/gate-enabled" \
  --value "false" \
  --overwrite

# 2. Wait 5 minutes for cache expiration

# 3. If still broken, remove all function associations manually
DIST_ID="..."
aws cloudfront get-distribution-config --id $DIST_ID > dist-config.json
# Edit to remove associations
aws cloudfront update-distribution --id $DIST_ID --if-match $(cat dist-config.json | jq -r '.ETag') --distribution-config file://dist-config-clean.json

# 4. Deploy previous working config with CDK
git checkout previous-working-commit
./cdk-deploy-command.sh
```

## Summary

**Key Takeaways:**

1. **Use convenience flags** over manual associations
2. **Stage changes** when switching event types
3. **Use SSM** for runtime configuration
4. **Test in dev** before prod
5. **Keep cleanup commands** handy for emergencies
6. **Monitor status** after deploys
7. **Wait 30 minutes** after Lambda@Edge changes

**Golden Rule:** When in doubt, clear everything, deploy, then add features one at a time.
