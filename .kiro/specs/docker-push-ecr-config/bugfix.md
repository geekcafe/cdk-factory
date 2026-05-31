# Bugfix Requirements Document

## Introduction

The `_do_push` function in `docker_build_cli.py` fails to push Docker images to ECR when no `lambda_deployments` are configured in `docker-images.json`. The function incorrectly couples the ECR push destination (account/region) to Lambda deployment configuration, even though these are separate concerns. An image should be pushable to ECR independently of whether any Lambda functions consume it.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN an image config in `docker-images.json` has no `lambda_deployments` (empty array or missing field) THEN the system prints a warning and skips the push entirely, leaving the image only in the local Docker daemon

1.2 WHEN an image config has `lambda_deployments` disabled (all entries have `"enabled": false`) THEN the system skips all deployments and the image is never pushed to ECR

1.3 WHEN a user wants to push an image to a DevOps ECR account that is separate from Lambda deployment accounts THEN the system provides no mechanism to specify the push destination independently of `lambda_deployments`

### Expected Behavior (Correct)

2.1 WHEN an image config contains an `ecr` field with `account` and `region` THEN the system SHALL use those values to construct the ECR URI and push the image, regardless of whether `lambda_deployments` exists

2.2 WHEN an image config contains both an `ecr` field and `lambda_deployments` THEN the system SHALL use the `ecr` field for the push destination (ecr takes priority over lambda_deployments for determining push target)

2.3 WHEN an image config has no `ecr` field but has valid `lambda_deployments` THEN the system SHALL fall back to deriving ECR account/region from `lambda_deployments` entries (backward compatibility)

2.4 WHEN an image config has neither an `ecr` field nor `lambda_deployments` THEN the system SHALL print a warning and skip the push (no change from current behavior for this edge case)

### Unchanged Behavior (Regression Prevention)

3.1 WHEN an image config has `lambda_deployments` with valid enabled entries and no `ecr` field THEN the system SHALL CONTINUE TO derive ECR URI from deployment account/region and push successfully

3.2 WHEN the push action is invoked THEN the system SHALL CONTINUE TO authenticate with ECR using `aws ecr get-login-password` before pushing

3.3 WHEN tags are resolved for push THEN the system SHALL CONTINUE TO apply version tags, environment tags, and explicit CLI tags in the same manner as before

3.4 WHEN `--tag-version` is specified THEN the system SHALL CONTINUE TO include the computed version as a push tag

3.5 WHEN the `build` or `tag` actions are invoked THEN the system SHALL CONTINUE TO function identically (this fix only affects the `push` action)
