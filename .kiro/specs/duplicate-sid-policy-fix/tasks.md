# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** — Duplicate SIDs for Colliding Resource Name Slugs
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate duplicate SIDs when resource names share a long common prefix
  - **Scoped PBT Approach**: Scope the property to concrete failing cases — pairs of resource names known to collide under 20-char truncation
  - Create `cdk-factory/tests/unit/test_duplicate_sid_bug_condition.py`
  - Instantiate `PolicyDocuments` with a mock `Construct`, `iam.Role`, `LambdaFunctionConfig`, and `DeploymentConfig` (follow pattern from `test_policy_documents_flexible_resolution.py`)
  - Set `AWS_REGION=us-east-1` and `AWS_ACCOUNT=123456789012` env vars for resource resolver
  - **DynamoDB collision**: Call `_get_structured_permission({"dynamodb": "read", "table": "v3-acme-saas-alpha-app-database"})` and `_get_structured_permission({"dynamodb": "read", "table": "v3-acme-saas-alpha-audit-logger-database"})` — assert the two returned SIDs are DIFFERENT (from Bug Condition `isBugCondition` in design)
  - **S3 collision**: Call with `{"s3": "read", "bucket": "v3-acme-saas-alpha-user-files"}` and `{"s3": "read", "bucket": "v3-acme-saas-alpha-analysis-upload-files"}` — assert SIDs are DIFFERENT
  - **SSM collision**: Call with `{"parameter_store": "read", "path": "/v3-acme-saas-alpha/dev/cognito/pool-id"}` and `{"parameter_store": "read", "path": "/v3-acme-saas-alpha/dev/cognito/client-id"}` — assert SIDs are DIFFERENT
  - Use `hypothesis` with `@given` to generate pairs of distinct resource names that share a common prefix longer than 20 chars (after stripping), and assert `_get_structured_permission()` produces distinct SIDs for each pair
  - Run test on UNFIXED code — expect FAILURE (this confirms the bug exists)
  - **EXPECTED OUTCOME**: Test FAILS — proves duplicate SIDs are generated for colliding resource names
  - Document counterexamples found (e.g., both tables produce SID `DynamoDbReadv3acmesaasalphaa`)
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** — SID Validity and Non-Colliding Behavior
  - **IMPORTANT**: Follow observation-first methodology — run UNFIXED code first, observe outputs, then write tests asserting those outputs
  - Create `cdk-factory/tests/unit/test_duplicate_sid_preservation.py`
  - Instantiate `PolicyDocuments` with the same mock setup as task 1
  - **Observe on unfixed code**:
    - `_get_structured_permission({"dynamodb": "read", "table": "users-table"})` → observe SID (e.g., `DynamoDbReaduserstable`)
    - `_get_structured_permission({"s3": "read", "bucket": "my-bucket"})` → observe SID
    - `get_permission_details("cognito_admin")` → observe full dict returned
    - `get_permission_details({"name": "Custom", "sid": "X", "actions": ["s3:GetObject"], "resources": ["*"]})` → observe full dict returned
  - **Property-based test — SID validity**: Use `hypothesis` to generate random resource name strings; for each, call `_get_structured_permission()` and assert the returned SID matches `[A-Za-z0-9]+` (alphanumeric only) and `len(sid) > 0`
  - **Property-based test — slug length bounded**: For any generated resource name, the slug portion of the SID must be ≤ 20 characters
  - **Example test — single-resource DynamoDB**: Verify single-table permission returns a valid policy dict with keys `name`, `description`, `sid`, `actions`, `resources`, `nag`
  - **Example test — single-resource S3**: Verify single-bucket permission returns a valid policy dict
  - **Example test — single-resource SSM**: Verify single-path permission returns a valid policy dict
  - **Example test — string permissions preserved**: Verify `cognito_admin`, `parameter_store_read` return identical dicts as before
  - **Example test — inline IAM dict preserved**: Verify inline dicts with `actions`/`resources` keys return identical dicts
  - **Example test — non-colliding multi-resource**: Verify `users-table` and `orders-table` (already unique within 20 chars) produce distinct SIDs
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

