# IP Gating Quick Start

## TL;DR

Two response modes when IP is not allowed:

1. **Redirect** (default): HTTP 302 → maintenance site (URL changes)
2. **Proxy**: Fetch & show maintenance content (URL stays same)

**Switch modes instantly via SSM - no redeployment needed!**

## Usage

### Set Redirect Mode (Default - Best for Lockdown)

```bash
aws ssm put-parameter \
  --name "/dev/my-app-ip-gate/response-mode" \
  --value "redirect" \
  --type String \
  --overwrite
```

**Result:** Users redirected to maintenance domain  
**Best for:** Security lockdown, beta access control

### Set Proxy Mode (Best for Maintenance)

```bash
aws ssm put-parameter \
  --name "/dev/my-app-ip-gate/response-mode" \
  --value "proxy" \
  --type String \
  --overwrite
```

**Result:** Maintenance content shown, URL stays same  
**Best for:** Scheduled maintenance, deployments

**Changes take effect in ~5 minutes** (SSM cache expiration)

## Testing

```bash
# Test from unauthorized IP
curl -I https://your-site.cloudfront.net | grep X-IP-Gate-Mode

# Redirect mode shows:
X-IP-Gate-Mode: redirect

# Proxy mode shows:
X-IP-Gate-Mode: proxy
```

## Common Scenarios

### Scenario 1: Dev Site Lockdown

```bash
# Use redirect mode (default)
# IP not in allow-list → redirected to maintenance site
# Clear access denial
```

### Scenario 2: Scheduled Maintenance Window

```bash
# 1. Switch to proxy mode
aws ssm put-parameter \
  --name "/prod/app/response-mode" \
  --value "proxy" \
  --overwrite

# 2. Disable gate (everyone sees maintenance)
aws ssm put-parameter \
  --name "/prod/app/gate-enabled" \
  --value "false" \
  --overwrite

# 3. Do deployment

# 4. Re-enable gate
aws ssm put-parameter \
  --name "/prod/app/gate-enabled" \
  --value "true" \
  --overwrite

# Users refresh → site is back!
```

## Quick Comparison

| Feature | Redirect | Proxy |
|---------|----------|-------|
| **Speed** | Fast (2ms) | Slower (100ms) |
| **Cost** | Cheap ($0.60/1M) | 2x ($1.20/1M) |
| **URL** | Changes | Stays same |
| **Best for** | Lockdown | Maintenance |

## More Info

- [Complete Response Modes Guide](./response-modes.md)
- [Implementation Guide](./implementation.md)
- [Cost Analysis](./cost.md)
- [Architecture](./architecture.md)
