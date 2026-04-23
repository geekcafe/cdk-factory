# Implementation Plan: SSM Parameter Resolver CLI

## Overview

Implement a generic, reusable CLI utility at `cdk_factory/utilities/ssm_resolver.py` that resolves AWS SSM Parameter Store values and prints them to stdout. The utility supports optional cross-account role assumption via STS and optional region override, following the same cross-account client pattern as `route53_delegation.py`. All diagnostic output goes to stderr so stdout remains clean for shell command substitution. Tests follow the existing `test_route53_delegation.py` pattern with mocked boto3 clients, plus Hypothesis property-based tests for the 4 design correctness properties.

## Tasks

- [x] 1. Create SsmResolver class and core resolve logic
  - [x] 1.1 Create `cdk-factory/src/cdk_factory/utilities/ssm_resolver.py` with `SsmResolver` class
    - Implement `_get_client(self, service, role_arn=None, region=None)` following the same STS assume-role pattern as `Route53Delegation._get_client` in `route53_delegation.py`
    - When `role_arn` is provided, assume the role via STS with session name prefixed `ssm-resolver`
    - When `region` is provided, pass it to the boto3 client constructor
    - Implement `resolve(self, parameter_name, role_arn=None, region=None) -> str` that creates an SSM client via `_get_client` and calls `get_parameter(Name=parameter_name, WithDecryption=True)`
    - Return the parameter value string on success
    - On `ParameterNotFound` ClientError: print `ERROR: SSM parameter not found: {parameter_name}` to stderr and `sys.exit(1)`
    - On STS failure ClientError in `_get_client`: ensure the error is caught in `resolve()` and print `ERROR: Failed to assume role {role_arn} for parameter {parameter_name}: {error}` to stderr and `sys.exit(1)`
    - On unexpected ClientError: print `ERROR: Failed to resolve parameter {parameter_name}: {error}` to stderr and `sys.exit(1)`
    - On unexpected Exception: print `ERROR: Unexpected error resolving {parameter_name}: {error}` to stderr and `sys.exit(1)`
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3, 4.1, 4.2, 4.3, 4.4, 6.1, 6.2_

  - [x] 1.2 Implement `main()` CLI entry point with argparse
    - Add `main()` function that configures `logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s", stream=sys.stderr)`
    - Use `argparse.ArgumentParser` with description "Resolve an AWS SSM Parameter Store value"
    - Add required `--parameter-name` argument
    - Add optional `--role-arn` argument
    - Add optional `--region` argument
    - Parse args, create `SsmResolver()`, call `resolve()`, and `print()` the result to stdout
    - Add `if __name__ == "__main__": main()` guard
    - _Requirements: 1.3, 1.4, 3.1, 3.2, 3.3, 3.4, 3.5, 5.1, 5.2, 5.3, 7.1, 7.2, 7.3_

- [x] 2. Unit tests for SsmResolver
  - [x] 2.1 Create `cdk-factory/tests/unit/test_ssm_resolver.py` with unit tests
    - Follow the existing pattern in `test_route53_delegation.py` — mock boto3 clients via `@patch.object(SsmResolver, "_get_client")`
    - Test happy path: resolve with ambient credentials (no role_arn) returns correct value
    - Test happy path: resolve with cross-account role returns correct value
    - Test `WithDecryption=True` is always passed to `get_parameter`
    - Test `--region` is forwarded to boto3 client
    - Test default region when `--region` is omitted
    - Test `ParameterNotFound` exits with code 1 and error message on stderr containing the parameter name
    - Test STS failure exits with code 1 and error message on stderr containing the parameter name
    - Test unexpected ClientError exits with code 1
    - Test library import and programmatic call (`SsmResolver().resolve(...)`)
    - Test module invocation via `python -m cdk_factory.utilities.ssm_resolver` (subprocess call)
    - Test missing `--parameter-name` exits non-zero
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3, 6.2, 7.1_

  - [ ]* 2.2 Write property test: stdout purity (Property 1)
    - **Property 1: Resolve value round-trip (stdout purity)**
    - For any generated string value (using `hypothesis.strategies.text`), mock SSM `get_parameter` to return that value, call `main()` with captured stdout/stderr, and assert stdout contains exactly the value and nothing else, and all diagnostic output is on stderr only
    - Use `@settings(max_examples=100)`
    - **Validates: Requirements 1.1, 1.3, 1.4, 7.2, 7.3**

  - [ ]* 2.3 Write property test: cross-account role assumption (Property 2)
    - **Property 2: Cross-account role assumption is triggered by --role-arn**
    - For any generated valid-looking IAM role ARN string and parameter name, when `--role-arn` is provided, assert STS `AssumeRole` is called with that ARN and a session name containing `ssm-resolver`
    - Use `@settings(max_examples=100)`
    - **Validates: Requirements 2.1, 2.3**

  - [ ]* 2.4 Write property test: parameter-not-found error includes parameter name (Property 3)
    - **Property 3: Parameter-not-found error includes parameter name**
    - For any generated parameter name string, mock SSM to raise `ParameterNotFound`, and assert exit code is 1 and stderr contains the parameter name
    - Use `@settings(max_examples=100)`
    - **Validates: Requirements 4.1, 4.4**

  - [ ]* 2.5 Write property test: STS failure error includes parameter name (Property 4)
    - **Property 4: STS failure error includes parameter name**
    - For any generated role ARN and parameter name, mock STS to raise `ClientError`, and assert exit code is 1 and stderr contains the parameter name
    - Use `@settings(max_examples=100)`
    - **Validates: Requirements 4.2, 4.4**

- [x] 3. Checkpoint — Verify core implementation and tests
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Wire up module entry point and verify shell integration
  - [x] 4.1 Ensure `__main__` compatibility for `python -m` invocation
    - Verify the `if __name__ == "__main__": main()` guard works when invoked as `python -m cdk_factory.utilities.ssm_resolver`
    - If the utilities package needs an `__init__.py` update, add the import
    - Verify exit code 0 on success and exit code 1 on failure scenarios
    - _Requirements: 5.1, 5.2, 5.3, 7.1_

- [x] 5. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis with `@settings(max_examples=100)`
- Unit tests follow the existing `test_route53_delegation.py` pattern with `@patch.object` mocking
- The `_get_client` method mirrors `Route53Delegation._get_client` with an added `region` parameter
- All error messages include the parameter name for pipeline log traceability
- All logging is directed to stderr; only the resolved value goes to stdout
