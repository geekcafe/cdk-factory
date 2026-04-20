# Requirements Document

## Introduction

JSON Schema Validation for cdk-factory stack configs. This feature adds JSON schema definitions for each stack module's configuration shape and validates configs at load time — before CDK synth runs. The goal is to catch typos, missing fields, and wrong types early with clear, actionable error messages. This also reconciles the two existing `ConfigValidator` implementations into a single canonical location.

## Glossary

- **Schema_Registry**: The module responsible for loading, caching, and providing JSON schema definitions for all stack module config shapes.
- **Schema_Validator**: The component that validates a stack config dictionary against its corresponding JSON schema using the `jsonschema` library.
- **Stack_Config**: A JSON dictionary describing a single CloudFormation stack, containing common fields (`name`, `module`, `enabled`, `ssm`, `depends_on`, `description`) and a module-specific resource block.
- **Common_Schema**: The JSON schema defining the shared top-level fields present in every Stack_Config (name, module, enabled, ssm, depends_on, description).
- **Module_Schema**: A JSON schema defining the resource-specific configuration block for a particular stack module (e.g., `dynamodb`, `bucket`, `api_gateway`).
- **ConfigValidator**: The existing class at `configurations/config_validator.py` that performs pattern-level validation (deprecated keys, structural checks).
- **Old_Validator**: The broken validator at `validation/config_validator.py` that uses `jsonschema` but has import errors.
- **Placeholder**: A `{{PLACEHOLDER}}` token in string fields that is resolved later during deployment parameter resolution.
- **Merged_Config**: The final Stack_Config dictionary after all `__imports__`/`__inherits__` references have been resolved.

## Requirements

### Requirement 1: Add jsonschema Dependency

**User Story:** As a cdk-factory maintainer, I want `jsonschema` added as a project dependency, so that schema validation can be used without import errors.

#### Acceptance Criteria

1. THE Build_System SHALL declare `jsonschema` as a runtime dependency in `pyproject.toml`.
2. WHEN cdk-factory is installed, THE Build_System SHALL make the `jsonschema` package importable without errors.

### Requirement 2: Reconcile ConfigValidator Implementations

**User Story:** As a cdk-factory maintainer, I want a single canonical ConfigValidator, so that there is no confusion about which validator to use and no broken imports.

#### Acceptance Criteria

1. THE cdk-factory project SHALL have exactly one ConfigValidator class at `configurations/config_validator.py`.
2. WHEN the reconciliation is complete, THE Old_Validator file at `validation/config_validator.py` SHALL be removed.
3. THE ConfigValidator SHALL retain all existing pattern-level validations (name present, no nested SSM, no ssm.enabled, no deprecated exists, single dependency key, use_existing has name, no stack_name key).
4. THE ConfigValidator SHALL integrate schema-based validation into its `validate()` method alongside the existing pattern checks.

### Requirement 3: Common Stack Config Schema

**User Story:** As a stack config author, I want the shared top-level fields validated against a schema, so that typos in common fields like `name`, `module`, `enabled`, `ssm`, `depends_on`, and `description` are caught immediately.

#### Acceptance Criteria

1. THE Common_Schema SHALL define `name` as a required string field.
2. THE Common_Schema SHALL define `module` as a required string field.
3. THE Common_Schema SHALL define `enabled` as an optional boolean field.
4. THE Common_Schema SHALL define `description` as an optional string field.
5. THE Common_Schema SHALL define `depends_on` as an optional array of strings.
6. THE Common_Schema SHALL define `ssm` as an optional object with properties `auto_export` (boolean), `namespace` (string), and `imports` (object).
7. THE Common_Schema SHALL allow additional properties beyond the defined common fields to support module-specific resource blocks.
8. WHEN a Stack_Config is missing the `name` field, THE Schema_Validator SHALL report a validation error identifying the missing field.
9. WHEN a Stack_Config is missing the `module` field, THE Schema_Validator SHALL report a validation error identifying the missing field.

### Requirement 4: Module-Specific Resource Schemas

**User Story:** As a stack config author, I want each module's resource block validated against a module-specific schema, so that field names, types, and required properties within `dynamodb`, `bucket`, `api_gateway`, `sqs`, `cognito`, `route53`, `monitoring`, `state_machine`, and `resources` (lambda) blocks are checked.

#### Acceptance Criteria

