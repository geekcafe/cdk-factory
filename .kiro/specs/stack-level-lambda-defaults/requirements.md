# Requirements Document

## Introduction

This feature adds support for stack-level `additional_permissions` and `additional_environment_variables` in the `lambda_stack` module of cdk-factory. When defined in the root stack config JSON, these fields are automatically merged into every Lambda resource in that stack during setup. This eliminates the need to duplicate shared permissions and environment variables across dozens of individual resource config files.

## Glossary

- **Lambda_Stack**: The CDK stack module (`LambdaStack` in `lambda_stack.py`) responsible for creating AWS Lambda functions and their associated resources from a stack config JSON.
- **Stack_Config**: The JSON configuration object that defines a Lambda stack, containing fields like `name`, `module`, `resources`, and the new `additional_permissions` and `additional_environment_variables`.
- **Resource_Config**: An individual Lambda function configuration dict within the `resources` array of a Stack_Config. Each Resource_Config is loaded into a `LambdaFunctionConfig` instance.
- **Additional_Permissions**: An optional array at the stack level containing permission entries (structured dicts or strings) that are merged into every Resource_Config's `permissions` array before CDK constructs are created.
- **Additional_Environment_Variables**: An optional array at the stack level containing environment variable entries (`{"name": "...", "value": "..."}`) that are merged into every Resource_Config's `environment_variables` array before CDK constructs are created.
- **Merge**: The process of combining stack-level entries with resource-level entries, where resource-level entries take precedence over stack-level entries when duplicates exist.
- **JsonLoadingUtility**: The utility class that resolves `__inherits__` / `__imports__` references in JSON config files before the config is passed to stack modules.

## Requirements

### Requirement 1: Stack-Level Additional Permissions

**User Story:** As a platform engineer, I want to define shared permissions once at the stack level, so that every Lambda in the stack automatically receives those permissions without duplicating them in each resource config file.

#### Acceptance Criteria

1. WHEN a Stack_Config contains an `additional_permissions` array, THE Lambda_Stack SHALL merge each entry in `additional_permissions` into every Resource_Config's `permissions` array before creating CDK constructs.
2. WHEN a Resource_Config already contains a permission entry that matches a stack-level entry in `additional_permissions`, THE Lambda_Stack SHALL keep the resource-level entry and discard the duplicate stack-level entry.
3. WHEN a Stack_Config does not contain an `additional_permissions` field, THE Lambda_Stack SHALL process resources with no change to existing behavior.
4. THE Lambda_Stack SHALL support all permission formats in `additional_permissions` that are supported in resource-level `permissions` (structured dicts like `{"dynamodb": "read", "table": "..."}`, string keys like `"parameter_store_read"`, and inline IAM dicts).
5. WHEN `additional_permissions` contains an `__inherits__` reference, THE JsonLoadingUtility SHALL resolve the reference to an array of permission entries before the Lambda_Stack processes the config.

### Requirement 2: Stack-Level Additional Environment Variables

**User Story:** As a platform engineer, I want to define shared environment variables once at the stack level, so that every Lambda in the stack automatically receives those variables without duplicating them in each resource config file.

#### Acceptance Criteria

1. WHEN a Stack_Config contains an `additional_environment_variables` array, THE Lambda_Stack SHALL merge each entry into every Resource_Config's `environment_variables` array before environment variables are loaded into CDK constructs.
2. WHEN a Resource_Config already defines an environment variable with the same `name` as a stack-level entry in `additional_environment_variables`, THE Lambda_Stack SHALL keep the resource-level entry and discard the duplicate stack-level entry.
3. WHEN a Stack_Config does not contain an `additional_environment_variables` field, THE Lambda_Stack SHALL process resources with no change to existing behavior.
4. THE Lambda_Stack SHALL support all environment variable formats in `additional_environment_variables` that are supported in resource-level `environment_variables` (including `{"name": "...", "value": "..."}` and `{"name": "...", "ssm_parameter": "..."}` formats).
5. WHEN `additional_environment_variables` contains an `__inherits__` reference, THE JsonLoadingUtility SHALL resolve the reference to an array of environment variable entries before the Lambda_Stack processes the config.

