# CodeBuildStep Support in Pipeline Builds

## Overview

CDK Factory now supports **CodeBuildStep** for pipeline builds, enabling you to build Docker images and run custom build processes from external GitHub repositories (public or private).

**Version**: 0.15.17+

---

## Features

✅ **External GitHub repositories** - Build from any GitHub repo  
✅ **Private repository support** - Uses your existing GitHub CodeConnections  
✅ **Custom buildspec files** - Reference buildspec.yml from the source repo  
✅ **Environment configuration** - Specify compute type, Docker image, privileged mode  
✅ **Environment variables** - Pass build-time configuration  
✅ **Automatic detection** - Seamlessly switches between ShellStep and CodeBuildStep  

---

## Configuration

### Basic Example

```json
{
  "builds": [
    {
      "name": "my-docker-build",
      "enabled": true,
      "description": "Build and push Docker image",
      "source": {
        "type": "GITHUB",
        "location": "https://github.com/myorg/myrepo.git",
        "branch": "main"
      },
      "buildspec": "buildspec.yml",
      "environment": {
        "compute_type": "BUILD_GENERAL1_SMALL",
        "image": "aws/codebuild/standard:7.0",
        "type": "LINUX_CONTAINER",
        "privileged_mode": true
      },
      "environment_variables": [
        {
          "name": "AWS_DEFAULT_REGION",
          "value": "us-east-1"
        },
        {
          "name": "AWS_ACCOUNT_ID",
          "value": "{{AWS_ACCOUNT}}"
        },
        {
          "name": "IMAGE_REPO_NAME",
          "value": "my-app"
        }
      ]
    }
  ]
}
```

### Pipeline Stage Integration

```json
{
  "deployments": [{
    "pipeline": {
      "stages": [
        {
          "name": "Build-Docker",
          "builds": [
            "my-docker-build"
          ]
        }
      ]
    }
  }]
}
```

---

## Supported Parameters

### `source` (Required for CodeBuildStep)

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `type` | string | Source type | `"GITHUB"` |
| `location` | string | Repository URL or org/repo | `"https://github.com/org/repo.git"` |
| `branch` | string | Branch to build from | `"main"` |

**Supported URL formats:**
- `https://github.com/org/repo.git`
- `https://github.com/org/repo`
- `org/repo`

### `buildspec` (Optional)

Path to buildspec file in the source repository.

```json
"buildspec": "buildspec.yml"
```

If not specified, you can provide inline `commands` instead.

### `environment` (Optional)

| Field | Type | Description | Values |
|-------|------|-------------|--------|
| `compute_type` | string | Build instance size | `BUILD_GENERAL1_SMALL`, `BUILD_GENERAL1_MEDIUM`, `BUILD_GENERAL1_LARGE`, `BUILD_GENERAL1_2XLARGE` |
| `image` | string | Docker image for builds | `aws/codebuild/standard:7.0` |
| `type` | string | Container type | `LINUX_CONTAINER` |
| `privileged_mode` | boolean | Docker daemon access | `true` for Docker builds |

**Defaults:**
- `compute_type`: `BUILD_GENERAL1_SMALL`
- `image`: `aws/codebuild/standard:7.0`
- `privileged_mode`: `false`

### `environment_variables` (Optional)

Array of environment variables for the build.

```json
"environment_variables": [
  {
    "name": "MY_VAR",
    "value": "my-value",
    "type": "PLAINTEXT"
  },
  {
    "name": "DB_PASSWORD",
    "value": "/prod/db/password",
    "type": "PARAMETER_STORE"
  },
  {
    "name": "API_KEY",
    "value": "prod/api-key",
    "type": "SECRETS_MANAGER"
  }
]
```

**Supported types:**
- `PLAINTEXT` - Plain text value (default)
- `PARAMETER_STORE` - AWS Systems Manager Parameter Store
- `SECRETS_MANAGER` - AWS Secrets Manager

---

## How It Works

### Automatic Detection

The pipeline factory automatically detects whether to create a **ShellStep** or **CodeBuildStep**:

```python
if build.get("source") or build.get("buildspec") or build.get("environment"):
    # Create CodeBuildStep
else:
    # Create ShellStep (traditional inline commands)
```

### GitHub Authentication

**For private repositories**, CDK Factory uses your workload's existing **GitHub CodeConnections** (`code_repository_arn`):

```json
{
  "cdk": {
    "code_repository_arn": "arn:aws:codeconnections:us-east-1:123456789012:connection/abc-123"
  }
}
```

This connection is automatically applied to all GitHub builds, enabling access to private repos without additional configuration.

---

## Use Cases

### 1. Docker Image Build from External Repo

