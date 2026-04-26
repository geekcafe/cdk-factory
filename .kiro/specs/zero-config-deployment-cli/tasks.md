# Implementation Plan: Zero-Config Deployment CLI

## Overview

Absorb the duplicated JSON-based deployment logic from `NcaSaasDeployment` and `NcaSaasUiDeployment` subclasses into the `CdkDeploymentCommand` base class. All changes target `cdk-factory/src/cdk_factory/commands/deployment_command.py` (steps 1–10), then rewrite the two consuming project deploy scripts as one-liners (steps 11–12).

## Tasks

- [ ] 1. Add STANDARD_ENV_VARS class attribute and `_is_json_mode` helper
  - [ ] 1.1 Add `STANDARD_ENV_VARS` class attribute to `CdkDeploymentCommand`
    - Add the list of `(json_key, env_key)` tuples as a class-level constant, matching the mapping used by both subclasses: `aws_account→AWS_ACCOUNT`, `aws_region→AWS_REGION`, `aws_profile→AWS_PROFILE`, `git_branch→GIT_BRANCH`, `workload_name→WORKLOAD_NAME`, `tenant_name→TENANT_NAME`
    - Place it alongside the existing `STAGE_KEYWORDS` and `DELETION_ORDER` class attributes
    - _Requirements: 2.3, 9.6_
  - [ ] 1.2 Add `_is_json_mode(self, env_config)` private method
    - Returns `True` if `env_config.extra.get("parameters")` is truthy (non-empty dict)
    - Returns `False` if `extra` has no `parameters` key, or `parameters` is empty/falsy
    - _Requirements: 1.1, 1.2, 1.4_
  - [ ]* 1.3 Write property test for mode detection
    - **Property 1: Mode detection is determined by parameters key presence**
    - Generate random `extra` dicts with/without `parameters` key, empty/non-empty values
    - Verify `_is_json_mode` returns `True` iff `parameters` is truthy
    - **Validates: Requirements 1.1, 1.2, 1.4**

- [ ] 2. Add `_load_deploy_config` and `deploy.config.json` support
  - [ ] 2.1 Initialize `_deploy_config` in `__init__` and add `_load_deploy_config` method
    - Add `self._deploy_config: Dict[str, Any] = {}` in `__init__` before `_auto_discover_deployments()`
    - Add `self._load_deploy_config()` call after `_auto_discover_deployments()`
    - `_load_deploy_config` reads `deploy.config.json` from `self.script_dir` if it exists, stores parsed dict in `self._deploy_config`
    - If `deploy.config.json` contains `stage_keywords`, update `self.STAGE_KEYWORDS` with those values
    - _Requirements: 7.1, 7.4, 7.5_
  - [ ]* 2.2 Write property test for deploy.config.json overrides
    - **Property 6: deploy.config.json overrides replace built-in defaults**
    - Generate random `deploy.config.json` contents with `required_vars` and `standard_env_vars` arrays
    - Verify they override the built-in defaults
    - **Validates: Requirements 7.2, 7.3**

- [ ] 3. Add `_set_json_environment_variables` private method
  - [ ] 3.1 Implement `_set_json_environment_variables(self, env_config)` method
    - Extract the JSON env var loading logic from the subclasses into this new private method
    - Steps: (1) set ENVIRONMENT from config name, (2) set all parameters block key-values, (3) map STANDARD_ENV_VARS (using `_deploy_config` override if present), (4) set code_repository fields, (5) set management fields, (6) load config.json defaults for unset vars, (7) default DEPLOYMENT_NAMESPACE to TENANT_NAME, (8) resolve `{{PLACEHOLDER}}` references with max 5 passes
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_
  - [ ]* 3.2 Write property test for JSON loading
    - **Property 2: JSON loading sets all parameters as environment variables**
    - Generate random deployment configs with parameters, name, and standard fields
    - Verify all expected env vars are set after calling `_set_json_environment_variables`
    - **Validates: Requirements 2.1, 2.2, 2.3**
  - [ ]* 3.3 Write property test for placeholder resolution
    - **Property 3: Placeholder resolution is idempotent and bounded**
    - Generate random env var dicts with `{{KEY}}` references including chains and circular refs
    - Verify resolution terminates within 5 passes and is idempotent after convergence
    - **Validates: Requirements 2.8**

- [ ] 4. Modify `set_environment_variables` to check mode and dispatch
  - [ ] 4.1 Add JSON-mode branch to `set_environment_variables`
    - At the top of the method, check `if self._is_json_mode(env_config)` → call `self._set_json_environment_variables(env_config)` and return
    - Otherwise fall through to existing env-file logic unchanged
    - _Requirements: 1.1, 1.2, 9.1_

- [ ] 5. Modify `load_env_file` to return empty dict in JSON mode
  - [ ] 5.1 Add JSON-mode check to `load_env_file`
    - At the top of the method, check `if hasattr(self, "_current_env_config") and self._is_json_mode(self._current_env_config)` → return `{}`
    - Otherwise fall through to existing `.env` file loading logic unchanged
    - _Requirements: 8.1, 8.2, 9.2_
  - [ ]* 5.2 Write property test for load_env_file JSON mode bypass
    - **Property 7: load_env_file returns empty dict in JSON mode**
    - Generate random JSON-mode EnvironmentConfigs, verify `load_env_file` returns `{}`
    - **Validates: Requirements 8.1**