- [x] 3. Fix for duplicate SID policy generation

  - [x] 3.1 Add `_make_sid_slug()` helper method to `PolicyDocuments` class
    - Add `import hashlib` at the top of `cdk-factory/src/cdk_factory/constructs/lambdas/policies/policy_docs.py`
    - Add a new private method `_make_sid_slug(self, resource_name: str, extra_strip: dict | None = None) -> str` to the `PolicyDocuments` class
    - Implementation: strip dashes and underscores (plus any `extra_strip` replacements), compute `hashlib.md5(cleaned.encode()).hexdigest()[:8]`, return `cleaned[:12] + hash_suffix` (prefix 12 + hash 8 = 20 chars total)
    - Ensure output is alphanumeric only (hex digits `[0-9a-f]` satisfy this)
    - _Bug_Condition: isBugCondition(permissions) — multiple structured permissions whose resource name slugs collide after 20-char truncation_
    - _Expected_Behavior: `_make_sid_slug(name_a) != _make_sid_slug(name_b)` for all `name_a != name_b`_
    - _Preservation: All generated slugs must be alphanumeric, ≤ 20 chars, and non-empty_
    - _Requirements: 2.1, 2.2, 2.3, 3.8_

  - [x] 3.2 Update DynamoDB slug generation to use `_make_sid_slug()`
    - In `_get_structured_permission()`, replace `table_slug = table.replace("-", "").replace("_", "")[:20]` with `table_slug = self._make_sid_slug(table)`
    - _Bug_Condition: DynamoDB tables with colliding 20-char prefixes produce duplicate SIDs_
    - _Expected_Behavior: Each table gets a unique SID suffix via prefix+hash_
    - _Preservation: Single-table and already-unique-slug cases continue to work_
    - _Requirements: 1.1, 2.1, 3.1, 3.2_

  - [x] 3.3 Update S3 slug generation to use `_make_sid_slug()`
    - In `_get_structured_permission()`, replace `bucket_slug = bucket.replace("-", "").replace("_", "")[:20]` with `bucket_slug = self._make_sid_slug(bucket)`
    - _Bug_Condition: S3 buckets with colliding 20-char prefixes produce duplicate SIDs_
    - _Expected_Behavior: Each bucket gets a unique SID suffix via prefix+hash_
    - _Preservation: Single-bucket and already-unique-slug cases continue to work_
    - _Requirements: 1.2, 2.2, 3.3, 3.4_

  - [x] 3.4 Update SSM slug generation to use `_make_sid_slug()`
    - In `_get_structured_permission()`, replace `path_slug = path.replace("/", "").replace("-", "").replace("*", "All")[:20]` with `path_slug = self._make_sid_slug(path, extra_strip={"/": "", "*": "All"})`
    - _Bug_Condition: SSM paths with colliding 20-char prefixes produce duplicate SIDs_
    - _Expected_Behavior: Each path gets a unique SID suffix via prefix+hash_
    - _Preservation: Single-path cases continue to work_
    - _Requirements: 1.3, 2.3, 3.5_

  - [x] 3.5 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** — Unique SIDs for Colliding Resource Name Slugs
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - The test from task 1 encodes the expected behavior (distinct SIDs for distinct resource names)
    - When this test passes, it confirms the expected behavior is satisfied
    - Run: `source cdk-factory/.venv/bin/activate && python -m pytest cdk-factory/tests/unit/test_duplicate_sid_bug_condition.py -v`
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed — all colliding resource names now produce unique SIDs)
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.6 Verify preservation tests still pass
    - **Property 2: Preservation** — SID Validity and Non-Colliding Behavior
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run: `source cdk-factory/.venv/bin/activate && python -m pytest cdk-factory/tests/unit/test_duplicate_sid_preservation.py -v`
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions — SID validity, string permissions, inline IAM dicts all unchanged)
    - Confirm all tests still pass after fix (no regressions)

- [x] 4. Checkpoint — Ensure all tests pass
  - Run full test suite: `source cdk-factory/.venv/bin/activate && python -m pytest cdk-factory/tests/unit/ -v`
  - Ensure both `test_duplicate_sid_bug_condition.py` and `test_duplicate_sid_preservation.py` pass
  - Ensure existing tests (especially `test_policy_documents_flexible_resolution.py`) still pass
  - Ask the user if questions arise
