# RUM (Real User Monitoring) Stack

Deploy CloudWatch RUM for real user monitoring of web applications with optional Cognito integration.

## What this stack creates

- **CloudWatch RUM App Monitor** for collecting client-side telemetry
- **Cognito Identity Pool** (new or existing) for authorization
- **Cognito User Pool** (optional, if creating new resources)
- **IAM Roles** for unauthenticated access to RUM
- **SSM Parameters** for cross-stack resource sharing

## Features

- **Flexible Cognito Integration**: Use existing Cognito resources or create new ones
- **Comprehensive Telemetry**: Collect errors, performance metrics, and HTTP data
- **X-Ray Integration**: Optional client-side tracing
- **Custom Events**: Support for application-specific events
- **Page Filtering**: Include/exclude specific pages from monitoring
- **SSM Parameter Integration**: Export/import resources using enhanced SSM patterns

## Configuration Files

- **`rum_minimal_config.json`**: Basic RUM setup with new Cognito resources
- **`rum_with_existing_cognito_config.json`**: Advanced setup using existing Cognito Identity Pool

## Prerequisites

- **Node.js** (for `npx cdk`), **Python 3.10+**
- **AWS credentials** configured for the target account
- Install project dependencies (from repo root):
  - `pip install -r requirements.txt`

## Quick Start: Minimal RUM Setup

Use the minimal configuration to create a complete RUM setup:

```sh
cdk synth -c config=../../samples/rum/rum_minimal_config.json
```

**Required environment variables:**
```sh
export CDK_WORKLOAD_NAME="my-app"
export AWS_ACCOUNT_NUMBER="123456789012"
export ENVIRONMENT="dev"
export RUM_DOMAIN="example.com"
```

This creates:
- RUM app monitor named `my-app-monitor`
- New Cognito Identity Pool and User Pool
- IAM roles for RUM data collection
- SSM parameters for resource sharing

## Advanced: Using Existing Cognito

If you already have Cognito resources, use the advanced configuration:

```sh
cdk synth -c config=../../samples/rum/rum_with_existing_cognito_config.json
```

**Additional environment variables:**
```sh
export COGNITO_IDENTITY_POOL_ID="us-east-1:12345678-1234-1234-1234-123456789012"
```

This configuration:
- Uses your existing Cognito Identity Pool
- Enables X-Ray tracing and CloudWatch Logs
- Supports custom events
- Includes page filtering examples

## Configuration Options

### Core RUM Properties

| Property | Type | Description | Default |
|----------|------|-------------|---------|
| `name` | string | Name of the RUM app monitor | `"app-monitor"` |
| `domain` | string | Primary domain for your application | Required |
| `domain_list` | string[] | List of domains for your application | Optional |
| `session_sample_rate` | number | Portion of sessions to sample (0.0-1.0) | `0.1` |
| `telemetries` | string[] | Types of data to collect | `["errors", "performance", "http"]` |

### Cognito Integration

| Property | Type | Description | Default |
|----------|------|-------------|---------|
| `cognito_identity_pool_id` | string | Existing Identity Pool ID | Optional |
| `cognito_user_pool_id` | string | Existing User Pool ID | Optional |
| `create_cognito_identity_pool` | boolean | Create new Identity Pool if none provided | `true` |
| `create_cognito_user_pool` | boolean | Create new User Pool if none provided | `true` |
| `cognito_identity_pool_name` | string | Name for new Identity Pool | `"{name}_identity_pool"` |
| `cognito_user_pool_name` | string | Name for new User Pool | `"{name}_user_pool"` |

### Monitoring Options

| Property | Type | Description | Default |
|----------|------|-------------|---------|
| `allow_cookies` | boolean | Enable user tracking cookies | `true` |
| `enable_xray` | boolean | Enable X-Ray client-side tracing | `false` |
| `cw_log_enabled` | boolean | Send data to CloudWatch Logs | `false` |
| `custom_events_enabled` | boolean | Allow custom application events | `false` |

### Page Filtering

