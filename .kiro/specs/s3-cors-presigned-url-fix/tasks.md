# Implementation Plan

- [ ] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** — CORS Config Silently Ignored
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate `S3BucketConfig` ignores `cors_rules` and `S3BucketConstruct` creates buckets without CORS
  - **Scoped PBT Approach**: Scope the property to concrete failing cases — configs with `cors_rules` specified
  - Test file: `cdk-factory/tests/unit/test_s3_cors_bug_condition.py`
  - Test 1 — Config property missing: Create `S3BucketConfig({"name": "test-bucket", "cors_rules": [{"allowed_methods": ["GET", "PUT", "POST"], "allowed_origins": ["*"], "allowed_headers": ["*"], "max_age": 3600}]})` and assert `config.cors_rules` returns a non-empty list of `s3.CorsRule` objects (will fail with `AttributeError` on unfixed code — confirms config ignores CORS)
  - Test 2 — Construct synthesis missing CORS: Synthesize an `S3BucketStack` with a config containing `cors_rules` and assert the CloudFormation template contains a `CorsConfiguration` property on the `AWS::S3::Bucket` resource (will be absent on unfixed code — confirms construct ignores CORS)
  - Test 3 — Property-based (Hypothesis): For any valid CORS config (random subsets of HTTP methods from `["GET","PUT","POST","DELETE","HEAD"]`, random allowed_origins, random allowed_headers), `S3BucketConfig.cors_rules` must return matching `s3.CorsRule` entries. Use `@given` with strategies for method subsets, origin lists, header lists, and optional max_age. (Will fail on unfixed code)
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests FAIL (this is correct — it proves the bug exists)
  - Document counterexamples found (e.g., `AttributeError: 'S3BucketConfig' object has no attribute 'cors_rules'`)
  - Mark task complete when tests are written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3_

- [ ] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** — Buckets Without CORS Config Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Test file: `cdk-factory/tests/unit/test_s3_cors_preservation.py`
  - Observe: Synthesize `S3BucketStack` with config `{"name": "test-bucket"}` (no `cors_rules`) on unfixed code → template has no `CorsConfiguration` property
  - Observe: Synthesize `S3BucketStack` with config `{"name": "test-bucket", "cors_rules": []}` (empty list) on unfixed code → template has no `CorsConfiguration` property
  - Observe: Synthesize `S3BucketStack` with config `{"name": "test-bucket", "versioned": "true", "encryption": "s3_managed", "enforce_ssl": "true"}` on unfixed code → template has encryption, versioning, SSL enforcement properties unchanged
  - Observe: `S3BucketConfig({"name": "test-bucket", "use_existing": "true"})` with `use_existing=true` → bucket is imported, no CORS modification attempted
  - Write property-based test (Hypothesis): For any bucket config WITHOUT `cors_rules` (random combinations of `versioned`, `encryption`, `enforce_ssl`, `block_public_access`, `removal_policy`, `access_control`), the synthesized CloudFormation template must NOT contain a `CorsConfiguration` property, and all other bucket properties (encryption, versioning, block_public_access) must match the config
  - Write property-based test: For any bucket config with `use_existing=true`, the construct imports the bucket without error and does not attempt CORS configuration
  - Verify all tests PASS on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 3. Fix S3 CORS presigned URL bug

  - [ ] 3.1 Add `cors_rules` property to `S3BucketConfig`
    - File: `cdk-factory/src/cdk_factory/configurations/resources/s3.py`
    - Add HTTP method string-to-enum mapping: `{"GET": s3.HttpMethods.GET, "PUT": s3.HttpMethods.PUT, "POST": s3.HttpMethods.POST, "DELETE": s3.HttpMethods.DELETE, "HEAD": s3.HttpMethods.HEAD}`
    - Add `cors_rules` property that reads `self.__config.get("cors_rules", [])` and converts each dict to `s3.CorsRule(allowed_methods=[mapped enums], allowed_origins=[...], allowed_headers=[...], exposed_headers=[...], max_age=int or None)`
    - Return `list[s3.CorsRule]` — empty list when key is absent or empty
    - Handle invalid/unknown HTTP method strings gracefully (skip or raise ValueError)
    - _Bug_Condition: isBugCondition(input) where input.json_config.cors_rules IS NOT NULL AND IS NOT EMPTY_
    - _Expected_Behavior: config.cors_rules returns list[s3.CorsRule] matching the JSON config entries_
    - _Preservation: Configs without cors_rules key return empty list — no change to existing behavior_
    - _Requirements: 1.3, 2.3_

  - [ ] 3.2 Pass `cors` parameter in `S3BucketConstruct`
    - File: `cdk-factory/src/cdk_factory/constructs/s3_buckets/s3_bucket_construct.py`
    - In the `s3.Bucket()` constructor call (new bucket path only, inside the `else` block), add `cors=self.bucket_config.cors_rules or None`
    - Pass `None` (not empty list) when no CORS rules are configured so CDK omits the property entirely
    - Do NOT modify the `use_existing` import path — CORS cannot be applied to imported buckets
    - _Bug_Condition: isBugCondition(input) where bucket is new (not use_existing) and cors_rules configured_
    - _Expected_Behavior: s3.Bucket() receives cors=list[s3.CorsRule] and CloudFormation template includes CorsConfiguration_
    - _Preservation: When cors_rules is empty/absent, cors=None is passed and template has no CorsConfiguration_
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3_

  - [ ] 3.3 Add CORS config to upload bucket JSON
    - File: `Acme-SaaS-IaC/cdk/configs/stacks/storage/s3-analysis-uploads.json`
    - Add `cors_rules` array to the `bucket` object matching the old deployment's CORS config from `Acme-SaaS-Application/devops/cdk/resources/constructs/s3_construct.py`:
      ```json
      "cors_rules": [
        {
          "allowed_methods": ["GET", "POST", "PUT"],
          "allowed_origins": ["*"],
          "allowed_headers": ["*"],
          "exposed_headers": ["Date"],
          "max_age": 3600
        }
      ]
      ```
    - _Requirements: 1.1, 1.2, 2.1, 2.2_

  - [ ] 3.4 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** — CORS Config Applied When Configured
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - The test from task 1 encodes the expected behavior (config.cors_rules returns CorsRule list, template has CorsConfiguration)
    - When this test passes, it confirms the expected behavior is satisfied
    - Run: `source cdk-factory/.venv/bin/activate && python -m pytest cdk-factory/tests/unit/test_s3_cors_bug_condition.py -v`
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ] 3.5 Verify preservation tests still pass
    - **Property 2: Preservation** — Buckets Without CORS Config Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run: `source cdk-factory/.venv/bin/activate && python -m pytest cdk-factory/tests/unit/test_s3_cors_preservation.py -v`
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all preservation tests still pass after fix (no regressions)

- [ ] 4. Checkpoint — Ensure all tests pass
  - Run full test suite: `source cdk-factory/.venv/bin/activate && python -m pytest cdk-factory/tests/unit/ -v`
  - Ensure all existing tests still pass (no regressions to other stacks/constructs)
  - Ensure both bug condition and preservation tests pass
  - Ask the user if questions arise