```json
{
  "builds": [{
    "name": "app-docker-build",
    "source": {
      "type": "GITHUB",
      "location": "https://github.com/myorg/my-app.git",
      "branch": "main"
    },
    "buildspec": "buildspec.yml",
    "environment": {
      "privileged_mode": true
    }
  }]
}
```

### 2. Test Application Build

```json
{
  "builds": [{
    "name": "infra-test-app-build",
    "source": {
      "type": "GITHUB",
      "location": "https://github.com/myorg/infra-test.git",
      "branch": "main"
    },
    "buildspec": "buildspec.yml",
    "environment": {
      "compute_type": "BUILD_GENERAL1_SMALL",
      "privileged_mode": true
    },
    "environment_variables": [
      {
        "name": "IMAGE_REPO_NAME",
        "value": "infra-test"
      }
    ]
  }]
}
```

### 3. Traditional Inline Commands (Still Supported)

```json
{
  "builds": [{
    "name": "my-build",
    "pre_steps": [{
      "name": "build-step",
      "commands": [
        "npm install",
        "npm run build"
      ]
    }]
  }]
}
```

---

## Comparison: ShellStep vs CodeBuildStep

| Feature | ShellStep | CodeBuildStep |
|---------|-----------|---------------|
| **Inline commands** | ✅ Yes | ⚠️ Via buildspec object |
| **External source** | ❌ No | ✅ GitHub, CodeCommit |
| **Custom buildspec** | ❌ No | ✅ Yes |
| **Privileged mode** | ❌ No | ✅ Yes (Docker) |
| **Custom environment** | ❌ No | ✅ Compute type, image |
| **Private repos** | ❌ No | ✅ Via CodeConnections |

---

## Best Practices

### 1. Use External Source for Docker Builds

Docker builds require `privileged_mode: true`, which is only available in CodeBuildStep.

```json
{
  "source": { "type": "GITHUB", "location": "..." },
  "environment": { "privileged_mode": true }
}
```

### 2. Separate Build Repos

Keep build logic in dedicated repositories:
- ✅ Application code in one repo
- ✅ Infrastructure code in another repo
- ✅ Build/test utilities in a third repo

This allows each to evolve independently.

### 3. Reuse GitHub Connection

The same `code_repository_arn` can authenticate multiple builds across different repos in your organization.

### 4. Environment Variables for Configuration

Use environment variables to pass workload-specific values:

```json
"environment_variables": [
  {
    "name": "ECR_REPO_NAME",
    "value": "{{WORKLOAD_NAME}}-app"
  }
]
```

---

## Troubleshooting

### Issue: "Source location not specified"

**Symptom:** Build step is skipped with warning.

**Solution:** Ensure `source.location` is provided:
```json
"source": {
  "location": "https://github.com/org/repo.git"
}
```

### Issue: "Access denied to private repository"

**Symptom:** CodeBuild fails to clone the repository.

**Solution:** Verify `code_repository_arn` in your CDK config points to a valid GitHub CodeConnection with access to the repository.

### Issue: Docker commands fail

**Symptom:** `docker build` or `docker push` fails.

**Solution:** Enable privileged mode:
```json
"environment": {
  "privileged_mode": true
}
```

### Issue: Build not running

**Symptom:** CodeBuildStep doesn't execute.

**Solution:** CodeBuildStep currently only runs as `pre_steps` by default. Make sure your build is configured to run at the appropriate stage.

---

## Migration Guide

### From Traditional Builds

**Before (inline commands):**
```json
{
  "builds": [{
    "name": "docker-build",
    "pre_steps": [{
      "name": "build",
      "commands": [
        "./docker-build.sh"
      ]
    }]
  }]
}
```

**After (external source):**
```json
{
  "builds": [{
    "name": "docker-build",
    "source": {
      "type": "GITHUB",
      "location": "https://github.com/org/build-scripts.git"
    },
    "buildspec": "docker-build-spec.yml",
    "environment": {
      "privileged_mode": true
    }
  }]
}
```

---

## Limitations

1. **Source Types:** Currently only `GITHUB` is supported
2. **Step Placement:** CodeBuildStep runs as pre_steps only
3. **Inline Buildspec:** Limited to build phase commands when no buildspec file is specified

---

## Future Enhancements

- [ ] Support for CodeCommit source
- [ ] Support for S3 source
- [ ] Post-step CodeBuildStep execution
- [ ] Artifact passing between steps
- [ ] Build caching configuration
- [ ] VPC configuration for builds

---

## Related Documentation

- [AWS CDK Pipelines](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.pipelines-readme.html)
- [AWS CodeBuild](https://docs.aws.amazon.com/codebuild/)
- [GitHub CodeConnections](https://docs.aws.amazon.com/codepipeline/latest/userguide/connections-github.html)

---

## Questions?

For issues or feature requests, check:
1. This documentation for configuration examples
2. CDK Factory GitHub repository
3. Your buildspec.yml syntax in the source repository
