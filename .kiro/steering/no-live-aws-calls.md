# No Live AWS Calls — Use CloudFormation Tokens

## Priority: HIGH

## Rule

NEVER use live boto3 calls (or any direct AWS SDK calls) to resolve values during CDK synthesis. Always use CDK token-based mechanisms that defer resolution to CloudFormation deploy time.

## Why

Live AWS calls during CDK synth:
- Require valid AWS credentials on the developer's machine just to run `cdk synth`
- Create timing issues — the value resolved at synth time may differ from deploy time
- Break CI/CD pipelines that don't have the same AWS context as the target account
- Make the synthesized template non-portable between environments
- Add latency and failure modes (network errors, throttling) to the synth step

CloudFormation tokens:
- Are resolved at deploy time by CloudFormation itself
- Always reflect the current state of the target environment
- Require no AWS credentials during synth
- Make templates fully portable

## Correct Pattern — SSM Parameter References

Use `aws_cdk.aws_ssm.StringParameter.value_for_string_parameter()` to produce a CF dynamic reference:

```python
# CORRECT — resolved by CloudFormation at deploy time
ssm_value = aws_cdk.aws_ssm.StringParameter.value_for_string_parameter(
    scope, "/my-app/dev/lambda/handler/arn"
)
# ssm_value is a CDK token: {{resolve:ssm:/my-app/dev/lambda/handler/arn}}
```

## Correct Pattern — Cross-Stack References

Use CDK exports/imports or `Fn.import_value()`:

```python
# CORRECT — resolved by CloudFormation at deploy time
function_arn = cdk.Fn.import_value("MyStack-FunctionArn")
```

## Anti-Pattern

```python
# WRONG — live boto3 call during synth
import boto3
ssm_client = boto3.client("ssm")
response = ssm_client.get_parameter(Name="/my-app/dev/lambda/handler/arn")
arn = response["Parameter"]["Value"]

# WRONG — value_from_lookup caches in cdk.context.json and requires live calls
value = aws_cdk.aws_ssm.StringParameter.value_from_lookup(scope, "/path")
```

## When This Applies

- Any code in `src/cdk_factory/` that generates CloudFormation resources
- Permission builders (`policy_docs.py`)
- Environment variable resolution
- Resource ARN construction where the target is in another stack

## Exception

- **Test utilities** that verify deployed resources may use boto3 (they run post-deploy, not during synth)
- **CLI tools** (`commands/`) that interact with live AWS resources outside the CDK synth lifecycle
- **Context lookups** (`value_from_lookup`) are acceptable ONLY for values that genuinely cannot change between synth and deploy (e.g., VPC IDs, AZ lists) — but prefer `value_for_string_parameter` where possible
