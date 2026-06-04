# Lambda Deploy Role — Cross-Account IAM for Lambda Image Updates

## Purpose

When your Docker Lambda images are built and pushed to ECR in a **DevOps account**, but the Lambda functions run in a separate **target account**, the Lambda Image Updater needs cross-account access to update those functions. The `lambda_deploy_role_stack` module creates the necessary IAM role in the target account.

```
┌─────────────────────────┐          ┌─────────────────────────┐
│     DevOps Account       │          │     Target Account       │
│   (CodeBuild / ECR)      │          │   (Lambda functions)     │
│                          │          │                          │
│  CodeBuild runs:         │  assume  │  DevOpsLambdaDeployRole  │
│  Lambda Image Updater ───┼─────────▶│    ├─ ssm:GetParameter   │
│                          │   role   │    ├─ ssm:GetParams...   │
│  AssumeRoleLambdaUpdater │          │    ├─ lambda:GetFunction │
│  policy (caller side)    │          │    └─ lambda:UpdateFunc  │
└─────────────────────────┘          └─────────────────────────┘
```

## Two Sides of Cross-Account Access

| Side | What | Where |
|------|------|-------|
| **Caller** | IAM policy allowing `sts:AssumeRole` on `DevOpsLambdaDeployRole` | DevOps account (auto-created by cdk-factory's `CodeBuildPolicy`) |
| **Target** | IAM role with trust policy + permissions | Target account (created by `lambda_deploy_role_stack`) |

The caller-side policy is already handled by cdk-factory automatically — `policies.py` grants CodeBuild permission to assume `DevOpsLambdaDeployRole` (and the legacy `DevOpsCrossAccountAccessRole`) in any account. You only need to create the target-side role.

---

## Setup

### 1. Add the stack to your IaC config

Create a stack config JSON in your project (e.g., `cdk/configs/stacks/iam/lambda-deploy-role.json`):

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-iam-lambda-deploy-role",
  "description": "IAM role for cross-account Lambda image deployment",
  "module": "lambda_deploy_role_stack",
  "enabled": true,
  "phase": "persistent",
  "ssm": {
    "auto_export": true,
    "namespace": "{{WORKLOAD_NAME}}/{{DEPLOYMENT_NAMESPACE}}/iam/lambda-deploy-role"
  },
  "lambda_deploy_role": {
    "role_name": "DevOpsLambdaDeployRole",
    "devops_account": "{{DEVOPS_AWS_ACCOUNT}}",
    "ssm_resource_prefix": "*",
    "lambda_resource_prefix": "*"
  }
}
```

### 2. Add it to the pipeline's persistent-resources stage

```json
{
  "stages": [
    {
      "name": "persistent-resources",
      "stacks": [
        {
          "__inherits__": "./configs/stacks/iam/lambda-deploy-role.json"
        }
      ]
    }
  ]
}
```

### 3. Reference the role in docker-images.json

In your services project, add `role_name` to each `lambda_deployments` entry:

```json
{
  "images": [
    {
      "repo_name": "my-org/my-service",
      "lambda_deployments": [
        {
          "account": "111111111111",
          "region": "us-east-1",
          "ssm_prefix": "my-app/dev",
          "tag": "dev",
          "role_name": "DevOpsLambdaDeployRole"
        }
      ]
    }
  ]
}
```

If `role_name` is omitted, the Lambda Image Updater falls back to `DevOpsCrossAccountAccessRole` for backward compatibility.

---

## Configuration Reference

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `role_name` | No | `DevOpsLambdaDeployRole` | IAM role name created in the target account |
| `devops_account` | **Yes** | — | AWS account ID of the DevOps/pipeline account |
| `ssm_resource_prefix` | No | `*` | SSM parameter path prefix to scope read access |
| `lambda_resource_prefix` | No | `*` | Lambda function name prefix to scope update access |

### Tightening Permissions

For production, scope the prefixes to your workload:

```json
{
  "lambda_deploy_role": {
    "role_name": "DevOpsLambdaDeployRole",
    "devops_account": "072708757319",
    "ssm_resource_prefix": "my-app/*",
    "lambda_resource_prefix": "my-app-*"
  }
}
```

This limits the role to only read SSM parameters under `/my-app/` and only update Lambda functions whose names start with `my-app-`.

---

## How It Works End-to-End

1. **Pipeline deploys IaC** → CDK creates `DevOpsLambdaDeployRole` in target account (uses CDK bootstrap role)
2. **Services pipeline runs** → CodeBuild builds and pushes Docker image to ECR
3. **Lambda Image Updater runs** (post-push step):
   - Detects target account differs from caller account
   - Calls `sts:AssumeRole` on `arn:aws:iam::{target}:role/DevOpsLambdaDeployRole`
   - Uses assumed-role session to call `ssm:GetParametersByPath` → discovers Lambda ARNs
   - Calls `lambda:GetFunction` → reads current image URI
   - Calls `lambda:UpdateFunctionCode` → deploys new image

---

## No Chicken-and-Egg Problem

A common concern: "If the pipeline creates this role, how can it assume the role on first deploy?"

**Answer:** The CDK deploy step and the Lambda Image Updater use **different roles**:

| Step | Role Used | Created By |
|------|-----------|------------|
| CDK Deploy (create/update stacks) | `cdk-hnb659fds-deploy-role-{account}-{region}` | `cdk bootstrap` |
| Lambda Image Updater (post-deploy) | `DevOpsLambdaDeployRole` | This stack |

On **first deploy**:
1. CDK uses the bootstrap role to create stacks → `DevOpsLambdaDeployRole` gets created ✓
2. Lambda Image Updater runs → role now exists, assumes it successfully ✓

The only prerequisite is that `cdk bootstrap` has been run in the target account with trust to the DevOps account. This is a one-time setup you've already done.

---

## Relationship to cross_account_role_arns

The `pipeline.cross_account_role_arns` config field is a **separate mechanism** for granting CodeBuild additional assume-role permissions for pipeline build steps (e.g., DNS delegation, SSM lookups during `cdk synth`).

The Lambda Image Updater does **not** use `cross_account_role_arns`. It has its own dedicated policy (`AssumeRoleLambdaUpdater`) that grants assume on `DevOpsLambdaDeployRole` and `DevOpsCrossAccountAccessRole` in any account. This means:

- You do **not** need to add `DevOpsLambdaDeployRole` to `cross_account_role_arns`
- `cross_account_role_arns` is only needed if your pipeline build steps (not CDK deploy, not Lambda updater) need to assume roles in other accounts

---

## SSM Exports

When `ssm.auto_export` is enabled, the stack exports:

| SSM Path | Value |
|----------|-------|
| `/{namespace}/role_arn` | Full ARN of the created role |
| `/{namespace}/role_name` | Role name string |

---

## Migration from DevOpsCrossAccountAccessRole

If you have an existing `DevOpsCrossAccountAccessRole` that was created manually:

1. Deploy the `lambda_deploy_role_stack` to create `DevOpsLambdaDeployRole`
2. Update `docker-images.json` to specify `"role_name": "DevOpsLambdaDeployRole"`
3. Verify the pipeline succeeds with the new role
4. Delete the old `DevOpsCrossAccountAccessRole` from the target account (it's no longer needed)

The Lambda Image Updater's caller-side policy (`AssumeRoleLambdaUpdater`) already allows both role names, so you can migrate incrementally.

---

## Troubleshooting

### AccessDenied on AssumeRole

```
An error occurred (AccessDenied) when calling the AssumeRole operation:
User: arn:aws:sts::DEVOPS_ACCOUNT:assumed-role/...
is not authorized to perform: sts:AssumeRole on resource:
arn:aws:iam::TARGET_ACCOUNT:role/DevOpsLambdaDeployRole
```

**Causes:**
1. The role doesn't exist yet in the target account → Deploy the IaC stack first
2. The role's trust policy doesn't include the DevOps account → Check `devops_account` in your config
3. CodeBuild doesn't have the `AssumeRoleLambdaUpdater` policy → Update cdk-factory to latest version

### ParameterNotFound during Lambda discovery

```
SSM parameter not found: /my-app/dev/ecr/my-repo/my-function/arn
```

**Causes:**
1. Lambda stacks haven't been deployed yet (they register SSM parameters on deploy)
2. The `ssm_prefix` in `docker-images.json` doesn't match the Lambda stack's SSM namespace
3. The `ssm_resource_prefix` in the role config is too restrictive

### Lambda update fails after role assumption succeeds

```
An error occurred (ResourceNotFoundException) when calling UpdateFunctionCode
```

**Causes:**
1. Lambda function was deleted or renamed
2. The function ARN in SSM is stale — redeploy the Lambda stack to refresh it