1. THE Schema_Registry SHALL provide a Module_Schema for the `dynamodb` resource block covering fields: `name` (string, required), `use_existing` (boolean or string), `gsi_count` (integer), `replica_regions` (array of strings), `enable_delete_protection` (boolean or string), `point_in_time_recovery` (boolean or string), `ttl_attribute` (string), and `global_secondary_indexes` (array of objects).
2. THE Schema_Registry SHALL provide a Module_Schema for the `bucket` resource block covering fields: `name` (string, required), `use_existing` (boolean or string), `versioned` (boolean or string), `encryption` (string), `lifecycle_rules` (array), `removal_policy` (string), `enforce_ssl` (boolean or string), `enable_event_bridge` (boolean or string), and `auto_delete_objects` (boolean or string).
3. THE Schema_Registry SHALL provide a Module_Schema for the `api_gateway` resource block covering fields: `name` (string), `api_type` (string), `description` (string), `deploy_options` (object), `routes` (array of objects), `cors` (object), `custom_domain` (object), and `cognito` (object).
4. THE Schema_Registry SHALL provide a Module_Schema for the `sqs` resource block covering fields: `queues` (array of objects), where each queue object includes `queue_name` (string), `type` (string), `visibility_timeout_seconds` (integer), `max_receive_count` (integer), `batch_size` (integer), and `add_dead_letter_queue` (boolean or string).
5. THE Schema_Registry SHALL provide a Module_Schema for the `cognito` resource block covering fields: `user_pool_name` (string), `self_sign_up_enabled` (boolean), `sign_in_aliases` (object), `password_policy` (object), `mfa` (string), `app_clients` (array of objects), and `deletion_protection` (boolean).
6. THE Schema_Registry SHALL provide a Module_Schema for the `route53` resource block covering fields: `hosted_zone_id` (string), `domain_name` (string), `create_hosted_zone` (boolean), `record_names` (array of strings), `use_existing` (boolean or string), and `records` (array of objects).
7. THE Schema_Registry SHALL provide a Module_Schema for the `monitoring` resource block covering fields: `name` (string), `sns_topics` (array), `alarms` (array), `dashboards` (array), and `enable_anomaly_detection` (boolean).
8. THE Schema_Registry SHALL provide a Module_Schema for the `state_machine` resource block covering fields: `name` (string, required), `type` (string), `definition_file` (string), `definition` (object), `lambda_arns` (object), and `logging` (boolean or string).
9. THE Schema_Registry SHALL provide a Module_Schema for the `resources` block (lambda stack) covering fields per resource: `name` (string, required), `description` (string), `docker` (object), `ecr` (object), `image_config` (object), `handler` (string), `runtime` (string), `memory_size` (integer), `timeout` (integer), `environment_variables` (array), `permissions` (array), and `layers` (array).

### Requirement 5: Placeholder-Aware Validation

**User Story:** As a stack config author, I want `{{PLACEHOLDER}}` tokens in string fields to pass schema validation, so that configs with unresolved placeholders are not rejected before parameter resolution.

#### Acceptance Criteria

1. WHEN a string field contains a `{{PLACEHOLDER}}` token, THE Schema_Validator SHALL accept the value as a valid string.
2. WHEN a field expects a boolean or integer type but the value is a string containing a `{{PLACEHOLDER}}` token, THE Schema_Validator SHALL accept the value without reporting a type error.
3. THE Schema_Validator SHALL recognize placeholder patterns matching the regex `\{\{[A-Z_][A-Z0-9_]*\}\}` as valid placeholder tokens.

### Requirement 6: Validation at Config Load Time

**User Story:** As a cdk-factory user, I want schema validation to run automatically when configs are loaded, so that errors are caught before CDK synth begins.

#### Acceptance Criteria

1. WHEN a Merged_Config is loaded, THE ConfigValidator SHALL run schema validation before any CDK constructs are created.
2. THE ConfigValidator SHALL run schema validation after the `__imports__`/`__inherits__` references have been resolved, validating the Merged_Config.
3. THE ConfigValidator SHALL run existing pattern-level validations and schema validation in a single `validate()` call.
4. IF schema validation fails, THEN THE ConfigValidator SHALL raise a `ValueError` with all validation errors collected.

### Requirement 7: Clear Error Messages

**User Story:** As a stack config author, I want validation errors to identify the exact field path, what is wrong, and what is expected, so that I can fix config issues without guessing.

#### Acceptance Criteria

1. WHEN a validation error occurs, THE Schema_Validator SHALL include the JSON path to the invalid field (e.g., `dynamodb.name`, `ssm.auto_export`).
2. WHEN a validation error occurs, THE Schema_Validator SHALL include a description of what is wrong (e.g., "is a required property", "is not of type 'string'").
3. WHEN a validation error occurs, THE Schema_Validator SHALL include the expected type or allowed values for the field.
4. WHEN multiple validation errors exist in a single config, THE Schema_Validator SHALL report all errors rather than stopping at the first error.

### Requirement 8: Schema Storage and Maintainability

**User Story:** As a cdk-factory maintainer, I want schemas stored as separate JSON files alongside the codebase, so that they are easy to find, review, and update independently of the Python code.

#### Acceptance Criteria

1. THE Schema_Registry SHALL load schema files from a `schemas/` directory within the cdk-factory package.
2. THE Schema_Registry SHALL support schema files in JSON format.
3. THE Schema_Registry SHALL use a naming convention that maps module names to schema file names (e.g., `dynamodb.schema.json`, `s3.schema.json`).
4. THE Schema_Registry SHALL cache loaded schemas in memory to avoid repeated file reads.

### Requirement 9: Validation Performance

**User Story:** As a cdk-factory user, I want schema validation to complete quickly, so that it does not noticeably slow down CDK synth.

#### Acceptance Criteria

1. WHEN validating a single Stack_Config, THE Schema_Validator SHALL complete validation within 50 milliseconds for a typical config.
2. THE Schema_Registry SHALL load and cache all schemas once at startup rather than re-reading files for each validation call.

### Requirement 10: Schema Validator Round-Trip Consistency

**User Story:** As a cdk-factory maintainer, I want to verify that schemas accurately represent the config classes, so that valid configs are accepted and invalid configs are rejected.

#### Acceptance Criteria

1. FOR ALL valid Stack_Config dictionaries that the resource config classes accept, THE Schema_Validator SHALL accept the dictionary without errors (no false rejections).
2. FOR ALL Stack_Config dictionaries with invalid field types or missing required fields, THE Schema_Validator SHALL report at least one validation error (no false acceptances).
3. THE Schema_Validator SHALL produce consistent results when validating the same config dictionary multiple times (idempotent validation).
