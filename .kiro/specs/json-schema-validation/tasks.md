# Implementation Plan: JSON Schema Validation

## Overview

Replace the dual-validator setup with a single `ConfigValidator` that runs both pattern-level checks and JSON Schema validation. Add a `SchemaRegistry` for loading/caching schema files, a `SchemaValidator` for placeholder-aware validation using `jsonschema`, and `.schema.json` files for each module. Delete the old broken validator at `validation/config_validator.py`.

## Tasks

- [ ] 1. Add jsonschema dependency and create schemas directory
  - [ ] 1.1 Add `jsonschema` to `pyproject.toml` dependencies
    - Add `"jsonschema"` to the `dependencies` list in `pyproject.toml`
    - _Requirements: 1.1, 1.2_
  - [ ] 1.2 Create the `src/cdk_factory/schemas/` directory with `common.schema.json`
    - Define `common.schema.json` with required fields `name` (string) and `module` (string), optional `enabled` (boolean), `description` (string), `depends_on` (array of strings), `ssm` (object with `auto_export`, `namespace`, `imports`), and `additionalProperties: true`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [ ] 2. Create module-specific JSON schema files
  - [ ] 2.1 Create `dynamodb.schema.json`
    - Define schema for the `dynamodb` resource block: `name` (string, required), `use_existing` (boolean or string), `gsi_count` (integer), `replica_regions` (array of strings), `enable_delete_protection` (boolean or string), `point_in_time_recovery` (boolean or string), `ttl_attribute` (string), `global_secondary_indexes` (array of objects), `additionalProperties: true`
    - _Requirements: 4.1_
  - [ ] 2.2 Create `s3.schema.json`
    - Define schema for the `bucket` resource block: `name` (string, required), `use_existing` (boolean or string), `versioned` (boolean or string), `encryption` (string), `lifecycle_rules` (array), `removal_policy` (string), `enforce_ssl` (boolean or string), `enable_event_bridge` (boolean or string), `auto_delete_objects` (boolean or string), `additionalProperties: true`
    - _Requirements: 4.2_
  - [ ] 2.3 Create `lambda.schema.json`
    - Define schema for items in the `resources` array: `name` (string, required), `description` (string), `docker` (object), `ecr` (object), `image_config` (object), `handler` (string), `runtime` (string), `memory_size` (integer), `timeout` (integer), `environment_variables` (array), `permissions` (array), `layers` (array), `api` (object), `additionalProperties: true`
    - _Requirements: 4.9_
  - [ ] 2.4 Create `api_gateway.schema.json`
    - Define schema for the `api_gateway` resource block: `name` (string), `api_type` (string), `description` (string), `deploy_options` (object), `routes` (array of objects), `cors` (object), `custom_domain` (object), `cognito` (object), `additionalProperties: true`
    - _Requirements: 4.3_
  - [ ] 2.5 Create `sqs.schema.json`
    - Define schema for the `sqs` resource block: `queues` (array of objects with `queue_name`, `type`, `visibility_timeout_seconds`, `max_receive_count`, `batch_size`, `add_dead_letter_queue`), `additionalProperties: true`
    - _Requirements: 4.4_
  - [ ] 2.6 Create `cognito.schema.json`
    - Define schema for the `cognito` resource block: `user_pool_name` (string), `self_sign_up_enabled` (boolean), `sign_in_aliases` (object), `password_policy` (object), `mfa` (string), `app_clients` (array of objects), `deletion_protection` (boolean), `additionalProperties: true`
    - _Requirements: 4.5_
  - [ ] 2.7 Create `route53.schema.json`
    - Define schema for the `route53` resource block: `hosted_zone_id` (string), `domain_name` (string), `create_hosted_zone` (boolean), `record_names` (array of strings), `use_existing` (boolean or string), `records` (array of objects), `additionalProperties: true`
    - _Requirements: 4.6_
  - [ ] 2.8 Create `monitoring.schema.json`
    - Define schema for the `monitoring` resource block: `name` (string), `sns_topics` (array), `alarms` (array), `dashboards` (array), `enable_anomaly_detection` (boolean), `additionalProperties: true`
    - _Requirements: 4.7_
  - [ ] 2.9 Create `state_machine.schema.json`
    - Define schema for the `state_machine` resource block: `name` (string, required), `type` (string), `definition_file` (string), `definition` (object), `lambda_arns` (object), `logging` (boolean or string), `additionalProperties: true`
    - _Requirements: 4.8_

