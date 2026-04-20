# IP Gating Response Modes

## Overview

The Lambda@Edge IP gating function supports two response modes when an IP address is not in the allow-list:

1. **Redirect Mode** (default) - HTTP 302 redirect to maintenance site
2. **Proxy Mode** - Fetch and return maintenance content, keep URL the same

## Response Mode Comparison

| Feature | Redirect Mode | Proxy Mode |
|---------|---------------|------------|
| **URL behavior** | Changes to maintenance domain | Stays on original domain |
| **User experience** | Clear they've been redirected | Seamless, looks like original site |
| **Performance** | ~1-2ms (just redirect header) | ~50-200ms (fetch + proxy) |
| **Cost** | Minimal ($0.60/1M requests) | Slightly higher (data transfer) |
| **Lambda execution time** | 1-5ms | 50-500ms |
| **Best for** | Lockdown/security | Maintenance windows |
| **Refresh behavior** | Stays on maintenance site | Refreshing checks live site |

## Use Cases

### Redirect Mode (Default)

**Best for: IP-based lockdown / security restrictions**

```
User visits site → Lambda checks IP → Not allowed → 302 redirect
URL changes to: https://maintenance-site.cloudfront.net
```

**When to use:**
- ✅ **Development/staging lockdown** - Clear you're not authorized
- ✅ **Beta access control** - Obvious you're outside allowed network
- ✅ **Security restrictions** - Transparent access denial
- ✅ **Partner portals** - Clear separation of access

