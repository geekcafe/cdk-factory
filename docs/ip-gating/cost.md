# IP Gating Cost Analysis

## Overview

This document provides a comprehensive cost analysis for the Lambda@Edge IP gating solution. The IP gating feature adds a Lambda@Edge function that runs on every CloudFront viewer request to validate the client's IP address against an allow-list stored in AWS Systems Manager (SSM) Parameter Store.

## Cost Components

### 1. Lambda@Edge Execution Costs

Lambda@Edge pricing is higher than regular Lambda because it runs at CloudFront edge locations globally.

**AWS Lambda@Edge Pricing (US East - N. Virginia, as of 2025):**

| Component | Price | Notes |
|-----------|-------|-------|
| **Requests** | $0.60 per 1M requests | 5x more expensive than regular Lambda ($0.20/1M) |
| **Duration** | $0.00005001 per GB-second | Slightly higher than regular Lambda |
| **Memory** | 128MB minimum | IP check typically uses minimum memory |

**Typical Execution Characteristics:**
- **Memory**: 128MB (minimum allocation)
- **Duration**: 5-20ms per request (IP validation is fast)
- **Invocations**: Every non-cached request to CloudFront

### 2. CloudFront Costs (No Additional Cost)

IP gating doesn't add CloudFront costs beyond what you'd already pay:

- **Data Transfer OUT**: $0.085/GB (first 10TB/month)
- **HTTP/HTTPS Requests**: $0.0075-$0.016 per 10K requests
- **Viewer-Request Lambda@Edge**: Already covered above

**Note**: These are standard CloudFront costs whether or not you use IP gating.

### 3. SSM Parameter Store Costs

**Standard Parameters** (used for IP allow-list):
- **Storage**: FREE (up to 10,000 parameters)
- **API Calls**: First 10,000/month FREE, then $0.05 per 10K
- **Parameter size**: Up to 4KB per parameter

For IP gating, you typically have:
- 1-3 parameters (gate-enabled, allow-cidrs, dns-alias)
- 1-10 API calls per deployment
- **Effective cost**: $0.00/month

### 4. CloudWatch Logs (Optional)

If you enable Lambda@Edge logging:
- **Ingestion**: $0.50 per GB
- **Storage**: $0.03 per GB/month
- **Typical IP gate logs**: 100-500 bytes per request

For most use cases, logging costs are negligible (<$1/month).

## Cost Calculations

### Example 1: Small Development Site

```
Monthly Traffic: 10,000 requests
Memory: 128MB
Avg Duration: 10ms

Calculation:
- Request cost: (10,000 / 1,000,000) × $0.60 = $0.006
- Duration cost: (10,000 × 0.010s × 0.125GB) × $0.00005001 ≈ $0.0006
- Total Lambda@Edge: ~$0.01/month
- CloudFront: ~$0.10/month (data transfer)
- SSM: $0.00/month

Total Monthly Cost: ~$0.11/month
```

**Verdict**: Effectively free for development! ✅

### Example 2: Medium Production Site

```
Monthly Traffic: 100,000 requests
Memory: 128MB
Avg Duration: 10ms

Calculation:
- Request cost: (100,000 / 1,000,000) × $0.60 = $0.06
- Duration cost: (100,000 × 0.010s × 0.125GB) × $0.00005001 ≈ $0.006
- Total Lambda@Edge: ~$0.07/month
- CloudFront: ~$1.00/month (data transfer)
- SSM: $0.00/month

Total Monthly Cost: ~$1.07/month
```

**Verdict**: Very affordable for most production sites! ✅

### Example 3: High-Traffic Production Site

```
Monthly Traffic: 1,000,000 requests
Memory: 128MB
Avg Duration: 10ms

Calculation:
- Request cost: (1,000,000 / 1,000,000) × $0.60 = $0.60
- Duration cost: (1,000,000 × 0.010s × 0.125GB) × $0.00005001 ≈ $0.06
- Total Lambda@Edge: ~$0.66/month
- CloudFront: ~$10.00/month (data transfer)
- SSM: $0.00/month

Total Monthly Cost: ~$10.66/month
```

**Verdict**: Still very cost-effective! ✅

### Example 4: Very High Traffic Site

```
Monthly Traffic: 10,000,000 requests
Memory: 128MB
Avg Duration: 10ms

Calculation:
- Request cost: (10,000,000 / 1,000,000) × $0.60 = $6.00
- Duration cost: (10,000,000 × 0.010s × 0.125GB) × $0.00005001 ≈ $0.60
- Total Lambda@Edge: ~$6.60/month
- CloudFront: ~$100.00/month (data transfer)
- SSM: $0.00/month

Total Monthly Cost: ~$106.60/month
```

