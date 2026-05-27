# Pipeline Commands

CLI modules for CI/CD pipeline steps — CDK synth, Docker build/tag/push, unit tests, SSM version publishing, Lambda image updates, CodeArtifact publishing, and a unified orchestrator.

These commands run *inside* pipeline build steps (CodeBuild, GitHub Actions, etc.) and are distinct from the CDK Pipeline *constructs* (`pipeline_factory.py`, `stage.py`) that define CodePipeline infrastructure.

## Quick Start

```bash
# Install cdk-factory (includes all pipeline commands)
pip install cdk-factory>=1.5.0

# Run the unified pipeline CLI (does everything)
python3 -m cdk_factory.pipeline.commands.unified_pipeline_cli \
    --run-tests \
    --deploy-images \
    --publish-code-artifact \
    --project-root /path/to/project
```

Or use individual commands for fine-grained control:

```bash
# CDK synth
python -m cdk_factory.pipeline.synth.cdk_synth_exec \
    --project-root /path/to/project \
    --cdk-dir devops/cdk-iac

# Run unit tests
python -m cdk_factory.pipeline.commands.unit_tests_cli \
    --project-root /path/to/project

# Docker build/tag/push
python -m cdk_factory.pipeline.commands.docker_build_cli \
    --package-name my_package \
    --config docker-images.json \
    --action build

# Publish version to SSM
python -m cdk_factory.pipeline.commands.parameter_store_cli \
    --app-name my-app \
    --project-root /path/to/project

# Update Lambda images
python -m cdk_factory.pipeline.commands.lambda_image_updater \
    --config docker-images.json

# Publish to CodeArtifact
python -m cdk_factory.pipeline.publishing.codeartifact_publish \
    --project-root /path/to/project
```

## Module Reference

### Unified Pipeline CLI

The orchestrator that auto-detects project configuration and runs build/deploy steps in a fixed order.

```
python3 -m cdk_factory.pipeline.commands.unified_pipeline_cli [OPTIONS]
```

| Flag | Description |
|------|-------------|
| `--run-tests` | Run unit tests |
| `--deploy-images` | Build, tag, push Docker images + SSM publish + Lambda update |
| `--publish-code-artifact` | Build and publish Python package to CodeArtifact |
| `--project-root PATH` | Project root directory (defaults to `CODEBUILD_SRC_DIR` or cwd) |

**Behavior:**
- Exits with code 1 if no action flags are provided
- Reads package name from `pyproject.toml` at the project root
- Derives app name by replacing underscores with hyphens (`my_cool_app` → `my-cool-app`)
- Executes steps in fixed order: run-tests → deploy-images → publish-code-artifact
- Halts on step failure and exits non-zero

**Step execution when `--deploy-images` is enabled:**
1. Docker Build (all images in `docker-images.json`)
2. Docker Tag (version + environment tags)
3. Docker Push (to ECR)
4. SSM Version Publish (write version to Parameter Store)
5. Lambda Image Update (update Lambda function image URIs)

---

### CDK Synth Exec

Resolves the project root and CDK directory, then runs `npx cdk synth`.

```
python -m cdk_factory.pipeline.synth.cdk_synth_exec [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--project-root PATH` | `CODEBUILD_SRC_DIR` or cwd | Project root directory |
| `--cdk-dir PATH` | `devops/cdk-iac` | CDK app directory relative to project root |
| `--operation OP` | `synth` | CDK operation to perform |

**Project root resolution order:**
1. `--project-root` flag (if provided)
2. `CODEBUILD_SRC_DIR` environment variable
3. Current working directory

**Errors:**
- `FileNotFoundError` if the resolved CDK directory doesn't exist
- `EnvironmentError` if `npx` is not on PATH
- Propagates non-zero exit code from `npx cdk synth`

---

### Docker Build CLI

Builds, tags, and pushes Docker images using configuration from `docker-images.json`.

```
python -m cdk_factory.pipeline.commands.docker_build_cli [OPTIONS]
```

| Flag | Required | Description |
|------|----------|-------------|
| `--package-name NAME` | Yes | Python package name |
| `--action ACTION` | Yes | `build`, `tag`, or `push` |
| `--config PATH` | No | Path to `docker-images.json` |
| `--tag NAME` | No | Explicit tag(s) to apply (repeatable) |
| `--tag-version` | No | Include computed version as a tag |
| `--project-root PATH` | No | Project root directory |

**Version computation:**
1. Reads base version from `pyproject.toml` (e.g., `3.0.0`)
2. Computes git-based build number for the `major.minor` prefix
3. Produces full version (e.g., `3.0.47`)
4. Updates `pyproject.toml` and `version.py` with the computed version

---

### Unit Tests CLI

Discovers requirements files, installs dependencies, and runs pytest.

```
python -m cdk_factory.pipeline.commands.unit_tests_cli [OPTIONS]
```

| Flag | Description |
|------|-------------|
| `--project-root PATH` | Project root (defaults to `CODEBUILD_SRC_DIR` or cwd) |
| `--ignore-integration` | Skip integration tests (default: true) |

