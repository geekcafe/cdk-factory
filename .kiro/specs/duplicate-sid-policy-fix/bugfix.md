# Bugfix Requirements Document

## Introduction

During CloudFormation deployment, IAM policy creation fails with "Statement IDs (SID) in a single policy must be unique" for lambdas that have permissions on multiple DynamoDB tables (or S3 buckets, or SSM parameter paths) whose names share the same first 20 characters after slug transformation (dash/underscore removal). This blocks deployment of any lambda whose permission config references multiple similarly-named resources.

The bug is in `cdk-factory/src/cdk_factory/constructs/lambdas/policies/policy_docs.py` in the `_get_structured_permission()` method. The slug generation truncates resource names to 20 characters after stripping dashes and underscores, which produces identical SIDs when multiple resource names share a long common prefix.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a lambda has structured DynamoDB permissions on multiple tables whose names, after removing dashes and underscores, share the same first 20 characters (e.g., `v3-acme-saas-alpha-app-database` and `v3-acme-saas-alpha-audit-logger-database` both produce slug `v3acmesaasalphaa`) THEN the system generates duplicate SIDs (e.g., `DynamoDbReadv3acmesaasalphaa` appears twice) causing CloudFormation deployment to fail with "Statement IDs (SID) in a single policy must be unique (Service: Iam, Status Code: 400)"

1.2 WHEN a lambda has structured S3 permissions on multiple buckets whose names, after removing dashes and underscores, share the same first 20 characters THEN the system generates duplicate SIDs (e.g., `S3Readxxxx` appears twice) which would cause the same CloudFormation deployment failure

1.3 WHEN a lambda has structured parameter_store permissions on multiple paths whose slugs (after removing slashes, dashes, and replacing asterisks), share the same first 20 characters THEN the system generates duplicate SIDs (e.g., `SSMReadxxxx` appears twice) which would cause the same CloudFormation deployment failure

### Expected Behavior (Correct)

2.1 WHEN a lambda has structured DynamoDB permissions on multiple tables whose names share a long common prefix THEN the system SHALL generate unique SIDs for each table's permission statements, ensuring no two statements in the same policy document share the same SID

2.2 WHEN a lambda has structured S3 permissions on multiple buckets whose names share a long common prefix THEN the system SHALL generate unique SIDs for each bucket's permission statements, ensuring no two statements in the same policy document share the same SID

2.3 WHEN a lambda has structured parameter_store permissions on multiple paths whose slugs share a long common prefix THEN the system SHALL generate unique SIDs for each path's permission statements, ensuring no two statements in the same policy document share the same SID

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a lambda has structured DynamoDB permissions on a single table THEN the system SHALL CONTINUE TO generate a valid SID and create the policy statement successfully

3.2 WHEN a lambda has structured DynamoDB permissions on multiple tables whose slugs are already unique within 20 characters (e.g., `users-table` and `orders-table`) THEN the system SHALL CONTINUE TO generate unique SIDs and create the policy statements successfully

3.3 WHEN a lambda has structured S3 permissions on a single bucket THEN the system SHALL CONTINUE TO generate a valid SID and create the policy statement successfully

3.4 WHEN a lambda has structured S3 permissions on multiple buckets whose slugs are already unique within 20 characters THEN the system SHALL CONTINUE TO generate unique SIDs and create the policy statements successfully

3.5 WHEN a lambda has structured parameter_store permissions on a single path THEN the system SHALL CONTINUE TO generate a valid SID and create the policy statement successfully

3.6 WHEN a lambda has string-based permissions (e.g., `cognito_admin`, `parameter_store_read`) THEN the system SHALL CONTINUE TO generate the correct permission details unchanged

3.7 WHEN a lambda has inline IAM dict permissions (with explicit `actions` and `resources` keys) THEN the system SHALL CONTINUE TO generate the correct permission details unchanged

3.8 WHEN SIDs are generated THEN the system SHALL CONTINUE TO produce SIDs that are valid IAM SID values (alphanumeric characters only)