**Verdict**: Lambda@Edge is only 6% of total CloudFront costs. Still reasonable! ✅

## Cost Comparison: Lambda@Edge vs. AWS WAF

For very high traffic sites, AWS WAF might be an alternative:

| Traffic/Month | Lambda@Edge Cost | AWS WAF Cost | Recommendation |
|---------------|------------------|--------------|----------------|
| 100K | $0.07 | $5.10 | Lambda@Edge ✅ |
| 1M | $0.66 | $6.00 | Lambda@Edge ✅ |
| 5M | $3.30 | $10.00 | Lambda@Edge ✅ |
| 10M | $6.60 | $15.00 | Lambda@Edge ✅ |
| 50M | $33.00 | $55.00 | Lambda@Edge ✅ |
| 100M | $66.00 | $105.00 | Lambda@Edge ✅ |

**AWS WAF Pricing:**
- Base: $5.00/month per Web ACL
- Rules: $1.00/month per rule
- Requests: $1.00 per million requests

**Break-even Analysis:**
Lambda@Edge remains more cost-effective than WAF until you reach extremely high traffic (>100M requests/month). Additionally, Lambda@Edge offers more flexibility for custom logic.

## Response Mode Cost Comparison

The IP gating function supports two response modes when blocking unauthorized IPs, each with different cost implications:

### Redirect Mode (Default)

**Cost Profile:**
```
Monthly Traffic: 1M requests (all blocked)
Memory: 128MB
Avg Duration: 2-5ms
```

**Calculation:**
- Request cost: (1M / 1M) × $0.60 = $0.60
- Duration cost: (1M × 0.003s × 0.125GB) × $0.00005001 ≈ $0.02
- **Total: ~$0.62/month**

**Characteristics:**
- Fast execution (~2-5ms)
- Minimal compute cost
- Returns HTTP 302 redirect
- User sees lockout URL in browser

### Proxy Mode

**Cost Profile:**
```
Monthly Traffic: 1M requests (all blocked)
Memory: 128MB
Avg Duration: 100-200ms (includes HTTP fetch)
```

**Calculation:**
- Request cost: (1M / 1M) × $0.60 = $0.60
- Duration cost: (1M × 0.150s × 0.125GB) × $0.00005001 ≈ $0.94
- **Total: ~$1.54/month**

**Characteristics:**
- Slower execution (~100-200ms)
- Higher compute cost (50x more duration)
- Fetches and returns lockout page content
- User stays on original URL

### Cost Comparison Summary

| Traffic/Month | Redirect Mode | Proxy Mode | Difference |
|---------------|---------------|------------|------------|
| 10K | $0.01 | $0.02 | +100% |
| 100K | $0.06 | $0.15 | +150% |
| 1M | $0.62 | $1.54 | +148% |
| 10M | $6.20 | $15.40 | +148% |

**Key Takeaway:** Proxy mode costs approximately **2.5x more** than redirect mode due to longer execution times (fetching and returning content). However, both remain very affordable for typical use cases.

**Recommendation:**
- **Use redirect mode by default** - Lower cost, faster performance
- **Switch to proxy mode for scheduled maintenance** - Better UX, worth the small extra cost
- **Changes via SSM take 5 minutes** - No redeployment needed

## Monitoring Your Actual Costs

### Method 1: CloudWatch Metrics

Monitor Lambda@Edge in CloudWatch:

```bash
# View invocation count
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=us-east-1.your-function-name \
  --start-time 2025-01-01T00:00:00Z \
  --end-time 2025-01-31T23:59:59Z \
  --period 86400 \
  --statistics Sum

# View duration
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=us-east-1.your-function-name \
  --start-time 2025-01-01T00:00:00Z \
  --end-time 2025-01-31T23:59:59Z \
  --period 86400 \
  --statistics Average
```

**Key Metrics:**
- **Invocations**: Total requests through the IP gate
- **Duration**: Average execution time
- **Errors**: Failed validations (should be 0)
- **Throttles**: Rate limiting (should be 0)

### Method 2: Cost Allocation Tags

Tag your Lambda@Edge function for cost tracking:

```json
{
  "lambda_edge": {
    "name": "ip-gate",
    "tags": {
      "CostCenter": "Security",
      "Feature": "IPGating",
      "Environment": "prod",
      "Application": "tech-talk"
    }
  }
}
```