| Property | Type | Description | Default |
|----------|------|-------------|---------|
| `excluded_pages` | string[] | URLs to exclude from monitoring | Optional |
| `included_pages` | string[] | URLs to include in monitoring | Optional |
| `favorite_pages` | string[] | Pages to mark as favorites in console | Optional |

**Note**: You cannot specify both `excluded_pages` and `included_pages` in the same configuration.

## SSM Parameter Integration

The RUM stack supports both exporting and importing resources via SSM parameters using the enhanced SSM pattern.

### Exporting RUM Resources

```json
{
  "rum": {
    "ssm_exports": {
      "app_monitor_name": "/my-app/rum/app-monitor-name",
      "app_monitor_id": "/my-app/rum/app-monitor-id",
      "identity_pool_id": "/my-app/rum/identity-pool-id"
    }
  }
}
```

### Importing Cognito Resources

```json
{
  "rum": {
    "ssm_imports": {
      "cognito_identity_pool_id": "auto"
    }
  }
}
```

The `"auto"` value uses the enhanced SSM pattern to automatically discover the correct parameter path.

## Deployment Scenarios

### Scenario 1: New Application
- Use `rum_minimal_config.json`
- Creates all necessary Cognito resources
- Suitable for new applications without existing authentication

### Scenario 2: Existing Cognito Integration
- Use `rum_with_existing_cognito_config.json`
- Integrates with your existing Cognito setup
- Ideal for applications with established user authentication

### Scenario 3: Multi-Stack Architecture
- Deploy Cognito stack first with SSM exports
- Deploy RUM stack with SSM imports
- Enables loose coupling between authentication and monitoring

## Getting the JavaScript Snippet

After deployment, get the RUM JavaScript snippet from the AWS Console:

1. Go to **CloudWatch** → **RUM** in the AWS Console
2. Select your app monitor
3. Click **Configuration** → **JavaScript snippet**
4. Copy the snippet and add it to your web application

The snippet will look like:
```javascript
(function(n,i,v,r,s,c,x,z){/* RUM snippet code */})('cwr','12345678-1234-1234-1234-123456789012','1.0.0','us-east-1','my-app-monitor');
```

## Monitoring and Dashboards

After deployment and snippet integration, you can:

- View real user metrics in the **CloudWatch RUM Console**
- Create custom dashboards with RUM metrics
- Set up alarms for performance thresholds
- Analyze user behavior patterns
- Monitor Core Web Vitals

## Cost Considerations

- **Free Tier**: 100,000 events per month
- **Pricing**: $1 per 100,000 events after free tier
- **CloudWatch Logs**: Additional charges if `cw_log_enabled: true`
- **X-Ray**: Additional charges if `enable_xray: true`

## Troubleshooting

### Common Issues

1. **CORS Errors**: Ensure your domain is correctly configured in `domain` or `domain_list`
2. **No Data**: Verify the JavaScript snippet is properly integrated
3. **Permission Errors**: Check that the IAM roles have correct RUM permissions
4. **Cognito Integration**: Verify Identity Pool ID is correct if using existing resources

### Debug Steps

1. Check CloudWatch RUM console for app monitor status
2. Verify JavaScript snippet is loading without errors
3. Check browser network tab for RUM API calls
4. Review CloudWatch Logs if enabled

## Example Integration

After deploying the stack, integrate the JavaScript snippet:

```html
<!DOCTYPE html>
<html>
<head>
    <title>My Application</title>
    <!-- RUM snippet goes here -->
    <script>
        (function(n,i,v,r,s,c,x,z){/* Your RUM snippet */})('cwr','your-identity-pool-id','1.0.0','us-east-1','your-app-monitor-name');
    </script>
</head>
<body>
    <!-- Your application content -->
</body>
</html>
```

## Using Outside This Repository

For production applications:

1. **Install CDK Factory**: `pip install cdk-factory`
2. **Create your config**: Model after the sample configurations
3. **Deploy**: `cdk deploy -c config=<your-config-path>`
4. **Integrate**: Add the JavaScript snippet to your web application
5. **Monitor**: View metrics in the CloudWatch RUM console