### Requirement 3: Resource-Level Precedence

**User Story:** As a platform engineer, I want resource-level configurations to always override stack-level defaults, so that individual Lambdas can customize or override shared settings when needed.

#### Acceptance Criteria

1. FOR ALL Resource_Configs in a stack, THE Lambda_Stack SHALL apply stack-level `additional_permissions` entries only when no matching resource-level permission exists.
2. FOR ALL Resource_Configs in a stack, THE Lambda_Stack SHALL apply stack-level `additional_environment_variables` entries only when no resource-level environment variable with the same `name` exists.
3. WHEN a resource-level permission matches a stack-level permission by the same structured key (e.g., same `dynamodb` action and `table`, or same string key), THE Lambda_Stack SHALL use the resource-level permission.
4. WHEN a resource-level environment variable has the same `name` as a stack-level environment variable, THE Lambda_Stack SHALL use the resource-level environment variable.

### Requirement 4: Resource-Level Opt-Out

**User Story:** As a platform engineer, I want to exclude specific Lambdas from receiving stack-level defaults, so that internal workhorse Lambdas don't get unnecessary permissions or environment variables that would create noise (e.g., audit logging on high-throughput internal processors).

#### Acceptance Criteria

1. WHEN a Resource_Config contains `"skip_stack_defaults": true`, THE Lambda_Stack SHALL NOT merge any stack-level `additional_permissions` or `additional_environment_variables` into that resource.
2. WHEN a Resource_Config does not contain `skip_stack_defaults` or contains `"skip_stack_defaults": false`, THE Lambda_Stack SHALL merge stack-level defaults normally.
3. THE `skip_stack_defaults` field SHALL be optional and default to `false` when absent.

### Requirement 5: Backward Compatibility

**User Story:** As a platform engineer, I want existing stack configs without the new fields to continue working without any changes, so that this feature is purely additive.

#### Acceptance Criteria

1. WHEN a Stack_Config does not contain `additional_permissions` or `additional_environment_variables`, THE Lambda_Stack SHALL produce identical CDK output as before this feature was introduced.
2. THE Lambda_Stack SHALL treat both `additional_permissions` and `additional_environment_variables` as optional fields that default to empty arrays when absent.
3. WHEN `additional_permissions` is an empty array, THE Lambda_Stack SHALL not modify any Resource_Config's permissions.
4. WHEN `additional_environment_variables` is an empty array, THE Lambda_Stack SHALL not modify any Resource_Config's environment variables.

### Requirement 6: Merge Timing

**User Story:** As a platform engineer, I want the merge to happen before CDK constructs are created, so that the merged config is the single source of truth for Lambda setup.

#### Acceptance Criteria

1. THE Lambda_Stack SHALL merge stack-level `additional_permissions` into each Resource_Config's `permissions` before the `LambdaFunctionConfig` is used to create IAM policies via `PolicyDocuments`.
2. THE Lambda_Stack SHALL merge stack-level `additional_environment_variables` into each Resource_Config's `environment_variables` before `EnvironmentServices.load_environment_variables` is called.
3. THE Lambda_Stack SHALL perform the merge in the `build` method, after loading the `resources` array and before passing Resource_Configs to `__setup_lambdas`.

### Requirement 7: Inherits Support for Stack-Level Fields

**User Story:** As a platform engineer, I want to use `__inherits__` in the stack-level `additional_permissions` and `additional_environment_variables` fields, so that I can reference shared config files instead of inlining values.

#### Acceptance Criteria

1. WHEN `additional_permissions` is a dict containing an `__inherits__` key, THE JsonLoadingUtility SHALL resolve the reference and produce an array of permission entries.
2. WHEN `additional_environment_variables` is a dict containing an `__inherits__` key, THE JsonLoadingUtility SHALL resolve the reference and produce an array of environment variable entries.
3. THE Lambda_Stack SHALL accept both inline arrays and `__inherits__`-resolved arrays for `additional_permissions` and `additional_environment_variables`.
