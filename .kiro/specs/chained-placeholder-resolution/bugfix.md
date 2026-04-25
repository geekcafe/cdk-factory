# Bugfix Requirements Document

## Introduction

The `CdkConfig.__resolved_config()` method builds a replacements dictionary from `cdk.parameters` and passes it to `JsonLoadingUtility.recursive_replace()` to resolve `{{PLACEHOLDER}}` tokens in config.json. When a parameter's `value` field itself contains a placeholder reference to another parameter (a "chained reference"), the single-pass replacement in `recursive_replace()` leaves those inner placeholders unresolved. This causes pipeline failures when the final config still contains literal `{{AWS_ACCOUNT}}` or `{{DEPLOYMENT_NAMESPACE}}` tokens in values like `TARGET_ACCOUNT_ROLE_ARN` and `TARGET_HOSTED_ZONE_ID_SSM_PARAMETER_NAME`.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a parameter's `value` contains a placeholder reference to another parameter (e.g., `TARGET_ACCOUNT_ROLE_ARN` has value `"arn:aws:iam::{{AWS_ACCOUNT}}:role/DevOpsCrossAccountAccessRole"`) THEN the system produces a resolved config where the inner `{{AWS_ACCOUNT}}` placeholder remains as a literal string in the output

1.2 WHEN a parameter's `value` contains a placeholder reference to another parameter (e.g., `TARGET_HOSTED_ZONE_ID_SSM_PARAMETER_NAME` has value `"/acme-saas/{{DEPLOYMENT_NAMESPACE}}/route53/hosted-zone-id"`) THEN the system produces a resolved config where the inner `{{DEPLOYMENT_NAMESPACE}}` placeholder remains as a literal string in the output

1.3 WHEN the replacements dictionary is applied via `recursive_replace()` and a replacement value itself contains a placeholder that was already iterated past THEN the system does not re-resolve the newly introduced placeholder, leaving it unresolved in the final config

1.4 WHEN the resolved config contains unresolved placeholders from chained references THEN the `_check_unresolved_placeholders` method raises a `ValueError` or the pipeline fails at runtime with errors like `"Failed to assume role arn:aws:iam::{{AWS_ACCOUNT}}:role/..."`

### Expected Behavior (Correct)

2.1 WHEN a parameter's `value` contains a placeholder reference to another parameter (e.g., `TARGET_ACCOUNT_ROLE_ARN` has value `"arn:aws:iam::{{AWS_ACCOUNT}}:role/DevOpsCrossAccountAccessRole"`) THEN the system SHALL fully resolve the inner `{{AWS_ACCOUNT}}` placeholder to its concrete value (e.g., `"959096737760"`) in the final config output

2.2 WHEN a parameter's `value` contains a placeholder reference to another parameter (e.g., `TARGET_HOSTED_ZONE_ID_SSM_PARAMETER_NAME` has value `"/acme-saas/{{DEPLOYMENT_NAMESPACE}}/route53/hosted-zone-id"`) THEN the system SHALL fully resolve the inner `{{DEPLOYMENT_NAMESPACE}}` placeholder to its concrete value (e.g., `"beta"`) in the final config output

2.3 WHEN the replacements dictionary contains values that themselves reference other placeholders THEN the system SHALL resolve all transitive placeholder references so that no `{{...}}` tokens remain in any replacement value before applying replacements to the config

2.4 WHEN all chained references are resolved THEN the system SHALL produce a config where `_check_unresolved_placeholders` passes without raising any errors for parameters that have valid resolution chains

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a parameter's `value` is a simple literal with no placeholder references (e.g., `DEVOPS_ACCOUNT` with value `"974817967438"`) THEN the system SHALL CONTINUE TO resolve the placeholder to that literal value unchanged

3.2 WHEN a parameter's value is resolved from CDK context, environment variables, or static values without any chained references THEN the system SHALL CONTINUE TO apply those values correctly via `recursive_replace()`

3.3 WHEN the config contains `__inherits__` or `__imports__` references THEN the system SHALL CONTINUE TO resolve those file-based references before placeholder substitution as it does today

3.4 WHEN a placeholder has no matching parameter definition and is located in a skipped section (`cdk` or `deployments`) THEN the system SHALL CONTINUE TO leave it unresolved without raising an error, as those are resolved by a different pipeline stage

3.5 WHEN the replacements dictionary is empty THEN the system SHALL CONTINUE TO return the config unchanged without errors