**Pros:**
- Fast (1-2ms Lambda execution)
- Cheap (minimal compute)
- Transparent (user knows they're blocked)
- Simple implementation

**Cons:**
- URL changes (user sees redirect)
- Requires separate maintenance site

### Proxy Mode

**Best for: Scheduled maintenance windows**

```
User visits site → Lambda checks IP → Not allowed → Fetch maintenance content → Return HTML
URL stays: https://your-site.cloudfront.net
```

**When to use:**
- ✅ **Scheduled maintenance** - Users can refresh to check if site is back
- ✅ **Deployment windows** - Seamless maintenance page
- ✅ **Site updates** - Keep users on your domain
- ✅ **Testing** - Easier to test both modes

**Pros:**
- URL stays the same (better UX for maintenance)
- Users can refresh to check when site is live again
- Seamless experience
- No separate domain needed

**Cons:**
- Slower (50-200ms Lambda execution)
- More expensive (data transfer through Lambda)
- Larger Lambda package (urllib3)
- Potential timeout risk (5-second viewer-request limit)

## Configuration

### Option 1: SSM Parameter (Recommended)

Set the response mode via SSM Parameter Store (no redeployment required):

```bash
# Use redirect mode (default)
aws ssm put-parameter \
  --name "/dev/my-app-ip-gate/response-mode" \
  --value "redirect" \
  --type String \
  --overwrite

# Use proxy mode
aws ssm put-parameter \
  --name "/dev/my-app-ip-gate/response-mode" \
  --value "proxy" \
  --type String \
  --overwrite
```

**Changes take effect in ~5 minutes** (SSM cache expiration in Lambda)

### Option 2: Environment Variable

Add to your Lambda@Edge configuration:

```json
{
  "lambda_edge": {
    "name": "my-app-ip-gate",
    "environment": {
      "GATE_ENABLED": "true",
      "ALLOW_CIDRS": "203.0.113.0/24",
      "DNS_ALIAS": "maintenance.example.com",
      "RESPONSE_MODE": "redirect"  // or "proxy"
    }
  }
}
```

**Changes require redeployment** (30 minutes for Lambda@Edge propagation)

## Testing Both Modes

### 1. Start with Redirect Mode

```bash
# Set redirect mode
aws ssm put-parameter \
  --name "/dev/tech-talk-dev-ip-gate/response-mode" \
  --value "redirect" \
  --type String \
  --overwrite

# Test from unauthorized IP
curl -I https://your-site.cloudfront.net
# Should see: HTTP/2 302
# Location: https://maintenance-site.cloudfront.net
```

### 2. Switch to Proxy Mode

```bash
# Set proxy mode
aws ssm put-parameter \
  --name "/dev/tech-talk-dev-ip-gate/response-mode" \
  --value "proxy" \
  --type String \
  --overwrite

# Wait 5 minutes for cache expiration

# Test from unauthorized IP
curl -I https://your-site.cloudfront.net
# Should see: HTTP/2 200
# Content-Type: text/html
# X-IP-Gate-Mode: proxy
```

### 3. Verify Headers

Both modes include a custom header for debugging:

```bash
# Check which mode is active
curl -I https://your-site.cloudfront.net | grep X-IP-Gate-Mode

# Redirect mode:
# X-IP-Gate-Mode: redirect

# Proxy mode:
# X-IP-Gate-Mode: proxy
```

## Real-World Example: Scheduled Maintenance

### Scenario: Deploy New Version at 2 AM

**Before deployment (proxy mode):**
```bash
# 1. Enable proxy mode
aws ssm put-parameter \
  --name "/prod/app-ip-gate/response-mode" \
  --value "proxy" \
  --overwrite

# 2. Update maintenance page
echo "Site maintenance in progress. Refreshing automatically..." > /var/www/maintenance/index.html
aws s3 cp /var/www/maintenance/index.html s3://maintenance-bucket/
aws cloudfront create-invalidation --distribution-id E9DA247QGIUKV --paths "/*"

# 3. Disable IP gate (all users see maintenance)
aws ssm put-parameter \
  --name "/prod/app-ip-gate/gate-enabled" \
  --value "false" \
  --overwrite
```

**During deployment:**
- Users stay on your domain: `https://your-site.com`
- They see: "Site maintenance in progress. Refreshing automatically..."
- Users can refresh to check status

**After deployment (back online):**
```bash
# 1. Re-enable IP gate
aws ssm put-parameter \
  --name "/prod/app-ip-gate/gate-enabled" \
  --value "true" \
  --overwrite

# 2. Invalidate CloudFront cache
aws cloudfront create-invalidation \
  --distribution-id E3T9ODGTZTLF2N \
  --paths "/*"

# Users refresh → See new site immediately!
```

**Benefits of proxy mode for maintenance:**
- ✅ Users stay on your domain
- ✅ Refreshing checks if site is back online
- ✅ Seamless transition when maintenance completes
- ✅ Can add auto-refresh to maintenance page

## Performance Considerations

### Redirect Mode Performance

```
Lambda execution: 1-5ms
Cost per 1M requests: $0.60
User experience: One redirect, then fast
```

**Breakdown:**
1. Lambda checks IP: 1-2ms
2. Returns 302 redirect: <1ms
3. Browser follows redirect: 0ms (client-side)
4. Maintenance page loads: Normal CloudFront speed

**Total latency:** ~5ms added to first request only

### Proxy Mode Performance

```
Lambda execution: 50-500ms
Cost per 1M requests: $0.60 (requests) + data transfer
User experience: Slower initial load
```

**Breakdown:**
1. Lambda checks IP: 1-2ms
2. Fetch maintenance page: 20-100ms
3. Return proxied content: 10-50ms
4. User sees page: Normal browser render

**Total latency:** ~100ms added to every request

### Cost Comparison (1M Requests/Month)

**Redirect Mode:**
- Invocations: $0.60
- Duration: (1M × 0.002s × 0.125GB) × $0.00005001 ≈ $0.01
- **Total: ~$0.61/month**

**Proxy Mode:**
- Invocations: $0.60
- Duration: (1M × 0.100s × 0.125GB) × $0.00005001 ≈ $0.63
- Data transfer: ~1MB per response × 1M requests = 1TB
- Lambda data transfer: Included (within 1GB ephemeral storage)
- **Total: ~$1.23/month**

**Verdict:** Proxy mode costs ~2x redirect mode at high traffic, but still very cheap!

## Troubleshooting

### Proxy Mode Not Working

**Symptoms:**
- Still seeing redirect even though proxy mode is set
- Getting 403 error page instead of lockout page
- 502 errors from CloudFront
- Timeout errors in Lambda logs

**Common causes:**

**1. Using CloudFront domain instead of DNS alias (CRITICAL):**

This is the most common mistake! If you're getting Google's 403 error page, you're likely using the raw CloudFront domain.

```python
# ❌ WRONG - Returns 403!
response = http.request('GET', f'https://d14pisygxjo4bs.cloudfront.net/index.html')

# ✅ CORRECT - Works!
response = http.request('GET', f'https://lockout.techtalkwitheric.com/index.html')
```

**Why this happens:**
- CloudFront distributions with custom domains only accept requests with matching `Host` headers
- Raw CloudFront URLs don't match any configured aliases
- CloudFront returns 403 when no alias matches

**Fix:**
Ensure your Lambda@Edge function uses the DNS alias, not the CloudFront domain:

```bash
# Check what's configured
aws ssm get-parameter --name "/dev/tech-talk-dev-ip-gate/dns-alias"

# Should return: lockout.example.com (NOT d14pisygxjo4bs.cloudfront.net)
```

Update your SSM exports in CDK config:
```json
"ssm_exports": {
  "dns_alias": "/dev/my-app/secondary-site/dns-alias",  // ✅ Use this!
  "cloudfront_domain": "/dev/my-app/secondary-site/cloudfront-domain"  // ❌ Don't use for proxy
}
```

**2. Missing explicit /index.html path:**

```python
# ❌ May return 403
response = http.request('GET', f'https://{dns_alias}')

# ✅ Always specify the path
response = http.request('GET', f'https://{dns_alias}/index.html')
```

Even if you have a default root object configured, the proxy request needs an explicit path.

**Other common causes:**

1. **SSM parameter not set correctly:**
```bash
# Check current value
aws ssm get-parameter --name "/dev/tech-talk-dev-ip-gate/response-mode"

# Should show: "proxy"
# If not, set it:
aws ssm put-parameter \
  --name "/dev/tech-talk-dev-ip-gate/response-mode" \
  --value "proxy" \
  --type String \
  --overwrite
```

2. **SSM cache not expired (wait 5 minutes):**
```bash
# Check Lambda logs to see current mode
aws logs tail /aws/lambda/us-east-1.tech-talk-dev-ip-gate --follow
```

3. **Maintenance site timeout (slow response):**
```bash
# Test maintenance site speed
time curl -o /dev/null https://maintenance-site.cloudfront.net

# Should be < 1 second
# If slower, Lambda may timeout (5 second limit)
```

4. **urllib3 import error:**
```bash
# Check Lambda logs for import errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/us-east-1.tech-talk-dev-ip-gate \
  --filter-pattern "Error"

# urllib3 should be available (comes with botocore)
```

### Fallback Behavior

If proxy mode fails for any reason, the Lambda **automatically falls back to redirect mode**:

```python
except Exception as proxy_error:
    print(f"Error proxying maintenance content: {str(proxy_error)}")
    print(f"Falling back to redirect mode")
    response_mode = 'redirect'
```

This ensures users never see errors, just a redirect instead.

## Best Practices

### 1. Use Redirect Mode by Default

- Faster, cheaper, simpler
- Good for security/lockdown use cases
- Set and forget

### 2. Switch to Proxy Mode for Maintenance

- Better UX during scheduled maintenance
- Users can refresh to check status
- Seamless transition when back online

### 3. Test Both Modes

```bash
# Create test script
cat > test-ip-gate.sh << 'EOF'
#!/bin/bash
SITE="https://your-site.cloudfront.net"

echo "Testing redirect mode..."
aws ssm put-parameter --name "/dev/app/response-mode" --value "redirect" --overwrite
sleep 300  # Wait for cache expiration
curl -I $SITE | grep -E "(HTTP|Location|X-IP-Gate-Mode)"

echo -e "\nTesting proxy mode..."
aws ssm put-parameter --name "/dev/app/response-mode" --value "proxy" --overwrite
sleep 300
curl -I $SITE | grep -E "(HTTP|Content-Type|X-IP-Gate-Mode)"
EOF

chmod +x test-ip-gate.sh
```

### 4. Monitor Lambda Performance

```bash
# Check average execution time
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=us-east-1.tech-talk-dev-ip-gate \
  --start-time 2025-01-01T00:00:00Z \
  --end-time 2025-01-31T23:59:59Z \
  --period 86400 \
  --statistics Average

# Redirect mode: ~2-5ms
# Proxy mode: ~50-200ms
```

### 5. Set Appropriate Timeouts

For proxy mode, ensure your maintenance site responds quickly:

```bash
# Test maintenance site response time
time curl -o /dev/null https://maintenance-site.cloudfront.net

# Should be < 1 second
# Lambda timeout is 5 seconds
# Keep response time under 2 seconds for safety margin
```

## Summary

| Scenario | Recommended Mode | Why |
|----------|-----------------|-----|
| **Dev/staging lockdown** | Redirect | Fast, clear access denial |
| **Beta access control** | Redirect | Transparent restriction |
| **Scheduled maintenance** | Proxy | Users stay on your domain, can refresh |
| **Emergency lockdown** | Redirect | Simpler, more reliable |
| **Testing/demo** | Both | Test each mode's behavior |
| **Partner portals** | Redirect | Clear access boundaries |
| **Deployment windows** | Proxy | Better UX, seamless transition |

**Default: Redirect** (fast, cheap, reliable)  
**Maintenance: Proxy** (better UX, same URL)

Both modes are production-ready and can be switched instantly via SSM Parameter Store!
