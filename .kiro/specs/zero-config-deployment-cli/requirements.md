# Requirements Document

## Introduction

This feature makes the `CdkDeploymentCommand` base class handle all JSON-based environment variable loading natively, eliminating the need for consuming projects to subclass and override `set_environment_variables`, `load_env_file`, `validate_required_variables`, `select_environment`, and `display_configuration_summary` with nearly identical boilerplate. After this change, a consuming project with `deployment.*.json` files and a `config.json` needs only a one-liner `deploy.py`:

```python
#!/usr/bin/env python3
from cdk_factory.commands.deployment_command import CdkDeploymentCommand
if __name__ == "__main__":
    CdkDeploymentCommand.main()
```

The two validation projects are Acme-SaaS-IaC (`cdk/deploy.py`) and NCA-SaaS-UI (`devops/cdk/deploy.py`), both of which currently have ~280-line subclasses with 95%+ identical code. This feature absorbs that duplicated logic into the base class while preserving backward compatibility for `.env`-based projects and allowing project-specific customization via subclassing or an optional `deploy.config.json`.

## Glossary

- **CdkDeploymentCommand**: The base class in `cdk-factory/src/cdk_factory/commands/deployment_command.py` that provides CDK synth/deploy/diff/destroy operations, env loading, validation, and interactive menus.
- **Deployment_JSON**: A `deployment.*.json` file in the `deployments/` directory that describes an environment's parameters, account, region, profile, and workload configuration.
- **Parameters_Block**: The `"parameters"` key inside a Deployment_JSON file containing key-value pairs that become environment variables (e.g., `AWS_ACCOUNT`, `WORKLOAD_NAME`, `TENANT_NAME`).
- **Config_JSON**: A `config.json` file in the project's script directory containing CDK parameter definitions with optional default `value` fields and `env_var_name` mappings.
- **Deploy_Config_JSON**: An optional `deploy.config.json` file in the project's script directory that provides project-specific overrides (custom required_vars, custom STANDARD_ENV_VARS mappings, custom STAGE_KEYWORDS) without requiring a Python subclass.
- **Standard_Env_Vars**: A mapping of top-level Deployment_JSON field names to environment variable names (e.g., `aws_account` → `AWS_ACCOUNT`, `aws_region` → `AWS_REGION`).
- **Placeholder_Resolution**: The process of replacing `{{KEY}}` references in environment variable values with the actual value of the referenced environment variable, run iteratively to handle chained references.
- **JSON_Mode**: The deployment mode activated when auto-discovered Deployment_JSON files contain a Parameters_Block; env vars are loaded from JSON rather than `.env` files.
- **Env_File_Mode**: The legacy deployment mode where env vars are loaded from `.env` files using `KEY=VALUE` syntax.
- **TODO_Placeholder**: A `<TODO>` string value in an environment variable indicating the value has not been configured yet.
- **EnvironmentConfig**: A dataclass describing one deployment environment with name, env_file, git_branch, and extra (dict) fields.

## Requirements

### Requirement 1: Auto-Detect JSON vs Env-File Mode

**User Story:** As a library consumer, I want the base class to automatically detect whether to use JSON-based or `.env`-based environment loading, so that I do not need to override `load_env_file` or `set_environment_variables` for JSON-based projects.

#### Acceptance Criteria

1. WHEN auto-discovered Deployment_JSON files contain a Parameters_Block, THE CdkDeploymentCommand SHALL activate JSON_Mode for environment variable loading
2. WHEN auto-discovered Deployment_JSON files do not contain a Parameters_Block, THE CdkDeploymentCommand SHALL activate Env_File_Mode and use the existing `.env` file loading logic
3. WHEN no Deployment_JSON files are discovered and the subclass provides EnvironmentConfig entries with non-empty env_file paths, THE CdkDeploymentCommand SHALL use Env_File_Mode
4. THE CdkDeploymentCommand SHALL determine the mode per-environment based on the selected EnvironmentConfig's extra dict containing a Parameters_Block

### Requirement 2: Native JSON-Based Environment Variable Loading

**User Story:** As a library consumer, I want the base class to natively load environment variables from Deployment_JSON parameters, standard fields, code repository config, and management account config, so that I do not need to duplicate this logic in every project.

#### Acceptance Criteria