- [ ] 6. Modify `required_vars` property to be mode-aware
  - [ ] 6.1 Update `required_vars` property with deploy.config.json and JSON-mode defaults
    - Check `_deploy_config.get("required_vars")` first → return those pairs as tuples if present
    - Then check `hasattr(self, "_current_env_config") and self._is_json_mode(self._current_env_config)` → return the 8-var JSON-mode default list
    - Otherwise return the existing 4-var env-file default list
    - _Requirements: 3.1, 3.2, 3.3, 7.2_

- [ ] 7. Modify `validate_required_variables` to add TODO placeholder check
  - [ ] 7.1 Add `<TODO>` placeholder detection after existing validation
    - After the existing missing-var check and "Configuration validated" message, scan all `os.environ` items for values equal to `"<TODO>"`
    - If any found: print count, list each var name sorted, print guidance message, `sys.exit(1)`
    - _Requirements: 4.1, 4.2, 4.3, 9.3_
  - [ ]* 7.2 Write property test for TODO detection
    - **Property 4: TODO placeholder detection finds all unresolved TODOs**
    - Generate random env var dicts with some values set to `"<TODO>"`
    - Verify exact match of detected keys — no false positives, no false negatives
    - **Validates: Requirements 4.1, 4.2**

- [ ] 8. Modify `select_environment` to show descriptions
  - [ ] 8.1 Update `select_environment` to include description from deployment configs
    - For each environment key, check `self._deployment_configs.get(key, {}).get("description", "")`
    - If description is non-empty, format option as `"{name}: {description}"`; otherwise just `"{name}"`
    - _Requirements: 5.1, 5.2, 5.3, 9.4_
  - [ ]* 8.2 Write property test for environment selection options
    - **Property 5: Environment selection options include description iff present**
    - Generate random deployment config dicts with/without description fields
    - Verify option string format matches expected pattern
    - **Validates: Requirements 5.1, 5.2**

- [ ] 9. Modify `display_configuration_summary` to be mode-aware
  - [ ] 9.1 Add JSON-mode branch to `display_configuration_summary`
    - If `hasattr(self, "_current_env_config") and self._is_json_mode(self._current_env_config)`: display the richer 7-field format (Environment, Account, Region, Profile, Workload, Git Branch, Config File)
    - Otherwise display the existing 5-field format unchanged
    - _Requirements: 6.1, 6.2, 9.5_

- [ ] 10. Store `_current_env_config` in `run()` method
  - [ ] 10.1 Add `self._current_env_config = env_config` in `run()` after environment selection
    - Place it immediately after the `env_config` is determined (both the named-env and interactive-select branches)
    - This must be set before `self.load_env_file()` is called so mode-aware methods can reference it
    - _Requirements: 1.4, 8.1, 3.1, 6.1_

- [ ] 11. Checkpoint — Verify base class changes
  - Ensure all tests pass, ask the user if questions arise.
  - Verify that the existing `select_environment`, `run`, and `main` methods still work with the new mode-aware logic
  - Confirm backward compatibility: a subclass that overrides any of the modified methods should still work via Python MRO
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [ ] 12. Rewrite `Acme-SaaS-IaC/cdk/deploy.py` as one-liner
  - [ ] 12.1 Replace the `NcaSaasDeployment` subclass with a one-liner
    - Replace the entire file contents with the 4-line one-liner script:
      ```python
      #!/usr/bin/env python3
      from cdk_factory.commands.deployment_command import CdkDeploymentCommand
      if __name__ == "__main__":
          CdkDeploymentCommand.main()
      ```
    - Remove all imports of `json`, `os`, `sys`, `Path`, `Dict`, `List`, `Tuple`, `EnvironmentConfig`
    - Remove the entire `NcaSaasDeployment` class and all its methods
    - _Requirements: 10.1, 10.3_

- [ ] 13. Rewrite `NCA-SaaS-UI/devops/cdk/deploy.py` as one-liner
  - [ ] 13.1 Replace the `NcaSaasUiDeployment` subclass with a one-liner
    - Replace the entire file contents with the same 4-line one-liner script
    - Remove the entire `NcaSaasUiDeployment` class and all its methods
    - _Requirements: 10.1, 10.3_

- [ ] 14. Final checkpoint — Verify end-to-end
  - Ensure all tests pass, ask the user if questions arise.
  - Verify both one-liner deploy scripts can be parsed without syntax errors
  - Confirm the base class auto-discovers `deployment.*.json` files and handles the full flow
  - _Requirements: 10.1, 10.2, 10.3_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All code changes in tasks 1–10 target a single file: `cdk-factory/src/cdk_factory/commands/deployment_command.py`
- Tasks 12–13 each target a single consumer project file
- Property tests use Python Hypothesis library (project standard)
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation before moving to consumer rewrites