- [ ] 3. Implement SchemaRegistry
  - [ ] 3.1 Create `src/cdk_factory/configurations/schema_registry.py`
    - Implement `SchemaRegistry` class with `get_schema(schema_name)`, `get_module_schema(config)`, and `clear_cache()` class methods
    - Schema file resolution: `Path(__file__).parent.parent / "schemas" / f"{schema_name}.schema.json"`
    - Map config keys to schema file names: `dynamodb` → `dynamodb`, `bucket` → `s3`, `api_gateway` → `api_gateway`, `sqs` → `sqs`, `cognito` → `cognito`, `route53` → `route53`, `monitoring` → `monitoring`, `state_machine` → `state_machine`, `resources` → `lambda`
    - Cache loaded schemas in `_cache` dict; return `None` if schema file missing or malformed JSON
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 9.2_
  - [ ]* 3.2 Write unit tests for SchemaRegistry
    - Test `get_schema()` returns valid schema dicts for each module
    - Test `get_module_schema()` correctly detects resource keys in configs
    - Test `clear_cache()` resets the cache
    - Test missing schema file returns `None`
    - Test malformed JSON schema file returns `None`
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [ ] 4. Implement SchemaValidator with placeholder pre-processing
  - [ ] 4.1 Create `src/cdk_factory/configurations/schema_validator.py`
    - Implement `SchemaValidator` class with `validate(config)`, `_preprocess_for_placeholders(value, schema_property)`, and `_format_error(error)` static methods
    - `validate()`: get common schema and module schema from `SchemaRegistry`, pre-process config for placeholders, use `Draft7Validator.iter_errors()` to collect all errors, return list of formatted error strings
    - `_preprocess_for_placeholders()`: recursively walk config dict, replace `{{PLACEHOLDER}}` tokens matching `\{\{[A-Z_][A-Z0-9_]*\}\}` with type-appropriate sentinels (leave strings as-is, replace integer placeholders with `0`)
    - `_format_error()`: format each `ValidationError` with JSON path and description
    - _Requirements: 5.1, 5.2, 5.3, 6.4, 7.1, 7.2, 7.3, 7.4, 9.1, 10.1, 10.2, 10.3_
  - [ ]* 4.2 Write unit tests for SchemaValidator
    - Test valid configs return empty error list
    - Test missing required fields produce errors with field path
    - Test wrong types produce errors with expected type
    - Test placeholder tokens in string, boolean, and integer fields pass validation
    - Test multiple errors are all collected in a single pass
    - Test error message format includes JSON path and description
    - _Requirements: 5.1, 5.2, 5.3, 7.1, 7.2, 7.3, 7.4, 10.1, 10.2_

