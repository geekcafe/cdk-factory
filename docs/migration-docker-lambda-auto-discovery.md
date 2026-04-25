# Migration Guide: Docker Lambda Auto-Discovery

Unified CLI replaces two legacy tools:

- `LambdaImageUpdater` (Acme-SaaS-DevOps-CDK) — repo-triggered Docker Lambda updates
- `lambda_boto3_utilities.py` (NCA-SaaS-Application) — post-deployment refresh

Both are replaced by `python -m cdk_factory.utilities.docker_lambda_updater`.

---

## 1. Replace `LambdaImageUpdater` in Acme-SaaS-DevOps-CDK

### What changes

The `LambdaImageUpdater` class reads `docker-images.json` and calls `update_function_code` per lambda. Replace it with the Unified CLI in config-driven mode.

### Before (LambdaImageUpdater)

```python
from some_module import LambdaImageUpdater

updater = LambdaImageUpdater(config_path="docker-images.json")
updater.run()
```

### After (Unified CLI)

```bash
python -m cdk_factory.utilities.docker_lambda_updater \
  --config docker-images.json \
  --image-name "acme-analytics/v3/acme-nca-services"
```

### Find/replace pattern

1. Remove any import of `LambdaImageUpdater`
2. Replace the invocation with a shell call to the Unified CLI
3. Update `docker-images.json` to use `ssm_namespace` (see section 3)

---

## 2. Wire the Unified CLI into Acme-NCA-SaaS-IaC CDK Pipeline

### What changes

The legacy `NCA-SaaS-Application` pipeline runs `lambda_boto3_utilities.py` as a post-deployment shell step. In `Acme-NCA-SaaS-IaC`, replace that with the Unified CLI using environment variables.

### Legacy pattern (NCA-SaaS-Application — reference only)

```python
def __get_lambda_shell_steps_commands(self, deployment: Deployment) -> List[str]:
    ssm_docker_path = deployment.get_ssm_parameter_v4(
        resource_type_name="docker-lambdas",
        resource_name="",
        resource_property="",
    )
    ssm_docker_path = ssm_docker_path.rstrip("/")

    commands = [
        "echo discovering and updating Docker Lambda images via SSM",
        f'export SSM_DOCKER_LAMBDAS_PATH="{ssm_docker_path}"',
        f'export AWS_ACCOUNT_NUMBER="{deployment.account}"',
        f'export AWS_REGION="{deployment.region}"',
        "python ./utilities/lambda_boto3_utilities.py",
        "echo Docker Lambda image updates complete",
    ]
    return commands
```

### New pattern (Acme-NCA-SaaS-IaC)

```python
def __get_lambda_shell_steps_commands(self, deployment: Deployment) -> List[str]:
    ssm_docker_path = deployment.get_ssm_parameter_v4(
        resource_type_name="docker-lambdas",
        resource_name="",
        resource_property="",
    )
    ssm_docker_path = ssm_docker_path.rstrip("/")

    commands = [
        "echo discovering and updating Docker Lambda images via SSM",
        f'export SSM_DOCKER_LAMBDAS_PATH="{ssm_docker_path}"',
        f'export AWS_ACCOUNT_NUMBER="{deployment.account}"',
        f'export AWS_REGION="{deployment.region}"',
        "python -m cdk_factory.utilities.docker_lambda_updater",
        "echo Docker Lambda image updates complete",
    ]
    return commands
```

### How it works

When `SSM_DOCKER_LAMBDAS_PATH` is set and no `--config` is provided, the Unified CLI automatically operates in **direct namespace refresh mode**:

1. Discovers all Docker Lambdas under the SSM namespace via `get_parameters_by_path`
2. For each Lambda, reads the current image URI via `get_function`
3. Calls `update_function_code` with the same URI (forces cold-start refresh)
4. Tags each Lambda with `LastImageRefresh` timestamp and `RefreshedBy=deployment-pipeline`