1. WHEN JSON_Mode is active, THE CdkDeploymentCommand SHALL set the ENVIRONMENT env var from the deployment config's `name` field
2. WHEN JSON_Mode is active, THE CdkDeploymentCommand SHALL set env vars from all key-value pairs in the Parameters_Block
3. WHEN JSON_Mode is active, THE CdkDeploymentCommand SHALL map Standard_Env_Vars from top-level Deployment_JSON fields to env vars using the default mapping: aws_account→AWS_ACCOUNT, aws_region→AWS_REGION, aws_profile→AWS_PROFILE, git_branch→GIT_BRANCH, workload_name→WORKLOAD_NAME, tenant_name→TENANT_NAME
4. WHEN JSON_Mode is active and the Deployment_JSON contains a `code_repository` object, THE CdkDeploymentCommand SHALL set CODE_REPOSITORY_NAME from `code_repository.name` and CODE_REPOSITORY_ARN from `code_repository.connector_arn`
5. WHEN JSON_Mode is active and the Deployment_JSON contains a `management` object, THE CdkDeploymentCommand SHALL set MANAGEMENT_ACCOUNT from `management.account`, MANAGEMENT_ACCOUNT_ROLE_ARN from `management.cross_account_role_arn`, and MGMT_R53_HOSTED_ZONE_ID from `management.hosted_zone_id`
6. WHEN JSON_Mode is active and a Config_JSON file exists in the script directory, THE CdkDeploymentCommand SHALL load default values from Config_JSON `cdk.parameters` entries for any env var not already set (where the entry has both `env_var_name` and `value` fields)
7. WHEN JSON_Mode is active and DEPLOYMENT_NAMESPACE is not set after all other loading, THE CdkDeploymentCommand SHALL default DEPLOYMENT_NAMESPACE to the value of TENANT_NAME
8. WHEN JSON_Mode is active, THE CdkDeploymentCommand SHALL resolve all `{{PLACEHOLDER}}` references in env var values using iterative Placeholder_Resolution with a maximum of 5 passes to prevent infinite loops on circular references

### Requirement 3: Sensible Default Required Variables

**User Story:** As a library consumer, I want the base class to provide the standard set of 8 required variables as the default, so that I do not need to override `required_vars` in every JSON-based project.

#### Acceptance Criteria

1. WHEN JSON_Mode is active, THE CdkDeploymentCommand SHALL use the following default required_vars: AWS_ACCOUNT (AWS Account ID), AWS_REGION (AWS Region), WORKLOAD_NAME (Workload Name), ENVIRONMENT (Environment name), TENANT_NAME (Tenant name. Required for namespaces), GIT_BRANCH (Git branch), CODE_REPOSITORY_NAME (Code repository name), CODE_REPOSITORY_ARN (Code repository ARN)
2. WHEN Env_File_Mode is active, THE CdkDeploymentCommand SHALL use the existing 4-variable default required_vars: AWS_ACCOUNT, AWS_REGION, AWS_PROFILE, WORKLOAD_NAME
3. WHEN a subclass overrides the required_vars property, THE CdkDeploymentCommand SHALL use the subclass value regardless of mode

### Requirement 4: TODO Placeholder Validation

**User Story:** As a library consumer, I want the base class to detect `<TODO>` placeholder values in environment variables by default, so that I do not need to override `validate_required_variables` for this common check.

#### Acceptance Criteria

1. WHEN validation runs, THE CdkDeploymentCommand SHALL scan all environment variables for values equal to `<TODO>`
2. WHEN one or more TODO_Placeholder values are found, THE CdkDeploymentCommand SHALL display the count of unresolved placeholders, list each variable name and its `<TODO>` value, and exit with code 1
3. THE CdkDeploymentCommand SHALL run TODO_Placeholder detection after the existing required variable validation

### Requirement 5: Enhanced Environment Selection with Descriptions

**User Story:** As a library consumer, I want the base class environment selection menu to show descriptions alongside environment names, so that I do not need to override `select_environment` for this common enhancement.

#### Acceptance Criteria

1. WHEN a Deployment_JSON config has a `description` field, THE CdkDeploymentCommand SHALL display the environment option as `{name}: {description}` in the selection menu
2. WHEN a Deployment_JSON config does not have a `description` field, THE CdkDeploymentCommand SHALL display only the environment name in the selection menu
3. WHEN Env_File_Mode is active and no descriptions are available, THE CdkDeploymentCommand SHALL display only environment names (preserving existing behavior)

### Requirement 6: Enhanced Configuration Summary Display

**User Story:** As a library consumer, I want the base class to display a richer deployment configuration summary by default, so that I do not need to override `display_configuration_summary` for the standard fields.

#### Acceptance Criteria

