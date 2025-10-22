# ECR Cross-Account Access Configuration

## Overview

The ECR stack now supports flexible cross-account access policies that allow multiple AWS services (Lambda, ECS, CodeBuild, etc.) to pull images from your ECR repositories across different AWS accounts.

## Features

✅ **Multiple AWS Accounts** - Grant access to multiple AWS accounts  
✅ **Multiple Services** - Support for Lambda, ECS, CodeBuild, CodePipeline, EC2  
✅ **Custom Conditions** - Add IAM condition blocks for fine-grained control  
✅ **Custom Actions** - Specify which ECR actions each service can perform  
✅ **Backward Compatible** - Existing configs continue to work with default Lambda access  
✅ **Disable Option** - Explicitly disable cross-account access when not needed  

---

## Configuration Options

### Minimal Configuration (Legacy - Lambda Only)

When no `cross_account_access` is specified, the stack automatically configures Lambda-only access:

```json
{
  "name": "my-repo",
  "image_scan_on_push": "true",
  "empty_on_delete": "false"
}
```

**What this creates:**
- Account principal policy for the deployment account
- Lambda service principal policy with sourceArn condition

---

### Multi-Service Configuration

For advanced use cases with multiple services:

```json
{
  "name": "backend-api",
  "image_scan_on_push": "true",
  "auto_delete_untagged_images_in_days": 7,
  "cross_account_access": {
    "enabled": true,
    "accounts": ["123456789012", "987654321098"],
    "services": [
      {
        "name": "lambda",
        "actions": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
        "condition": {
          "StringLike": {
            "aws:sourceArn": "arn:aws:lambda:*:*:function:*"
          }
        }
      },
      {
        "name": "ecs-tasks",
        "actions": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
      },
      {
        "name": "codebuild",
        "actions": [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchCheckLayerAvailability"
        ]
      }
    ]
  }
}
```

---

### Disable Cross-Account Access

For repositories in the same account as devops or when cross-account access is not needed:

```json
{
  "name": "internal-service",
  "cross_account_access": {
    "enabled": false
  }
}
```

---

## Service Configuration

### Service Name Auto-Detection

The stack automatically infers service principals from common service names:

| Service Name | Inferred Principal |
|--------------|-------------------|
| `lambda` | `lambda.amazonaws.com` |
| `ecs` / `ecs-tasks` | `ecs-tasks.amazonaws.com` |
| `codebuild` | `codebuild.amazonaws.com` |
| `codepipeline` | `codepipeline.amazonaws.com` |
| `ec2` | `ec2.amazonaws.com` |

### Explicit Service Principal

You can also specify the service principal explicitly:

```json
{
  "name": "custom-service",
  "service_principal": "my-custom-service.amazonaws.com",
  "actions": ["ecr:BatchGetImage"]
}
```

---

## Common Use Cases

### 1. Lambda Functions Across Multiple Accounts

```json
{
  "cross_account_access": {
    "accounts": ["111111111111", "222222222222", "333333333333"],
    "services": [
      {
        "name": "lambda",
        "condition": {
          "StringLike": {
            "aws:sourceArn": "arn:aws:lambda:*:*:function:myapp-*"
          }
        }
      }
    ]
  }
}
```

### 2. ECS Tasks with Fargate

```json
{
  "cross_account_access": {
    "services": [
      {
        "name": "ecs-tasks",
        "actions": [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchCheckLayerAvailability"
        ]
      }
    ]
  }
}
```

### 3. CI/CD Pipeline with CodeBuild

```json
{
  "cross_account_access": {
    "accounts": ["123456789012"],
    "services": [
      {
        "name": "codebuild",
        "actions": [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchCheckLayerAvailability",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload"
        ]
      }
    ]
  }
}
```

### 4. Mixed Services (Lambda + ECS + CodeBuild)

```json
{
  "cross_account_access": {
    "accounts": ["123456789012", "987654321098"],
    "services": [
      {
        "name": "lambda",
        "actions": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
      },
      {
        "name": "ecs-tasks",
        "actions": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
      },
      {
        "name": "codebuild",
        "actions": [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchCheckLayerAvailability"
        ]
      }
    ]
  }
}
```

---

## IAM Conditions

You can add IAM condition blocks for fine-grained access control:

```json
{
  "name": "lambda",
  "condition": {
    "StringLike": {
      "aws:sourceArn": "arn:aws:lambda:us-east-1:123456789012:function:prod-*"
    },
    "StringEquals": {
      "aws:PrincipalOrgID": "o-xxxxxxxxxx"
    }
  }
}
```

### Common Condition Keys

| Condition Key | Description | Example |
|--------------|-------------|---------|
| `aws:sourceArn` | Restrict to specific ARN patterns | `arn:aws:lambda:*:*:function:myapp-*` |
| `aws:PrincipalOrgID` | Restrict to AWS Organization | `o-xxxxxxxxxx` |
| `aws:PrincipalAccount` | Restrict to specific accounts | `["123456789012"]` |
| `aws:userid` | Restrict to specific IAM users/roles | `AIDAI*` |

---

## ECR Actions Reference

### Read-Only Actions
- `ecr:BatchGetImage` - Pull images
- `ecr:GetDownloadUrlForLayer` - Download image layers
- `ecr:BatchCheckLayerAvailability` - Check if layers exist
- `ecr:DescribeImages` - List image metadata
- `ecr:DescribeRepositories` - Repository information

### Write Actions (CI/CD)
- `ecr:PutImage` - Push images
- `ecr:InitiateLayerUpload` - Start upload
- `ecr:UploadLayerPart` - Upload layer data
- `ecr:CompleteLayerUpload` - Finish upload

---

## Troubleshooting

### Cross-Account Access Not Working

1. **Check if same account**: If deployment account == devops account, cross-account access is skipped
2. **Check enabled flag**: Ensure `enabled: true` in configuration
3. **Check logs**: Look for "Setting up configurable cross-account access" messages
4. **Verify IAM trust**: Ensure the consuming service has proper IAM role trust relationships

### Service Principal Not Added

1. **Check service name**: Must match auto-detected names or provide explicit `service_principal`
2. **Check logs**: Look for "Unknown service principal" warnings
3. **Verify actions**: Ensure actions array is not empty

---

## Migration from Legacy

**Old (implicit):**
```json
{
  "name": "my-repo",
  "image_scan_on_push": "true"
}
```

**New (explicit, same behavior):**
```json
{
  "name": "my-repo",
  "image_scan_on_push": "true",
  "cross_account_access": {
    "accounts": ["123456789012"],
    "services": [
      {
        "name": "lambda"
      }
    ]
  }
}
```

**No breaking changes** - the old configuration continues to work!

---

## Examples

See sample configurations in `samples/ecr/`:
- `ecr_multi_service_cross_account.json` - Full multi-service example
- `ecr_legacy_lambda_only.json` - Legacy Lambda-only access
- `ecr_disabled_cross_account.json` - Disabled cross-account access
