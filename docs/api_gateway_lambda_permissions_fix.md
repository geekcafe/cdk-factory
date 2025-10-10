# API Gateway Lambda Permissions Fix

## Problem

When using the separated Lambda and API Gateway stack pattern (where Lambda is created in one stack and imported in API Gateway stack via SSM), API Gateway fails with:

```
Execution failed due to configuration error: Invalid permissions on Lambda function
```

## Root Cause

When importing a Lambda function using `Function.from_function_arn()`, the `LambdaIntegration` construct does **not automatically grant** API Gateway permission to invoke the Lambda. This is different from when Lambda and API Gateway are created in the same stack, where CDK automatically handles the permission grant.

## Solution

The fix adds explicit Lambda invoke permissions when importing Lambda functions from SSM:

### Code Changes in `api_gateway_stack.py`

In the `_setup_existing_lambda_route()` method, after importing the Lambda function, we now:

1. **Import Lambda using `from_function_attributes()`** with `same_environment=True`:
   ```python
   lambda_fn = _lambda.Function.from_function_attributes(
       self,
       f"{api_id}-imported-lambda-{suffix}",
       function_arn=lambda_arn,
       same_environment=True  # Allow permission grants for same-account imports
   )
   ```

2. **Add explicit resource-based permission** for the specific API Gateway and route:
   ```python
   _lambda.CfnPermission(
       self,
       f"lambda-permission-{suffix}",
       action="lambda:InvokeFunction",
       function_name=lambda_fn.function_arn,
       principal="apigateway.amazonaws.com",
       source_arn=f"arn:aws:execute-api:{self.region}:{self.account}:{api_gateway.rest_api_id}/*/{method}{route_path}"
   )
   ```

### What This Creates

The fix creates a `AWS::Lambda::Permission` CloudFormation resource that grants API Gateway permission to invoke the Lambda function:

```json
{
  "Type": "AWS::Lambda::Permission",
  "Properties": {
    "Action": "lambda:InvokeFunction",
    "FunctionName": "<lambda-arn>",
    "Principal": "apigateway.amazonaws.com",
    "SourceArn": "arn:aws:execute-api:us-east-1:123456789012:abc123/*/<METHOD>/<PATH>"
  }
}
```

## When This Applies

This fix applies when using the **new separated stack pattern**:

1. **Lambda Stack** - Creates Lambda and exports ARN to SSM
2. **API Gateway Stack** - Imports Lambda ARN from SSM and creates integration

### Configuration Example

```json
{
  "api_gateway": {
    "routes": [
      {
        "path": "/api/users",
        "method": "GET",
        "lambda_name": "user-service",  // ← Imports from SSM
        "authorization_type": "NONE"
      }
    ]
  }
}
```

or

```json
{
  "api_gateway": {
    "routes": [
      {
        "path": "/api/orders",
        "method": "POST",
        "lambda_arn_ssm_path": "/my-app/prod/lambda/order-service/arn",  // ← Explicit SSM path
        "authorization_type": "NONE"
      }
    ]
  }
}
```

## Legacy Pattern (Not Affected)

The legacy pattern where Lambda is created inline within API Gateway stack still works as before:

```json
{
  "api_gateway": {
    "routes": [
      {
        "path": "/health",
        "method": "GET",
        "src": "path/to/lambda/code",  // ← Creates Lambda inline
        "handler": "app.handler"
      }
    ]
  }
}
```

## Testing

A comprehensive test suite has been created in `test_api_gateway_lambda_permission.py` that verifies:

1. ✅ Lambda::Permission is created for imported Lambdas
2. ✅ Permission includes correct source ARN with method and path
3. ✅ Multiple routes create multiple permissions
4. ✅ Both `lambda_name` and `lambda_arn_ssm_path` patterns work

## Related Documentation

- [Lambda Stack Documentation](./lambda_stack.md)
- [API Gateway Stack Documentation](./api_gateway_stack.md)
- [SSM Parameter Sharing Pattern](./ssm_parameter_pattern.md)
- [Migration Guide v2.0](./MIGRATION_V2.md)

## Technical Details

### Why `from_function_attributes()` instead of `from_function_arn()`?

Using `Function.from_function_attributes()` with `same_environment=True` is crucial because:

1. **Allows Permission Modification** - Tells CDK the function is in the same account/region and we can modify its permissions
2. **Prevents Validation Errors** - `from_function_arn()` creates a read-only reference that blocks permission grants
3. **Enables `CfnPermission`** - The low-level permission resource needs to attach to a modifiable function reference

The `same_environment=True` flag is safe when:
- Lambda and API Gateway are in the same AWS account
- Lambda and API Gateway are in the same AWS region
- You're using SSM parameters within the same deployment environment

### Source ARN Pattern

The source ARN follows this format:
```
arn:aws:execute-api:{region}:{account}:{api-id}/*/{method}/{path}
```

Where:
- `{region}` - AWS region (e.g., `us-east-1`)
- `{account}` - AWS account ID
- `{api-id}` - API Gateway REST API ID
- `{method}` - HTTP method (e.g., `GET`, `POST`)
- `{path}` - Route path (e.g., `/api/users`)

The wildcard `*` in the stage position allows invocation from any stage (dev, prod, etc.).

## Troubleshooting

### Still Getting Permission Errors?

1. **Check SSM Parameter Exists**: Ensure Lambda stack deployed successfully and exported ARN to SSM
   ```bash
   aws ssm get-parameter --name "/<workload>/<env>/lambda/<lambda-name>/arn"
   ```

2. **Verify Lambda ARN**: Check the CloudFormation template shows correct Lambda ARN reference

3. **Check API Gateway Deployment**: Ensure API Gateway deployment occurred after permission grant

4. **Review CloudWatch Logs**: Look for Lambda permission errors in API Gateway execution logs

### Common Mistakes

❌ **Wrong**: Assuming imported Lambdas get automatic permissions
✅ **Right**: Explicitly grant permissions for cross-stack Lambda integrations

❌ **Wrong**: Using `lambda_name` without deploying Lambda stack first
✅ **Right**: Deploy Lambda stack, then API Gateway stack in sequence

❌ **Wrong**: Missing `authorization_type` configuration
✅ **Right**: Explicitly set `authorization_type: "NONE"` for public endpoints or configure Cognito