1. WHEN JSON_Mode is active, THE CdkDeploymentCommand SHALL display the following fields in the configuration summary: Environment, Account, Region, Profile, Workload, Git Branch, Config File
2. WHEN Env_File_Mode is active, THE CdkDeploymentCommand SHALL display the existing summary format: Config file, Environment, AWS Account, AWS Region, Git Branch
3. WHEN a subclass overrides display_configuration_summary, THE CdkDeploymentCommand SHALL use the subclass implementation

### Requirement 7: Optional Deploy Configuration File

**User Story:** As a library consumer, I want to customize deployment behavior via a `deploy.config.json` file without writing a Python subclass, so that simple configuration changes do not require code.

#### Acceptance Criteria

1. WHEN a Deploy_Config_JSON file exists in the script directory, THE CdkDeploymentCommand SHALL load it during initialization
2. WHEN Deploy_Config_JSON contains a `required_vars` array of `[var_name, description]` pairs, THE CdkDeploymentCommand SHALL use those as the required_vars (replacing the default)
3. WHEN Deploy_Config_JSON contains a `standard_env_vars` array of `[json_key, env_key]` pairs, THE CdkDeploymentCommand SHALL use those as the Standard_Env_Vars mapping (replacing the default)
4. WHEN Deploy_Config_JSON contains a `stage_keywords` object, THE CdkDeploymentCommand SHALL use it as the STAGE_KEYWORDS mapping (replacing the default)
5. WHEN no Deploy_Config_JSON file exists, THE CdkDeploymentCommand SHALL use the built-in defaults for all configurable values
6. WHEN a subclass overrides a property that Deploy_Config_JSON also configures, THE CdkDeploymentCommand SHALL use the subclass override (subclass takes precedence over Deploy_Config_JSON)

### Requirement 8: JSON-Mode Load_Env_File Bypass

**User Story:** As a library consumer, I want the base class to skip `.env` file loading when in JSON_Mode, so that I do not need to override `load_env_file` to return an empty dict.

#### Acceptance Criteria

1. WHEN JSON_Mode is active, THE CdkDeploymentCommand SHALL return an empty dict from load_env_file without attempting to read a file from disk
2. WHEN Env_File_Mode is active, THE CdkDeploymentCommand SHALL use the existing load_env_file logic that reads `KEY=VALUE` pairs from the env file path

### Requirement 9: Backward Compatibility

**User Story:** As a library consumer with an existing subclass, I want the base class changes to not break my existing deploy.py, so that I can adopt the new features incrementally.

#### Acceptance Criteria

1. WHEN a subclass overrides set_environment_variables, THE CdkDeploymentCommand SHALL call the subclass implementation instead of the JSON_Mode logic
2. WHEN a subclass overrides load_env_file, THE CdkDeploymentCommand SHALL call the subclass implementation instead of the JSON_Mode bypass
3. WHEN a subclass overrides validate_required_variables, THE CdkDeploymentCommand SHALL call the subclass implementation (which may call super() to include TODO_Placeholder detection)
4. WHEN a subclass overrides select_environment, THE CdkDeploymentCommand SHALL call the subclass implementation instead of the description-enhanced version
5. WHEN a subclass overrides display_configuration_summary, THE CdkDeploymentCommand SHALL call the subclass implementation instead of the enhanced version
6. THE CdkDeploymentCommand SHALL preserve the existing EnvironmentConfig dataclass interface without adding required fields

### Requirement 10: Zero-Config One-Liner Deploy Script

**User Story:** As a library consumer, I want to use `CdkDeploymentCommand.main()` directly without subclassing when my project follows the standard JSON deployment pattern, so that my deploy.py is a single line.

#### Acceptance Criteria

1. WHEN CdkDeploymentCommand.main() is called without subclassing and Deployment_JSON files exist in the deployments/ directory, THE CdkDeploymentCommand SHALL auto-discover environments, load env vars from JSON, validate required variables, display the enhanced summary, and execute the selected CDK operation
2. WHEN CdkDeploymentCommand.main() is called without subclassing and no Deployment_JSON files exist, THE CdkDeploymentCommand SHALL raise a NotImplementedError indicating that deployment files or a subclass are required
3. WHEN CdkDeploymentCommand is used as a one-liner, THE CdkDeploymentCommand SHALL support all existing CLI arguments: --config, --dry-run, --environment, --operation, --destroy-target, --target-profile, --confirm-destroy, --skip-dns-cleanup, --stack-delete-timeout, --no-interactive-failures
