# Requirements Document

## Introduction

The `.dynamic/config.json` file currently captures the resolved configuration state after placeholder substitution (performed by `CdkConfig.__resolved_config()`), but before any stack `build()` methods run. Stack modules like `LambdaStack.build()` mutate the config dicts in-place (e.g., merging `additional_permissions` and `additional_environment_variables` into individual resource entries). Because the config dict is passed by reference, these mutations are reflected in the original `CdkConfig.config` object — but the on-disk snapshot is stale.

This feature adds a post-build config snapshot so that `.dynamic/config.json` reflects the fully resolved, post-mutation state of the configuration after all stacks have been built. This is purely a debugging/troubleshooting aid and does not affect CDK synthesis or deployment.

## Glossary

- **CdkConfig**: The configuration class (`cdk_factory.configurations.cdk_config.CdkConfig`) responsible for loading, resolving placeholders in, and persisting the CDK configuration dictionary.
- **Dynamic_Config**: The `.dynamic/config.json` file written by CdkConfig that contains the resolved configuration snapshot.
- **WorkloadFactory**: The orchestration class (`cdk_factory.workload.workload_factory.WorkloadFactory`) that owns the CdkConfig instance, iterates over deployments, and delegates to stack and pipeline builders.
- **Stack_Build**: The `build()` method on a stack module (e.g., `LambdaStack.build()`) that mutates the config dict in-place to merge stack-level defaults into resource entries.
- **Post_Build_Snapshot**: A re-save of the Dynamic_Config performed after all Stack_Build methods have completed, capturing the post-mutation state.
- **JsonLoadingUtility**: The utility class (`cdk_factory.utilities.json_loading_utility.JsonLoadingUtility`) that provides `save()` for writing dicts to JSON files.
- **Cdk_Parameters_Section**: The `config["cdk"]` key in the configuration dictionary that contains placeholder definitions and must be preserved unchanged across saves.

## Requirements

### Requirement 1: Expose a public snapshot method on CdkConfig

**User Story:** As a developer debugging CDK deployments, I want CdkConfig to expose a public method that re-saves the current in-memory config state to the Dynamic_Config path, so that I can capture post-mutation configuration without duplicating save logic.

#### Acceptance Criteria

1. THE CdkConfig SHALL expose a public method named `save_config_snapshot` that writes the current `config` dictionary to the Dynamic_Config file path.
2. WHEN `save_config_snapshot` is called, THE CdkConfig SHALL preserve the Cdk_Parameters_Section by writing `config["cdk"]` with the original cdk parameters values, consistent with the existing save logic in `__resolved_config`.
3. WHEN `save_config_snapshot` is called, THE CdkConfig SHALL use `JsonLoadingUtility.save` to write the configuration as indented JSON.
4. IF the Dynamic_Config file path has not been established (i.e., `__resolved_config` was not previously called), THEN THE CdkConfig SHALL raise a `ValueError` with a descriptive message.
5. WHEN `save_config_snapshot` is called multiple times, THE CdkConfig SHALL overwrite the previous Dynamic_Config file each time with the current in-memory state (idempotent write).

### Requirement 2: Trigger post-build snapshot from WorkloadFactory

**User Story:** As a developer debugging CDK deployments, I want the orchestration layer to automatically re-save the Dynamic_Config after all stacks have been built, so that the snapshot reflects runtime mutations without manual intervention.

#### Acceptance Criteria

1. WHEN all deployments have been processed by `WorkloadFactory.__generate_deployments`, THE WorkloadFactory SHALL call `CdkConfig.save_config_snapshot` to persist the Post_Build_Snapshot.
2. THE WorkloadFactory SHALL call `save_config_snapshot` exactly once, after the loop over all deployments completes, regardless of how many deployments were processed.
3. WHEN `save_config_snapshot` is called by the WorkloadFactory, THE WorkloadFactory SHALL print a diagnostic message indicating the Post_Build_Snapshot has been saved.
4. IF no deployments are found or all deployments are disabled, THEN THE WorkloadFactory SHALL still call `save_config_snapshot` to ensure a consistent snapshot exists.

### Requirement 3: Post-build snapshot captures in-place mutations

**User Story:** As a developer troubleshooting lambda permission or environment variable issues, I want the Dynamic_Config to contain the merged `additional_permissions` and `additional_environment_variables` values after stack builds, so that I can verify the final resolved state.

#### Acceptance Criteria

1. WHEN a Stack_Build method merges `additional_permissions` into resource entries in-place, THE Post_Build_Snapshot SHALL contain those merged permission entries in the corresponding resource dictionaries.
2. WHEN a Stack_Build method merges `additional_environment_variables` into resource entries in-place, THE Post_Build_Snapshot SHALL contain those merged environment variable entries in the corresponding resource dictionaries.
3. THE Post_Build_Snapshot SHALL reflect the identical in-memory dictionary state held by `CdkConfig.config` at the time `save_config_snapshot` is called.

### Requirement 4: Snapshot preserves existing save semantics

**User Story:** As a developer, I want the post-build snapshot to follow the same file format and location conventions as the initial save, so that tooling and scripts that read `.dynamic/config.json` continue to work.

#### Acceptance Criteria

1. THE Post_Build_Snapshot SHALL be written to the same `.dynamic/config.json` file path used by the initial `__resolved_config` save.
2. THE Post_Build_Snapshot SHALL be formatted as indented JSON (2-space indent), consistent with `JsonLoadingUtility.save`.
3. THE Post_Build_Snapshot SHALL contain the complete configuration dictionary, including the Cdk_Parameters_Section.
