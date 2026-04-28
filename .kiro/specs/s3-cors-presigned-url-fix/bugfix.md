# Bugfix Requirements Document

## Introduction

S3 presigned URL uploads fail with a 403 Forbidden error on the browser's OPTIONS preflight request when using buckets deployed through cdk-factory's `S3BucketConstruct`. The root cause is that cdk-factory has no CORS configuration support — neither `S3BucketConfig` nor `S3BucketConstruct` handle CORS rules. The old deployment (`Acme-SaaS-Application`) explicitly configured CORS on its S3 buckets (allowed methods: GET/POST/PUT, allowed origins: `*`, allowed headers: `*`, max age: 3600), but the new deployment (`Acme-SaaS-IaC`) uses cdk-factory which lacks this capability entirely. This causes the browser to receive a 403 when it sends the mandatory CORS preflight OPTIONS request before the presigned URL POST, blocking all browser-based file uploads.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a browser sends an OPTIONS preflight request to an S3 bucket deployed via cdk-factory's `S3BucketConstruct` (e.g., from origin `https://v3.alpha.acme.com` to `v3-acme-saas-alpha-analysis-upload-files.s3.amazonaws.com`) THEN the system returns a 403 Forbidden because no CORS configuration exists on the bucket

1.2 WHEN a browser attempts a presigned URL POST upload to an S3 bucket deployed via cdk-factory THEN the system never executes the POST because the preceding OPTIONS preflight fails with 403

1.3 WHEN a consumer of cdk-factory specifies CORS settings in their S3 bucket JSON configuration (e.g., `s3-analysis-uploads.json`) THEN the system ignores those settings because `S3BucketConfig` has no CORS property and `S3BucketConstruct` does not apply CORS rules

### Expected Behavior (Correct)

2.1 WHEN a browser sends an OPTIONS preflight request to an S3 bucket deployed via cdk-factory's `S3BucketConstruct` that has CORS rules configured THEN the system SHALL return a successful preflight response (200) with the appropriate CORS headers (Access-Control-Allow-Origin, Access-Control-Allow-Methods, Access-Control-Allow-Headers)

2.2 WHEN a browser attempts a presigned URL POST upload to an S3 bucket deployed via cdk-factory that has CORS rules configured THEN the system SHALL allow the POST to execute after the OPTIONS preflight succeeds

2.3 WHEN a consumer of cdk-factory specifies CORS settings in their S3 bucket JSON configuration THEN the system SHALL parse those settings via `S3BucketConfig` and apply them as `s3.CorsRule` entries on the bucket in `S3BucketConstruct`

### Unchanged Behavior (Regression Prevention)

3.1 WHEN an S3 bucket configuration does not include any CORS settings THEN the system SHALL CONTINUE TO create the bucket without CORS rules (no CORS by default)

3.2 WHEN an S3 bucket is configured with `use_existing` set to true THEN the system SHALL CONTINUE TO import the existing bucket without attempting to modify its CORS configuration

3.3 WHEN an S3 bucket configuration includes other existing properties (encryption, versioning, removal_policy, block_public_access, enforce_ssl, access_control, lifecycle_rules, event_bridge) THEN the system SHALL CONTINUE TO apply those properties correctly and unchanged

3.4 WHEN an S3 bucket is created without CORS configuration THEN the system SHALL CONTINUE TO enforce SSL, block public access, and apply all other security settings as before


---

## Bug Condition Derivation

### Bug Condition Function

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type S3BucketDeployment
  OUTPUT: boolean

  // The bug triggers when a bucket needs CORS (e.g., for browser-based presigned URL uploads)
  // but is deployed via cdk-factory, which has no CORS support
  RETURN X.deployed_via_cdk_factory = true
     AND X.requires_cors = true
     AND X.cors_config IS NOT NULL
END FUNCTION
```

### Property Specification — Fix Checking

```pascal
// Property: Fix Checking — CORS rules are applied when configured
FOR ALL X WHERE isBugCondition(X) DO
  bucket ← S3BucketConstruct'(X)
  ASSERT bucket.cors_rules IS NOT EMPTY
     AND bucket.cors_rules MATCHES X.cors_config
     AND OPTIONS_preflight(bucket, X.origin) = 200
END FOR
```

### Property Specification — Preservation Checking

```pascal
// Property: Preservation Checking — Buckets without CORS config are unchanged
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT S3BucketConstruct(X) = S3BucketConstruct'(X)
  // Buckets with no CORS config continue to be created without CORS rules
  // All other bucket properties (encryption, versioning, etc.) remain identical
END FOR
```

### Key Definitions

- **F** (`S3BucketConstruct`): The original construct — creates S3 buckets but ignores any CORS configuration
- **F'** (`S3BucketConstruct'`): The fixed construct — reads CORS config from `S3BucketConfig` and applies `s3.CorsRule` entries to the bucket
- **Counterexample**: Deploying `s3-analysis-uploads.json` with `cors_rules` configured → browser sends `OPTIONS` to `v3-acme-saas-alpha-analysis-upload-files.s3.amazonaws.com` from `https://v3.alpha.acme.com` → receives 403 Forbidden instead of 200
