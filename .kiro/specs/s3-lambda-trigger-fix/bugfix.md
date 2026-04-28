# Bugfix Requirements Document

## Introduction

The `post-file-upload-processing-v3` Lambda function is never invoked when files are uploaded to the S3 upload bucket via presigned POST URLs. Files upload successfully to the bucket, but the Lambda shows zero metrics and no CloudWatch logs — it never executes. The root cause is an S3 event type mismatch: the Lambda trigger is configured to listen for `s3:ObjectCreated:Put` events, but presigned POST uploads (`generate_presigned_post()`) fire `s3:ObjectCreated:Post` events. The previous deployment avoided this issue by using EventBridge with the `Object Created` detail type, which catches all object creation methods regardless of upload mechanism.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a file is uploaded to the S3 upload bucket via a presigned POST URL (which fires an `s3:ObjectCreated:Post` event) THEN the system does not invoke the `post-file-upload-processing-v3` Lambda because the trigger is configured with `put_object` (mapped to `s3:ObjectCreated:Put`), which does not match the `Post` event type

1.2 WHEN the Lambda trigger config specifies `"event_type": ["put_object"]` and the `lambda_triggers.py` shorthand map resolves this to `s3:ObjectCreated:Put` THEN the system only subscribes to `Put` events, silently ignoring `Post`, `Copy`, and `CompleteMultipartUpload` creation events

### Expected Behavior (Correct)

2.1 WHEN a file is uploaded to the S3 upload bucket via a presigned POST URL (which fires an `s3:ObjectCreated:Post` event) THEN the system SHALL invoke the `post-file-upload-processing-v3` Lambda, matching the behavior of the previous EventBridge-based deployment that caught all object creation methods

2.2 WHEN the Lambda trigger config specifies `"event_type": ["object_created"]` and the `lambda_triggers.py` shorthand map resolves this to `s3:ObjectCreated:*` THEN the system SHALL subscribe to all S3 object creation events (Put, Post, Copy, CompleteMultipartUpload), ensuring the Lambda is triggered regardless of the upload method used

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a file is uploaded to the S3 upload bucket via a standard PUT request (which fires an `s3:ObjectCreated:Put` event) THEN the system SHALL CONTINUE TO invoke the `post-file-upload-processing-v3` Lambda, since `s3:ObjectCreated:*` is a superset that includes `Put` events

3.2 WHEN the `lambda_triggers.py` shorthand map resolves other event type shorthands (e.g., `delete_object` → `s3:ObjectRemoved:Delete`, `object_removed` → `s3:ObjectRemoved:*`) THEN the system SHALL CONTINUE TO map those shorthands to their correct S3 event type strings without any change

3.3 WHEN other Lambda functions in the system use `put_object` as their trigger event type and only need to respond to PUT uploads THEN the system SHALL CONTINUE TO trigger those Lambdas only on `s3:ObjectCreated:Put` events — the fix is scoped to the `post-file-upload-processing-v3` config, not the shorthand map itself

3.4 WHEN the S3 trigger setup in `lambda_stack.py` processes the resolved event type strings and configures bucket notifications THEN the system SHALL CONTINUE TO correctly map event strings to CDK `s3.EventType` enum values and apply prefix/suffix filters as before


---

## Bug Condition Derivation

### Bug Condition Function

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type S3TriggerConfig
  OUTPUT: boolean

  // The bug occurs when the configured event_type is "put_object" (resolving to
  // s3:ObjectCreated:Put) but the actual upload method is presigned POST (which
  // fires s3:ObjectCreated:Post). More generally, the bug condition is:
  // the config uses a narrow event type that does not cover the actual upload method.
  RETURN X.event_type CONTAINS "put_object"
     AND X.actual_upload_method = "presigned_post"
END FUNCTION
```

### Property Specification — Fix Checking

```pascal
// Property: Fix Checking — Presigned POST uploads trigger the Lambda
FOR ALL X WHERE isBugCondition(X) DO
  config' ← applyFix(X)  // change event_type from ["put_object"] to ["object_created"]
  resolved_events ← resolveShorthand(config'.event_type)
  ASSERT "s3:ObjectCreated:*" IN resolved_events
  ASSERT s3PostEvent IS MATCHED BY "s3:ObjectCreated:*"
  ASSERT lambda_is_invoked(config', "s3:ObjectCreated:Post") = TRUE
END FOR
```

### Preservation Goal — Preservation Checking

```pascal
// Property: Preservation Checking — Non-buggy configs behave identically
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT resolveShorthand(X.event_type) = resolveShorthand(X.event_type)
  // The shorthand map and lambda_stack.py trigger setup are unchanged,
  // so all other Lambda trigger configurations produce identical behavior.
END FOR
```
