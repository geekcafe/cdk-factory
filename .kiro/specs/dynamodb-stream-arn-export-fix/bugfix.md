# Bugfix Requirements Document

## Introduction

CloudFormation deployment fails with "Attribute 'StreamArn' does not exist" when deploying a DynamoDB table with `ssm.auto_export: true`. The auto-export system unconditionally attempts to export `table_stream_arn` for all DynamoDB tables, but when DynamoDB Streams are not enabled on the table, the `table_stream_arn` attribute resolves to a CloudFormation token that fails at deploy time. This blocks any DynamoDB table deployment that uses SSM auto-export without streams enabled.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a DynamoDB table is created without DynamoDB Streams enabled AND `ssm.auto_export` is true THEN the system unconditionally includes `table_stream_arn` in the `RESOURCE_AUTO_EXPORTS` list for the "dynamodb" resource type, causing CloudFormation to fail with "Attribute 'StreamArn' does not exist"

1.2 WHEN `_export_ssm_parameters()` checks for `table_stream_arn` availability using `hasattr(self.table, "table_stream_arn")` THEN the system incorrectly evaluates to `True` because CDK's `TableV2` class always defines `table_stream_arn` as a class property, even when streams are not enabled — the value resolves to an unresolvable CloudFormation token at deploy time

1.3 WHEN the `DynamoDBConfig` class is used to configure a DynamoDB table THEN the system provides no way to specify stream settings (e.g., `stream_specification`), so streams can never be intentionally enabled through configuration

### Expected Behavior (Correct)

2.1 WHEN a DynamoDB table is created without DynamoDB Streams enabled AND `ssm.auto_export` is true THEN the system SHALL skip exporting `table_stream_arn` and only export attributes that exist on the deployed resource (`table_name`, `table_arn`)

2.2 WHEN `_export_ssm_parameters()` determines whether to export `table_stream_arn` THEN the system SHALL check whether DynamoDB Streams are actually enabled in the table configuration rather than relying on `hasattr()`, and only include the stream ARN when streams are explicitly enabled

2.3 WHEN the `DynamoDBConfig` class is used to configure a DynamoDB table THEN the system SHALL support an optional `stream_specification` property that allows users to enable DynamoDB Streams (e.g., `NEW_AND_OLD_IMAGES`, `NEW_IMAGE`, `OLD_IMAGE`, `KEYS_ONLY`)

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a DynamoDB table has DynamoDB Streams enabled AND `ssm.auto_export` is true THEN the system SHALL CONTINUE TO export `table_stream_arn` along with `table_name` and `table_arn` to SSM

3.2 WHEN `ssm.auto_export` is false or SSM is not configured THEN the system SHALL CONTINUE TO skip all SSM parameter exports for the DynamoDB table

3.3 WHEN a DynamoDB table is created with other configurations (GSIs, TTL, replicas, point-in-time recovery) THEN the system SHALL CONTINUE TO create and configure those features correctly regardless of stream settings

3.4 WHEN other resource types (VPC, RDS, Lambda, S3, etc.) use `RESOURCE_AUTO_EXPORTS` THEN the system SHALL CONTINUE TO export their attributes unchanged

---

### Bug Condition

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type DynamoDBTableConfig
  OUTPUT: boolean
  
  // The bug triggers when auto-export is enabled but streams are not enabled on the table
  RETURN X.ssm_auto_export = true AND X.stream_specification = NONE
END FUNCTION
```

### Fix Checking Property

```pascal
// Property: Fix Checking - Stream ARN export is conditional on streams being enabled
FOR ALL X WHERE isBugCondition(X) DO
  result ← deployDynamoDBStack(X)
  ASSERT "table_stream_arn" NOT IN result.exported_ssm_parameters
  AND result.deployment_status = SUCCESS
END FOR
```

### Preservation Checking Property

```pascal
// Property: Preservation Checking - Tables with streams still export stream ARN
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT F(X) = F'(X)
  // Specifically: if streams ARE enabled and auto_export is true,
  // table_stream_arn is still exported
END FOR
```