### Environment variables (set by the pipeline)

| Variable | Purpose |
|----------|---------|
| `SSM_DOCKER_LAMBDAS_PATH` | SSM namespace prefix (e.g., `acme-nca-saas/beta/docker-lambdas`) |
| `AWS_ACCOUNT_NUMBER` | Target AWS account ID |
| `AWS_REGION` | Target AWS region |
| `CROSS_ACCOUNT_ROLE_ARN` | (Optional) Full ARN for cross-account role |

### Find/replace pattern

1. Find: `"python ./utilities/lambda_boto3_utilities.py"`
2. Replace: `"python -m cdk_factory.utilities.docker_lambda_updater"`
3. Remove the local `lambda_boto3_utilities.py` file (it's no longer needed)
4. Ensure `cdk-factory` is in the pipeline's Python dependencies

---

## 3. Update `docker-images.json` from `ssm_parameter` to `ssm_namespace`

### What changes

The old format requires a separate `ssm_parameter` path per lambda per deployment. The new format uses `ssm_namespace` — the CLI reads the discovery manifest from SSM to find all lambdas automatically.

### Old format (legacy `ssm_parameter`)

```json
{
  "images": [
    {
      "repo_name": "acme-analytics/v3/acme-nca-services",
      "dockerfile": "Dockerfile",
      "lambda_deployments": [
        {
          "account": "959096737760",
          "region": "us-east-1",
          "ssm_parameter": "/acme-nca-saas/dev/docker-lambdas/user-metrics-v3/arn",
          "tag": "dev"
        }
      ]
    }
  ]
}
```

### New format (`ssm_namespace` auto-discovery)

```json
{
  "images": [
    {
      "repo_name": "acme-analytics/v3/acme-nca-services",
      "dockerfile": "Dockerfile",
      "lambda_deployments": [
        {
          "account": "959096737760",
          "region": "us-east-1",
          "ssm_namespace": "acme-nca-saas/dev/lambda/orchestration",
          "tag": "dev"
        }
      ]
    }
  ]
}
```

### Multiple namespaces (when one ECR repo serves lambdas across stacks)

```json
{
  "lambda_deployments": [
    {
      "account": "123456789012",
      "region": "us-east-1",
      "ssm_namespaces": [
        "acme-nca-saas/prod/lambda/core-services",
        "acme-nca-saas/prod/lambda/api-services"
      ],
      "tag": "latest"
    }
  ]
}
```

### How auto-discovery works

1. The Lambda stack exports a manifest at `/{namespace}/docker-lambdas/manifest`
2. The manifest maps ECR repo names to Lambda SSM path prefixes:
   ```json
   {
     "acme-analytics/v3/acme-nca-services": [
       "/acme-nca-saas/dev/lambda/orchestration/user-metrics-v3",
       "/acme-nca-saas/dev/lambda/orchestration/analysis-send-to-queue"
     ]
   }
   ```
3. The CLI reads the manifest, matches the `repo_name` from the image config, resolves each Lambda ARN from `{path_prefix}/arn`, and updates them

### Find/replace pattern

1. In each deployment entry, remove the `ssm_parameter` field
2. Add `ssm_namespace` with the SSM namespace prefix for that stack (without leading `/`)
3. The namespace is the value configured in the Lambda stack's `ssm.namespace` config
4. Backward compatible: old `ssm_parameter` entries still work during migration

---

## 4. Configure Locked Version Tags for Production

### What changes

Production and higher environments pin Docker Lambda images to specific version tags instead of floating tags like `dev` or `latest`. The Unified CLI supports this via `--locked-versions`.

### Locked versions config (`.docker-locked-versions.json`)

```json
[
  {
    "name": "user-create",
    "tag": "3.3.29",
    "ecr": "acme-analytics/v3/acme-saas-core-services"
  },
  {
    "name": "user-throttle-status",
    "tag": "",
    "ecr": "non-docker (zip deploy)"
  }
]
```

- `name` — matches the Lambda name in SSM (the last segment of the path prefix)
- `tag` — pinned version tag; empty string means skip this lambda
- `ecr` — informational; not used by the CLI for matching

### CLI usage

```bash
# Repo-triggered update with locked versions
python -m cdk_factory.utilities.docker_lambda_updater \
  --config docker-images.json \
  --locked-versions .docker-locked-versions.json

# Post-deployment refresh with locked versions
python -m cdk_factory.utilities.docker_lambda_updater \
  --ssm-namespace "acme-nca-saas/prod/lambda/core-services" \
  --account 123456789012 \
  --region us-east-1 \
  --refresh \
  --locked-versions .docker-locked-versions.json
```

### Per-deployment locked versions in docker-images.json

```json
{
  "lambda_deployments": [
    {
      "account": "123456789012",
      "region": "us-east-1",
      "ssm_namespace": "acme-nca-saas/prod/lambda/core-services",
      "tag": "latest",
      "locked_versions": "configs/pipelines/.docker-locked-versions.json"
    }
  ]
}
```

### Tag resolution order

1. If `--locked-versions` is provided and a matching entry has a non-empty `tag` → use the locked tag
2. If a matching entry has an empty `tag` → skip that lambda entirely
3. If no matching entry → fall back to the deployment-level `tag`

### Dry-run to verify

```bash
python -m cdk_factory.utilities.docker_lambda_updater \
  --config docker-images.json \
  --locked-versions .docker-locked-versions.json \
  --dry-run
```

Dry-run shows the resolved tag source (`locked` vs `deployment`) for each lambda without making changes.

---

## 5. CLI Reference

```
python -m cdk_factory.utilities.docker_lambda_updater [OPTIONS]
```

| Argument | Description |
|----------|-------------|
| `--config PATH` | Path to `docker-images.json` (config-driven mode) |
| `--ssm-namespace NS` | Direct SSM namespace (post-deployment mode) |
| `--account ID` | Target AWS account ID |
| `--region REGION` | Target AWS region |
| `--refresh` | Re-deploy lambdas with current image (cold-start refresh) |
| `--locked-versions PATH` | Path to `.docker-locked-versions.json` |
| `--dry-run` | Preview — no changes made |
| `--image-name NAME` | Filter to a specific ECR repo name |
| `--cross-account-role ROLE` | IAM role name for cross-account access |

At least one of `--config` or `--ssm-namespace` (or `SSM_DOCKER_LAMBDAS_PATH` env var) is required.

### Environment variable fallbacks

| Env Var | Equivalent CLI Arg |
|---------|-------------------|
| `SSM_DOCKER_LAMBDAS_PATH` | `--ssm-namespace` |
| `AWS_ACCOUNT_NUMBER` | `--account` |
| `AWS_REGION` | `--region` |
| `CROSS_ACCOUNT_ROLE_ARN` | `--cross-account-role` |

CLI arguments take precedence over environment variables.

---

## 6. Checklist for Migrating a Workspace

- [ ] Ensure `cdk-factory` is a dependency (editable install or package reference)
- [ ] Ensure Lambda stacks have `ssm.auto_export: true` and `ssm.namespace` configured
- [ ] Deploy Lambda stacks so the discovery manifest SSM parameter is created
- [ ] Update `docker-images.json` entries from `ssm_parameter` to `ssm_namespace`
- [ ] Replace `LambdaImageUpdater` calls with `python -m cdk_factory.utilities.docker_lambda_updater --config ...`
- [ ] Replace `lambda_boto3_utilities.py` pipeline steps with `python -m cdk_factory.utilities.docker_lambda_updater`
- [ ] For production environments, add `--locked-versions` pointing to your `.docker-locked-versions.json`
- [ ] Run with `--dry-run` to verify discovery and tag resolution before going live
- [ ] Remove legacy `lambda_boto3_utilities.py` and `LambdaImageUpdater` references