Then filter in **AWS Cost Explorer**:
1. Go to **Billing** → **Cost Explorer**
2. Filter by:
   - **Service**: AWS Lambda
   - **Region**: US East (N. Virginia) - Lambda@Edge always reports here
   - **Tag**: Feature=IPGating
3. View costs by day/month/year

### Method 3: AWS Cost and Usage Reports (CUR)

For detailed cost analysis:

1. Enable **Cost and Usage Reports**:
   - Go to **Billing** → **Cost & Usage Reports**
   - Create report with **Resource IDs** enabled
   - Export to S3 bucket

2. Query with AWS Athena:

```sql
-- Get Lambda@Edge costs for specific function
SELECT 
  line_item_usage_start_date,
  line_item_resource_id,
  SUM(line_item_unblended_cost) as daily_cost,
  SUM(line_item_usage_amount) as invocations
FROM cur_table
WHERE 
  line_item_product_code = 'AWSLambda'
  AND line_item_resource_id LIKE '%ip-gate%'
  AND line_item_usage_start_date >= DATE('2025-01-01')
GROUP BY 
  line_item_usage_start_date,
  line_item_resource_id
ORDER BY line_item_usage_start_date DESC;
```

3. Visualize in QuickSight or export to Excel

### Method 4: Budget Alerts

Set up budget alerts to monitor costs:

```bash
# Create budget for Lambda@Edge
aws budgets create-budget \
  --account-id 123456789012 \
  --budget file://lambda-edge-budget.json \
  --notifications-with-subscribers file://notifications.json
```

**lambda-edge-budget.json:**
```json
{
  "BudgetName": "IP-Gating-Lambda-Edge",
  "BudgetLimit": {
    "Amount": "10.00",
    "Unit": "USD"
  },
  "TimeUnit": "MONTHLY",
  "BudgetType": "COST",
  "CostFilters": {
    "Service": ["AWS Lambda"],
    "TagKeyValue": ["Feature$IPGating"]
  }
}
```

**notifications.json:**
```json
[
  {
    "Notification": {
      "NotificationType": "ACTUAL",
      "ComparisonOperator": "GREATER_THAN",
      "Threshold": 80.0,
      "ThresholdType": "PERCENTAGE"
    },
    "Subscribers": [
      {
        "SubscriptionType": "EMAIL",
        "Address": "devops@example.com"
      }
    ]
  }
]
```

## Cost Optimization Strategies

### 1. Optimize Lambda Execution

**Keep the function fast and lean:**

```python
# ✅ GOOD: Fast IP check with set lookup O(1)
allowed_ips = set(os.environ['ALLOWED_IPS'].split(','))
if client_ip in allowed_ips:
    return request

# ❌ BAD: Slow list iteration O(n)
allowed_ips = os.environ['ALLOWED_IPS'].split(',')
for ip in allowed_ips:
    if client_ip == ip:
        return request
```

**Impact**: Reduces duration cost by 50-70%

### 2. Use Minimal Memory Allocation

```json
{
  "lambda_edge": {
    "name": "ip-gate",
    "memory": 128  // Minimum - IP check doesn't need more
  }
}
```

**Impact**: 128MB vs 256MB = 50% cost reduction

### 3. Leverage CloudFront Caching (Where Possible)

**For static content:**
```json
{
  "cloudfront": {
    "default_behavior": {
      "cache_policy": "CachingOptimized"
    }
  }
}
```

**Note**: For dynamic content or strict IP validation, caching must be disabled. The IP gate Lambda will run on every request.

**Impact**: Reduces Lambda invocations by 80-95% for cacheable content

### 4. Use Regional Allow-Lists (Advanced)

For global sites with regional access patterns:

```python
# Check region-specific allow-lists
region = context['distributionDomainName'].split('.')[1]
allowed_ips = get_regional_allowlist(region)
```

**Impact**: Reduces SSM API calls and improves performance

### 5. Implement Request Sampling (Advanced)

For very high traffic sites, sample a percentage of requests:

```python
# Sample 10% of requests for IP validation
if random.random() < 0.1:
    validate_ip(client_ip)
```

**⚠️ Warning**: Reduces security. Only use if cost is prohibitive and you have other security layers.

**Impact**: 90% cost reduction (but 90% less security!)

### 6. Disable Logging in Production

CloudWatch Logs can add up:

```json
{
  "lambda_edge": {
    "name": "ip-gate",
    "logging": {
      "level": "ERROR"  // Only log errors, not every request
    }
  }
}
```

