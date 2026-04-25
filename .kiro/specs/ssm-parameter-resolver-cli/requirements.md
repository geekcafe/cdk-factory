# Requirements Document

## Introduction

A generic, reusable CLI utility within the cdk-factory project that resolves AWS SSM Parameter Store values and prints them to stdout. The utility supports optional cross-account role assumption via AWS STS, enabling pipeline scripts to replace multi-line bash credential juggling with a clean one-liner. It is invocable as `python -m cdk_factory.utilities.ssm_resolver` and designed for use in shell variable capture patterns such as `export VAR=$(python -m cdk_factory.utilities.ssm_resolver --parameter-name "/path" --role-arn "arn:...")`.

## Glossary

- **SSM_Resolver**: The CLI utility module (`cdk_factory.utilities.ssm_resolver`) that resolves SSM parameter values and prints them to stdout.
- **SSM_Parameter**: An AWS Systems Manager Parameter Store parameter identified by a hierarchical name (e.g., `/acme-saas/beta/route53/hosted-zone-id`).
- **Role_ARN**: An AWS IAM role Amazon Resource Name used for cross-account STS role assumption.
- **Cross_Account_Role_Assumption**: The process of assuming an IAM role in another AWS account via STS to obtain temporary credentials for API calls.
- **Pipeline_Script**: A shell script executed within a CI/CD pipeline build step (e.g., CodeBuild) that invokes the SSM_Resolver.

## Requirements

### Requirement 1: Resolve SSM Parameter Value

**User Story:** As a pipeline developer, I want to resolve an SSM parameter value by name, so that I can capture it in a shell variable without writing custom boto3 code.

#### Acceptance Criteria

1. WHEN the `--parameter-name` argument is provided with a valid SSM parameter path, THE SSM_Resolver SHALL retrieve the parameter value from AWS SSM Parameter Store and print it to stdout.
2. WHEN the `--parameter-name` argument is provided, THE SSM_Resolver SHALL call SSM GetParameter with `WithDecryption=True` so that SecureString parameters are decrypted transparently.
3. THE SSM_Resolver SHALL print only the resolved parameter value to stdout, with no additional formatting, labels, or trailing whitespace.
4. THE SSM_Resolver SHALL direct all log messages, warnings, and diagnostic output to stderr so that stdout contains only the resolved value.

### Requirement 2: Cross-Account Role Assumption

**User Story:** As a pipeline developer, I want to optionally specify an IAM role ARN for cross-account access, so that I can resolve SSM parameters stored in a different AWS account.

#### Acceptance Criteria

1. WHEN the `--role-arn` argument is provided, THE SSM_Resolver SHALL assume the specified IAM role via AWS STS before calling SSM GetParameter.
2. WHEN the `--role-arn` argument is not provided, THE SSM_Resolver SHALL use the default AWS credential chain (ambient credentials) to call SSM GetParameter.
3. WHEN the `--role-arn` argument is provided, THE SSM_Resolver SHALL use a descriptive STS session name that includes the prefix `ssm-resolver`.

### Requirement 3: CLI Argument Interface

**User Story:** As a pipeline developer, I want a clear argparse-based CLI interface, so that I can invoke the resolver with standard command-line flags.

#### Acceptance Criteria

1. THE SSM_Resolver SHALL accept a required `--parameter-name` argument specifying the SSM parameter path to resolve.
2. THE SSM_Resolver SHALL accept an optional `--role-arn` argument specifying the IAM role ARN for cross-account assumption.
3. THE SSM_Resolver SHALL accept an optional `--region` argument specifying the AWS region for the SSM API call.
4. WHEN the `--region` argument is not provided, THE SSM_Resolver SHALL use the default AWS region from the environment or SDK configuration.
5. WHEN the `--parameter-name` argument is missing, THE SSM_Resolver SHALL print a usage error to stderr and exit with a non-zero exit code.

### Requirement 4: Error Handling and Exit Codes

**User Story:** As a pipeline developer, I want the resolver to exit non-zero with a clear error message when resolution fails, so that my pipeline fails fast on missing or inaccessible parameters.

#### Acceptance Criteria

1. IF the SSM parameter specified by `--parameter-name` does not exist, THEN THE SSM_Resolver SHALL print a descriptive error message to stderr and exit with exit code 1.
2. IF the STS AssumeRole call fails (e.g., access denied, invalid ARN), THEN THE SSM_Resolver SHALL print a descriptive error message to stderr and exit with exit code 1.
3. IF an unexpected AWS API error occurs, THEN THE SSM_Resolver SHALL print the error details to stderr and exit with exit code 1.
4. THE SSM_Resolver SHALL include the parameter name in all error messages so that the failing parameter is identifiable in pipeline logs.

### Requirement 5: Module Invocation

**User Story:** As a pipeline developer, I want to invoke the resolver as a Python module, so that I can call it from any environment where cdk-factory is installed.

#### Acceptance Criteria

1. THE SSM_Resolver SHALL be invocable via `python -m cdk_factory.utilities.ssm_resolver`.
2. THE SSM_Resolver SHALL implement a `__main__.py`-compatible entry point or a guarded `if __name__ == "__main__"` block in the module file.
3. WHEN invoked as a module, THE SSM_Resolver SHALL use the same argument parsing and behavior as direct script execution.

### Requirement 6: Reuse of Existing Cross-Account Client Pattern

**User Story:** As a maintainer of cdk-factory, I want the SSM resolver to reuse or align with the existing cross-account client creation pattern from `route53_delegation.py`, so that the codebase remains consistent and avoids duplicating STS logic.

#### Acceptance Criteria

1. THE SSM_Resolver SHALL use the same STS role assumption pattern (assume role, extract temporary credentials, create service client) as the `_get_client` method in `route53_delegation.py`.
2. THE SSM_Resolver SHALL encapsulate SSM resolution logic in a class or function that is importable and callable from other Python code, not only from the CLI entry point.

### Requirement 7: Shell Integration Compatibility

**User Story:** As a pipeline developer, I want to capture the resolved value in a shell variable using command substitution, so that I can use it in subsequent pipeline commands.

#### Acceptance Criteria

1. WHEN the SSM_Resolver resolves a parameter successfully, THE SSM_Resolver SHALL exit with exit code 0.
2. THE SSM_Resolver SHALL produce output compatible with shell command substitution (e.g., `export VAR=$(python -m cdk_factory.utilities.ssm_resolver --parameter-name "/path")`).
3. THE SSM_Resolver SHALL not print a trailing newline beyond what `print()` produces by default, so that captured values do not contain unexpected whitespace.
