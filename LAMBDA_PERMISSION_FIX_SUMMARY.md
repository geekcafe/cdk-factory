# Lambda Permission Fix - Quick Summary

## The Problem
```
Execution failed due to configuration error: Invalid permissions on Lambda function
```

## The Root Cause
When importing Lambda from SSM (`lambda_name` or `lambda_arn_ssm_path`), API Gateway didn't have permission to invoke it.

## The Fix (One Line Change)
Changed from:
```python
lambda_fn = _lambda.Function.from_function_arn(self, id, lambda_arn)
```

To:
```python
lambda_fn = _lambda.Function.from_function_attributes(
    self, id,
    function_arn=lambda_arn,
    same_environment=True  # ← This is the key!
)
```

Plus adding explicit permission:
```python
_lambda.CfnPermission(
    self, f"lambda-permission-{suffix}",
    action="lambda:InvokeFunction",
    function_name=lambda_fn.function_arn,
    principal="apigateway.amazonaws.com",
    source_arn=f"arn:aws:execute-api:{region}:{account}:{api_id}/*/{method}{path}"
)
```

## Why `same_environment=True`?
- Tells CDK the Lambda is in the same account/region
- Allows adding `CfnPermission` without validation errors
- `from_function_arn()` creates read-only references that block permissions

## What Gets Created
A CloudFormation `AWS::Lambda::Permission` resource that grants your API Gateway invoke access to the Lambda.

## Files Changed
- `src/cdk_factory/stack_library/api_gateway/api_gateway_stack.py` - The fix
- `tests/unit/test_api_gateway_lambda_permission.py` - New tests
- `docs/api_gateway_lambda_permissions_fix.md` - Full documentation

## Applies To
✅ Routes with `lambda_name` (SSM auto-discovery)
✅ Routes with `lambda_arn_ssm_path` (explicit SSM path)
❌ Routes with `src` (inline Lambda - already works)

## Deployment
Just redeploy your API Gateway stack - no Lambda stack changes needed!