**Impact**: Reduces logging costs by 95%

## Real-World Cost Scenarios

### Scenario 1: Development Environment

**Profile:**
- 10-20 developers accessing the site
- 5,000-10,000 requests/month
- Dev/staging environment

**Monthly Costs:**
- Lambda@Edge: $0.01
- CloudFront: $0.05
- SSM: $0.00
- **Total**: ~$0.06/month

**Verdict**: Negligible cost - perfect for dev/staging! ✅

### Scenario 2: Internal Company Portal

**Profile:**
- 500 employees accessing portal
- 100,000 requests/month
- Light usage (mostly cached)

**Monthly Costs:**
- Lambda@Edge: $0.07
- CloudFront: $0.50
- SSM: $0.00
- **Total**: ~$0.57/month

**Verdict**: Extremely cost-effective for internal tools! ✅

### Scenario 3: Partner Portal

**Profile:**
- 50 partner organizations
- 500,000 requests/month
- Moderate usage

**Monthly Costs:**
- Lambda@Edge: $0.33
- CloudFront: $5.00
- SSM: $0.00
- **Total**: ~$5.33/month

**Verdict**: Very reasonable for partner access! ✅

### Scenario 4: High-Traffic Public Site (Gated Beta)

**Profile:**
- 10,000 beta users
- 5,000,000 requests/month
- Active usage

**Monthly Costs:**
- Lambda@Edge: $3.30
- CloudFront: $50.00
- SSM: $0.00
- **Total**: ~$53.30/month

**Verdict**: Lambda@Edge is only 6% of total costs. Worth it for IP security! ✅

## When to Consider Alternatives

### Consider AWS WAF If:

1. **Very high traffic** (>100M requests/month)
2. **Need DDoS protection** (AWS Shield integration)
3. **Complex rule sets** (rate limiting, geo-blocking, SQL injection)
4. **Compliance requirements** (WAF is often required)

### Consider VPN/VPC If:

1. **Highly sensitive data** (PCI, HIPAA, etc.)
2. **Zero public access** required
3. **Private network access** already in place
4. **Cost is not a concern** (VPN/VPC more expensive)

### Stick with Lambda@Edge IP Gating If:

1. **Cost-effective** (< $10/month Lambda costs)
2. **Simple IP allow-listing** is sufficient
3. **Flexible access control** (easy to update SSM parameters)
4. **Quick deployment** (no VPN client setup)
5. **CloudFront distribution** already in use

## Summary

### Cost Overview

| Component | Typical Monthly Cost | Notes |
|-----------|---------------------|-------|
| **Lambda@Edge** | $0.01 - $10.00 | Based on traffic (10K-10M requests) |
| **CloudFront** | $0.10 - $100.00 | Standard costs (not IP gating specific) |
| **SSM Parameter Store** | $0.00 | Free tier covers this use case |
| **CloudWatch Logs** | $0.00 - $1.00 | Optional, minimal if enabled |

### Key Takeaways

1. **IP gating is very cost-effective** for most use cases (<$10/month)
2. **Lambda@Edge costs scale linearly** with traffic ($0.60 per 1M requests)
3. **No hidden costs** - transparent pricing
4. **Monitor with CloudWatch** and Cost Explorer
5. **Set budget alerts** to track costs
6. **Consider WAF only for very high traffic** (>100M requests/month)

### Recommendations by Traffic Level

| Monthly Requests | Recommended Solution | Estimated Monthly Cost |
|------------------|---------------------|----------------------|
| < 100K | Lambda@Edge IP Gating | $0.01 - $0.10 |
| 100K - 1M | Lambda@Edge IP Gating | $0.10 - $1.00 |
| 1M - 10M | Lambda@Edge IP Gating | $1.00 - $10.00 |
| 10M - 100M | Lambda@Edge IP Gating | $10.00 - $100.00 |
| > 100M | Consider AWS WAF | $100.00+ |

**For most development, staging, and production sites, Lambda@Edge IP gating is the most cost-effective solution!** 🎯

## Additional Resources

- [AWS Lambda@Edge Pricing](https://aws.amazon.com/lambda/pricing/)
- [AWS CloudFront Pricing](https://aws.amazon.com/cloudfront/pricing/)
- [AWS WAF Pricing](https://aws.amazon.com/waf/pricing/)
- [IP Gating Implementation Guide](./implementation.md)
- [IP Gating Architecture](./architecture.md)