- [ ] 5. Checkpoint - Ensure schema infrastructure works
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Integrate schema validation into ConfigValidator and clean up old validator
  - [ ] 6.1 Update `src/cdk_factory/configurations/config_validator.py` to call SchemaValidator
    - Add schema validation step at the end of `ConfigValidator.validate()`: import `SchemaValidator`, call `SchemaValidator.validate(stack_config)`, if errors exist raise `ValueError` with all errors formatted
    - Keep all existing pattern-level checks unchanged
    - _Requirements: 2.1, 2.3, 2.4, 6.1, 6.2, 6.3, 6.4_
  - [ ] 6.2 Delete `src/cdk_factory/validation/config_validator.py`
    - Remove the old broken validator file
    - _Requirements: 2.2_
  - [ ] 6.3 Update test framework imports
    - Update `tests/framework/factory_test_base.py`: change `from cdk_factory.validation.config_validator import ConfigValidator` to `from cdk_factory.configurations.config_validator import ConfigValidator`
    - Update `tests/framework/ssm_integration_tester.py`: same import change
    - _Requirements: 2.2_
  - [ ]* 6.4 Write integration tests for ConfigValidator with schema validation
    - Test that `ConfigValidator.validate()` catches both pattern violations and schema errors
    - Test that real-world config files from `acme-SaaS-IaC/cdk/configs/` pass validation (dynamodb, lambda, api-gateway configs)
    - Test that pattern-level errors still raise `ValueError` with correct messages
    - _Requirements: 2.3, 6.1, 6.2, 6.3, 6.4_

- [ ] 7. Checkpoint - Ensure full integration works
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Property-based tests for correctness properties
  - [ ]* 8.1 Write property test: valid config acceptance (Property 1)
    - **Property 1: Valid config acceptance (no false rejections)**
    - Use Hypothesis to generate valid configs for each module (common fields + module-specific blocks with correct types and required fields)
    - Assert `SchemaValidator.validate()` returns empty error list for all generated valid configs
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 10.1**
  - [ ]* 8.2 Write property test: invalid config rejection (Property 2)
    - **Property 2: Invalid config rejection (no false acceptances)**
    - Use Hypothesis to generate valid configs then mutate them (remove required fields, change types to invalid ones)
    - Assert `SchemaValidator.validate()` returns at least one error for all mutated configs
    - **Validates: Requirements 3.8, 3.9, 10.2**
  - [ ]* 8.3 Write property test: placeholder passthrough (Property 3)
    - **Property 3: Placeholder passthrough**
    - Use Hypothesis to generate valid configs then inject `{{PLACEHOLDER}}` tokens into random string, boolean, and integer fields
    - Assert `SchemaValidator.validate()` returns empty error list
    - **Validates: Requirements 5.1, 5.2, 5.3**
  - [ ]* 8.4 Write property test: all errors collected (Property 4)
    - **Property 4: All errors collected**
    - Use Hypothesis to generate configs with N known distinct schema violations (N ≥ 2)
    - Assert `SchemaValidator.validate()` returns at least N errors
    - **Validates: Requirements 6.4, 7.4**
  - [ ]* 8.5 Write property test: error message completeness (Property 5)
    - **Property 5: Error message completeness**
    - Use Hypothesis to generate invalid configs, validate, assert each error string contains a JSON path and a description of the violation
    - **Validates: Requirements 7.1, 7.2, 7.3**
  - [ ]* 8.6 Write property test: pattern validation backward compatibility (Property 6)
    - **Property 6: Pattern validation backward compatibility**
    - Use Hypothesis to generate configs with each pattern-level violation (nested SSM, ssm.enabled, deprecated bucket.exists, both depends_on and dependencies, missing name, stack_name key, use_existing without name)
    - Assert `ConfigValidator.validate()` raises `ValueError` with the correct message for each violation
    - **Validates: Requirements 2.3**
  - [ ]* 8.7 Write property test: validation idempotence (Property 7)
    - **Property 7: Validation idempotence**
    - Use Hypothesis to generate random configs (valid and invalid), call `SchemaValidator.validate()` twice, assert identical results
    - **Validates: Requirements 10.3**

- [ ] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- The design uses Python — all code is Python, schemas are JSON files
- The old validator at `validation/config_validator.py` is broken (import errors) and unused in production — safe to delete
- All schemas use `additionalProperties: true` for incremental adoption
- Property tests use Hypothesis with a minimum of 100 examples per property
- Real-world config files from `acme-SaaS-IaC/cdk/configs/` should be used for integration testing