**Behavior:**
1. Discovers all `requirements*.txt` files in the project root
2. Installs dependencies from each file via pip
3. Installs the package in editable mode
4. Runs pytest on `tests/` (excluding `tests/integration/` by default)
5. Exits non-zero if pip install or pytest fails

---

### Parameter Store CLI

Publishes version information to AWS SSM Parameter Store.

```
python -m cdk_factory.pipeline.commands.parameter_store_cli [OPTIONS]
```

| Flag | Required | Description |
|------|----------|-------------|
| `--app-name NAME` | Yes | Application name (used in SSM path) |
| `--project-root PATH` | No | Project root directory |

Writes the computed version to `/<app-name>/version` in SSM Parameter Store with retry logic for transient AWS errors.

---

### Lambda Image Updater

Updates Lambda function configurations to reference new Docker image URIs after ECR push.

```
python -m cdk_factory.pipeline.commands.lambda_image_updater [OPTIONS]
```

| Flag | Required | Description |
|------|----------|-------------|
| `--config PATH` | Yes | Path to `docker-images.json` |
| `--image-name NAME` | No | Update only this image (partial match) |
| `--dry-run` | No | Show what would be updated without making changes |
| `--cross-account-role ROLE` | No | IAM role for cross-account access |

**Behavior:**
- Reads Lambda deployments from `docker-images.json`
- Supports SSM prefix-based auto-discovery of Lambda functions
- Supports legacy SSM parameter-based Lambda resolution
- Retries on ECR propagation delays (AccessDeniedException)
- Reports failures per function, continues processing remaining
- Exits non-zero if any update failed

---

### CodeArtifact Publisher

Builds and publishes Python packages to AWS CodeArtifact.

```
python -m cdk_factory.pipeline.publishing.codeartifact_publish [OPTIONS]
```

| Flag | Description |
|------|-------------|
| `--project-root PATH` | Project root (defaults to `CODEBUILD_SRC_DIR` or cwd) |
| `--skip-login` | Skip CodeArtifact authentication |
| `--skip-build` | Skip building the package |
| `--skip-upload` | Skip uploading to CodeArtifact |

**Required environment variables (for authentication):**
- `CODE_ARTIFACT_DOMAIN` — CodeArtifact domain name
- `CODE_ARTIFACT_DOMAIN_OWNER` — AWS account ID owning the domain
- `CODE_ARTIFACT_REPOSITORY` — Repository name
- `AWS_REGION` or `AWS_DEFAULT_REGION` — AWS region

---

## Configuration

### docker-images.json

The Docker build, Lambda updater, and unified CLI all read from this file:

```json
{
  "images": [
    {
      "repo_name": "my-org/my-app",
      "dockerfile": "Dockerfile",
      "lambda_deployments": [
        {
          "account": "111111111111",
          "region": "us-east-1",
          "ssm_prefix": "my-app/dev",
          "tag": "latest",
          "enabled": true,
          "role_name": "DevOpsCrossAccountAccessRole",
          "ecr_account": "222222222222"
        }
      ]
    }
  ]
}
```

| Field | Description |
|-------|-------------|
| `repo_name` | ECR repository path (lowercase) |
| `dockerfile` | Relative path to Dockerfile |
| `lambda_deployments[].account` | Target AWS account for Lambda functions |
| `lambda_deployments[].region` | AWS region (default: `us-east-1`) |
| `lambda_deployments[].ssm_prefix` | SSM path prefix for auto-discovering Lambda ARNs |
| `lambda_deployments[].ssm_parameter` | Legacy: direct SSM parameter path to Lambda ARN |
| `lambda_deployments[].tag` | Image tag to deploy (default: `latest`) |
| `lambda_deployments[].enabled` | Enable/disable this deployment (default: `true`) |
| `lambda_deployments[].role_name` | IAM role for cross-account access |
| `lambda_deployments[].ecr_account` | Account owning the ECR repo (defaults to caller) |

### pyproject.toml

The pipeline commands read project metadata from `pyproject.toml`:

```toml
[project]
name = "my-package"
version = "1.0.0"
```

- `name` — Used by the unified CLI to derive the app name
- `version` — Base version for git-based build number computation

---

## Docker Tag Resolution

Tags are resolved based on the deployment environment:

| Environment | Tags |
|-------------|------|
| `prod` | `[version]` |
| `dev`, `integration` | `[version, environment, "latest"]` |
| Other (staging, qa, etc.) | `[version, "latest"]` |

The environment is read from the `ENVIRONMENT` or `ENV` environment variable.

---

## Consumer Migration Guide

If you're migrating from `aplos-saas-devops-cdk` to `cdk-factory`:

### 1. Update dependencies

```diff
- aplos-saas-devops-cdk>=1.0.0
+ cdk-factory>=1.5.0
```

### 2. Update shell script invocations

```diff
- python -m aplos_saas_devops_cdk.synth.cdk_synth_exec --project-root "$PROJECT_ROOT" --cdk-dir "devops/cdk-iac"
+ python -m cdk_factory.pipeline.synth.cdk_synth_exec --project-root "$PROJECT_ROOT" --cdk-dir "devops/cdk-iac"
```

