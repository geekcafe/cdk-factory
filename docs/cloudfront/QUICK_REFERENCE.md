# CloudFront Function Associations - Quick Reference

## TL;DR

**Golden Rule:** Clear functions before changing event types, use convenience flags, change runtime config via SSM.

## Quick Commands

### Check Current State
```bash
aws cloudfront get-distribution-config \
  --profile gc-shared \
  --id E3T9ODGTZTLF2N \
  --query "{Lambda: DistributionConfig.DefaultCacheBehavior.LambdaFunctionAssociations.Quantity, CFFunc: DistributionConfig.DefaultCacheBehavior.FunctionAssociations.Quantity}"
```

### Clean Stuck Distribution
```bash
# Automated cleanup script
./scripts/cloudfront-cleanup.sh \
  --distribution-id E3T9ODGTZTLF2N \
  --profile gc-shared

# Or manual
cd /path/to/project/devops
```

Set all to false:
```json
{
  "enable_url_rewrite": false,
  "restrict_to_known_hosts": false,
  "enable_ip_gating": false
}
```

Deploy → Wait → Re-enable what you want

### Change Runtime Config (No Redeploy!)
```bash
# Toggle IP gate on/off
aws ssm put-parameter \
  --name "/dev/my-app/gate-enabled" \
  --value "false" \
  --overwrite

# Switch response mode
aws ssm put-parameter \
  --name "/dev/my-app/response-mode" \
  --value "redirect" \
  --overwrite

# Changes take effect in ~5 minutes (SSM cache)
```

## Config Patterns

### ✅ Safe: Different Function Types
```json
{
  "cloudfront": {
    "enable_url_rewrite": true,      // CloudFront Function
    "enable_ip_gating": true          // Lambda@Edge
  }
}
```

### ✅ Safe: Auto-Combined
```json
{
  "cloudfront": {
    "enable_url_rewrite": true,       // Combined into
    "restrict_to_known_hosts": true   // one CloudFront Function
  }
}
```

### ❌ Conflict: Duplicate Event Type
```json
{
  "cloudfront": {
    "enable_ip_gating": true          // Auto viewer-request
  },
  "lambda_edge": {
    "event_type": "viewer-request"    // Manual viewer-request - CONFLICT!
  }
}
```

## Safe Change Process

### Scenario: Enable IP Gating on Existing Distribution

**Method 1: Direct (Usually Works)**
```json
{
  "cloudfront": {
    "restrict_to_known_hosts": false,   // Disable to keep it simple
    "enable_ip_gating": true
  }
}
```
Deploy once

**Method 2: Staged (Safest)**

Step 1:
```json
{"enable_url_rewrite": false, "restrict_to_known_hosts": false, "enable_ip_gating": false}
```
Deploy → Wait

Step 2:
```json
{"enable_ip_gating": true}
```
Deploy → Wait

Step 3 (optional):
```json
{"enable_url_rewrite": true, "enable_ip_gating": true}
```

## Troubleshooting

### Error: "Event type must be unique"

**Quick Fix:**
```bash
# 1. Use cleanup script
./scripts/cloudfront-cleanup.sh --distribution-id <ID> --profile <PROFILE>

# 2. Redeploy with CDK
cd devops && ./cdk-deploy-command.sh
```

### Lambda@Edge Not Running

**Check event type:**
```bash
aws cloudfront get-distribution-config \
  --id <DIST_ID> \
  --query "DistributionConfig.DefaultCacheBehavior.LambdaFunctionAssociations.Items[].EventType"
```

Must be `viewer-request` for IP gating (runs before cache).

### Changes Not Taking Effect

**Lambda@Edge:** Wait 20-30 minutes for global propagation  
**CloudFront Function:** Takes effect in ~1 minute  
**SSM Parameters:** Cache expires in ~5 minutes

## Emergency Rollback

```bash
# 1. Disable via SSM (immediate)
aws ssm put-parameter --name "/prod/app/gate-enabled" --value "false" --overwrite

# 2. If that doesn't work, clear all functions
./scripts/cloudfront-cleanup.sh --distribution-id <ID> --profile <PROFILE>

# 3. Redeploy previous config
git checkout <previous-commit>
./cdk-deploy-command.sh
```

## Best Practices Checklist

- [ ] Use convenience flags (`enable_ip_gating`) not manual associations
- [ ] Store changing config in SSM parameters
- [ ] Test in dev before prod
- [ ] Stage changes when modifying event types
- [ ] Wait for "Deployed" status before next change
- [ ] Keep cleanup script handy
- [ ] Monitor CloudWatch logs during changes

## Function Association Limits

| Event Type | CloudFront Functions | Lambda@Edge |
|-----------|---------------------|-------------|
| viewer-request | 1 | 1 |
| viewer-response | 1 | 1 |
| origin-request | 0 | 1 |
| origin-response | 0 | 1 |

**Can have**: 1 CloudFront Function + 1 Lambda@Edge at same event  
**Cannot have**: 2 of same type at same event

## See Also

- [Full Function Associations Guide](./function-associations.md)
- [IP Gating Setup](../ip-gating/implementation.md)
- [Response Modes](../ip-gating/response-modes.md)
