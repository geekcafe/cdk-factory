# Fixing CDK Environment Context Error

## Problem

When using CDK constructs that require context lookups (like VPC, security groups, etc.), you may encounter this error:

```
RuntimeError: ValidationError: Cannot retrieve value from context provider vpc-provider since account/region are not specified at the stack level. Configure "env" with an account and region when you define your stack. See https://docs.aws.amazon.com/cdk/latest/guide/environments.html for more details.
```

This happens because CDK needs to know which AWS account and region to use for context lookups.

## Solution

The `StackFactory`, `WorkloadFactory`, and `CdkAppFactory` classes have been updated to automatically pass account and region information from the deployment configuration to each stack.

### How It Works

1. The `StackFactory` extracts account and region from the deployment configuration
2. It creates a CDK `Environment` object and passes it to the stack constructor
3. The `WorkloadFactory` passes the deployment object to the stack factory
4. The `CdkAppFactory` enables this behavior by default

### Configuration Requirements

Make sure your deployment configuration includes:

```json
{
  "name": "my-deployment",
  "account": "123456789012",
  "region": "us-east-1",
  "mode": "stack",
  "environment": "dev"
}
```

Both `account` and `region` are required for the environment context to work properly.

### Disabling Environment Context

If needed, you can disable the automatic environment context by setting `add_env_context=False` when initializing the `CdkAppFactory`:

```python
factory = CdkAppFactory(
    config_path="path/to/config.json",
    add_env_context=False  # Disable automatic environment context
)
```

### Example

No code changes are needed to use this feature - it's enabled by default. Just make sure your deployment configuration includes the required `account` and `region` properties.