```diff
- python3 -m aplos_saas_devops_cdk.commands.unified_pipeline_cli --run-tests --deploy-images --publish-code-artifact
+ python3 -m cdk_factory.pipeline.commands.unified_pipeline_cli --run-tests --deploy-images --publish-code-artifact
```

### 3. Import path mapping

| Old Import | New Import |
|-----------|-----------|
| `aplos_saas_devops_cdk.synth.cdk_synth_exec` | `cdk_factory.pipeline.synth.cdk_synth_exec` |
| `aplos_saas_devops_cdk.commands.unified_pipeline_cli` | `cdk_factory.pipeline.commands.unified_pipeline_cli` |
| `aplos_saas_devops_cdk.commands.docker_build_cli` | `cdk_factory.pipeline.commands.docker_build_cli` |
| `aplos_saas_devops_cdk.commands.unit_tests_cli` | `cdk_factory.pipeline.commands.unit_tests_cli` |
| `aplos_saas_devops_cdk.commands.parameter_store_cli` | `cdk_factory.pipeline.commands.parameter_store_cli` |
| `aplos_saas_devops_cdk.commands.lambda_image_updater` | `cdk_factory.pipeline.commands.lambda_image_updater` |
| `aplos_saas_devops_cdk.publishing.codeartifact_publish` | `cdk_factory.pipeline.publishing.codeartifact_publish` |
| `aplos_saas_devops_cdk.versioning.*` | `cdk_factory.pipeline.versioning.*` |
| `aplos_saas_devops_cdk.ssm.version_publisher` | `cdk_factory.pipeline.ssm.version_publisher` |
| `aplos_saas_devops_cdk.conventions.*` | `cdk_factory.pipeline.conventions.*` |

### 4. Key behavioral change

`derive_app_name()` no longer strips any vendor prefix. It only replaces underscores with hyphens:
- `asset_workbench_workload` → `asset-workbench-workload`
- `my_cool_app` → `my-cool-app`

CLI arguments are fully backward-compatible. Deprecated arguments are accepted without error (with a warning to stderr).

---

## Example: CodeBuild buildspec

```yaml
version: 0.2

phases:
  install:
    commands:
      - pip install cdk-factory>=1.5.0

  build:
    commands:
      - python3 -m cdk_factory.pipeline.commands.unified_pipeline_cli
          --run-tests
          --deploy-images
          --publish-code-artifact
          --project-root $CODEBUILD_SRC_DIR
```

## Example: Bootstrap Shell Script

```bash
#!/bin/bash
set -e

PROJECT_ROOT="${CODEBUILD_SRC_DIR:-$(pwd)}"

# CodeArtifact login
bash "$PROJECT_ROOT/devops/cdk-iac/commands/codeartifact-login.sh"

# Install pipeline dependencies
pip install -r "$PROJECT_ROOT/devops/cdk-iac/requirements.cdk.txt"

# Run the unified pipeline
python3 -m cdk_factory.pipeline.commands.unified_pipeline_cli \
    --run-tests \
    --deploy-images \
    --publish-code-artifact \
    --project-root "$PROJECT_ROOT"
```

---

## Utilities (for library consumers)

These modules can be imported directly if you need programmatic access:

```python
from cdk_factory.pipeline.conventions.template_render import render_template
from cdk_factory.pipeline.conventions.docker_tags import resolve_docker_tags
from cdk_factory.pipeline.versioning.pyproject_version import read_project_version_from_pyproject
from cdk_factory.pipeline.versioning.pyproject_version_writer import update_version_in_pyproject
from cdk_factory.pipeline.versioning.version_file_writer import update_version_in_version_py
from cdk_factory.pipeline.ssm.version_publisher import publish_version_to_ssm
```

### Template Renderer

```python
from cdk_factory.pipeline.conventions.template_render import render_template

result = render_template("/{{APP}}/{{ENV}}/version", {"APP": "my-app", "ENV": "prod"})
# → "/my-app/prod/version"
```

### Docker Tag Resolver

```python
from cdk_factory.pipeline.conventions.docker_tags import resolve_docker_tags

tags = resolve_docker_tags(environment="dev", version="1.2.3")
# → ["1.2.3", "dev", "latest"]

tags = resolve_docker_tags(environment="prod", version="1.2.3")
# → ["1.2.3"]
```

### Version Reader/Writer

```python
from cdk_factory.pipeline.versioning.pyproject_version import read_project_version_from_pyproject
from cdk_factory.pipeline.versioning.pyproject_version_writer import update_version_in_pyproject

version = read_project_version_from_pyproject("/path/to/project")
update_version_in_pyproject("/path/to/project", "2.0.0")
```

### SSM Version Publisher

```python
import boto3
from cdk_factory.pipeline.ssm.version_publisher import publish_version_to_ssm

ssm = boto3.client("ssm")
param_name = publish_version_to_ssm(
    ssm_client=ssm,
    version="1.2.3",
    parameter_name_template="/{{APP}}/version",
    template_values={"APP": "my-app"},
)
# Writes "1.2.3" to "/my-app/version"
```
