# cdk-factory

Config-driven AWS CDK wrapper. Define infrastructure in JSON, deploy with one command.

## How It Works

1. You write a `config.json` describing your workload (stacks, pipelines, deployments)
2. Stack modules (DynamoDB, Lambda, S3, etc.) are registered via `@register_stack` decorator and loaded dynamically at runtime
3. `{{PLACEHOLDER}}` template variables in config are resolved from environment variables, CDK context (`-c` flags), or static defaults
4. Deployment JSON files (`deployment.*.json`) provide per-tenant/per-environment overrides
5. A single `deploy.py` CLI handles synth, diff, and deploy — interactive or scripted

## Core Concepts

| Concept | Description |
|---------|-------------|
| **Workload** | Top-level grouping: name, devops account, stacks, deployments, pipelines |
| **Deployment** | A target environment: account, region, naming prefix, mode (`stack` or `pipeline`) |
| **Stage** | A group of stacks deployed together within a pipeline (e.g., `persistent-resources`, `application`) |
| **Stack** | A CloudFormation stack backed by a module (e.g., `dynamodb_stack`, `lambda_stack`) |
| **Pipeline** | An AWS CodePipeline that orchestrates multi-stage deployments |
| **`__inherits__`** | JSON composition — pull stack config from external files |
| **`{{PLACEHOLDER}}`** | Template variables resolved at synth time |

## Quick Start

```bash
# 1. Install cdk-factory
pip install cdk-factory

# 2. Create your config.json (see configuration-reference.md)

# 3. Create a deployment file: deployments/deployment.dev.json

# 4. Deploy
python deploy.py                    # interactive
python deploy.py -e dev -o synth    # non-interactive
python deploy.py --dry-run          # validate only
```

## Minimal config.json

```json
{
  "cdk": {
    "parameters": [
      {
        "placeholder": "{{WORKLOAD_NAME}}",
        "env_var_name": "WORKLOAD_NAME",
        "cdk_parameter_name": "WorkloadName"
      },
      {
        "placeholder": "{{AWS_ACCOUNT}}",
        "env_var_name": "AWS_ACCOUNT",
        "cdk_parameter_name": "AccountNumber"
      },
      {
        "placeholder": "{{AWS_REGION}}",
        "env_var_name": "AWS_REGION",
        "cdk_parameter_name": "AccountRegion"
      }
    ]
  },
  "workload": {
    "name": "{{WORKLOAD_NAME}}",
    "devops": {
      "account": "111111111111",
      "region": "us-east-1",
      "code_repository": {
        "name": "MyOrg/MyRepo",
        "type": "connector_arn",
        "connector_arn": "arn:aws:codestar-connections:us-east-1:111111111111:connection/abc-123"
      }
    },
    "deployments": [
      {
        "name": "my-pipeline",
        "environment": "dev",
        "account": "{{AWS_ACCOUNT}}",
        "region": "{{AWS_REGION}}",
        "mode": "pipeline",
        "naming": {
          "prefix": "{{WORKLOAD_NAME}}-dev",
          "stack_pattern": "{prefix}-{stage}-{stack_name}"
        },
        "pipeline": {
          "name": "my-pipeline",
          "branch": "main",
          "enabled": true,
          "stages": [
            {
              "name": "storage",
              "stacks": [
                { "__inherits__": "./configs/stacks/dynamodb-main.json" }
              ]
            }
          ]
        }
      }
    ]
  }
}
```

## Stack Module Registration

Modules use the `@register_stack` decorator and are auto-discovered from `stack_library/`:

```python
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.interfaces.istack import IStack

@register_stack("my_custom_stack")
class MyCustomStack(IStack):
    def build(self, stack_config, deployment, workload):
        # Your CDK constructs here
        pass
```

Reference it in config:
```json
{ "name": "my-stack", "module": "my_custom_stack", "enabled": true }
```

## Documentation

- [Configuration Reference](configuration-reference.md) — Full config.json schema
- [Stack Modules](stack-modules.md) — Per-module config reference
- [Naming & SSM](naming-and-ssm.md) — Stack naming, SSM parameter conventions
- [Cross-Account](cross-account.md) — Multi-account setup and DNS delegation
- [Deployment Guide](deployment-guide.md) — How to deploy, add tenants, parameter resolution
