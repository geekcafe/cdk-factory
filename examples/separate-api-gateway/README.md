# Example: Separate Lambda and API Gateway Stacks

This example demonstrates the **recommended pattern** for deploying Lambda functions and API Gateway separately using CDK-Factory v2.0+.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Pipeline Stage 1                         │
│                   Deploy Lambda Stacks                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Lambda Stack                                               │
│  ┌───────────────────────────────────────────────┐         │
│  │  Create Lambda Functions                      │         │
│  │  ├─ Health Check Lambda                       │         │
│  │  ├─ User API Lambda                           │         │
│  │  └─ Admin API Lambda                          │         │
│  │                                                │         │
│  │  Export to SSM Parameter Store:               │         │
│  │  ├─ /org/env/lambda/health/arn                │         │
│  │  ├─ /org/env/lambda/user-api/arn              │         │
│  │  └─ /org/env/lambda/admin-api/arn             │         │
│  └───────────────────────────────────────────────┘         │
│                          │                                  │
│                          │ SSM Parameters                   │
│                          ▼                                  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    Pipeline Stage 2                         │
│                Deploy API Gateway Stack                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  API Gateway Stack                                          │
│  ┌───────────────────────────────────────────────┐         │
│  │  Import Lambda ARNs from SSM                  │         │
│  │  ├─ GET  /health        → health Lambda       │         │
│  │  ├─ GET  /users         → user-api Lambda     │         │
│  │  ├─ POST /users         → user-api Lambda     │         │
│  │  └─ GET  /admin/stats   → admin-api Lambda    │         │
│  │                                                │         │
│  │  Create API Gateway                            │         │
│  │  ├─ Stage: prod                                │         │
│  │  ├─ CORS Configuration                         │         │
│  │  ├─ Cognito Authorizer (optional)             │         │
│  │  └─ Custom Domain (optional)                  │         │
│  └───────────────────────────────────────────────┘         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Files

- `lambda-stack.json` - Lambda function definitions
- `api-gateway-stack.json` - API Gateway with route configurations
- `config.json` - Pipeline configuration

## Usage

1. **Deploy Lambda Stack First:**
   ```bash
   cdk deploy MyApp-Lambda-Stack
   ```

2. **Verify SSM Parameters:**
   ```bash
   aws ssm get-parameter --name /my-app/prod/lambda/health-check/arn
   ```

3. **Deploy API Gateway Stack:**
   ```bash
   cdk deploy MyApp-API-Gateway-Stack
   ```

## Key Features

✅ **SSM-based Cross-Stack Communication** - No CloudFormation exports
✅ **Independent Lifecycles** - Update Lambdas without touching API Gateway
✅ **Auto-Discovery** - Reference Lambdas by name, ARN auto-resolved
✅ **Multiple Environments** - Easy to deploy dev/staging/prod
✅ **Security Best Practices** - Cognito integration, CORS, authorization

## Testing

Test Lambda independently:
```bash
aws lambda invoke --function-name my-lambda output.json
```

Test API Gateway:
```bash
curl https://api-id.execute-api.region.amazonaws.com/prod/health
```
