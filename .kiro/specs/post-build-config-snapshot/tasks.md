# Implementation Plan: Post-Build Config Snapshot

## Overview

Add a `save_config_snapshot()` method to `CdkConfig` and call it from `WorkloadFactory.__generate_deployments()` after all deployments are processed. This captures the post-mutation config state (merged permissions, env vars, etc.) in `.dynamic/config.json`. ~15 lines of production code across two files, plus unit tests.

## Tasks

- [x] 1. Add `_dynamic_config_path` and `save_config_snapshot()` to CdkConfig
  - [x] 1.1 Store the computed `.dynamic/` path as `_dynamic_config_path` in `__resolved_config()`
    - In `cdk_config.py`, initialize `self._dynamic_config_path: str | None = None` in `__init__`
    - In `__resolved_config()`, after computing the `path` variable (the `.dynamic/config.json` path), store it as `self._dynamic_config_path = path`
    - _Requirements: 1.1, 4.1_
  - [x] 1.2 Add the public `save_config_snapshot()` method to `CdkConfig`
    - Add method that checks `_dynamic_config_path` is not `None`, raises `ValueError` if it is
    - Call `JsonLoadingUtility.save(self.config, self._dynamic_config_path)` to write the current in-memory config
    - Print a diagnostic message: `"📀 Saving post-build config snapshot to {path}"`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 4.1, 4.2, 4.3_

- [x] 2. Call `save_config_snapshot()` from WorkloadFactory
  - [x] 2.1 Add the post-build snapshot call in `__generate_deployments()`
    - In `workload_factory.py`, after the `for deployment in self.workload.deployments:` loop completes and before the final `logger.info "Completed"` message
    - Add `print("📀 Saving post-build config snapshot")` followed by `self.cdk_config.save_config_snapshot()`
    - This runs unconditionally after the loop — even if all deployments were disabled
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 3. Checkpoint - Verify production code
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Unit tests for config snapshot
  - [ ]* 4.1 Write unit tests in `tests/unit/test_config_snapshot.py`
    - `test_save_config_snapshot_writes_file` — create a CdkConfig with a known config, call `save_config_snapshot()`, read the file back, assert it matches
    - `test_save_config_snapshot_raises_without_resolved_path` — set `_dynamic_config_path` to `None`, call `save_config_snapshot()`, assert `ValueError`
    - `test_save_config_snapshot_overwrites_previous` — call twice with different config states, assert file reflects second call
    - `test_save_config_snapshot_captures_mutations` — load config, mutate in-place, call `save_config_snapshot()`, assert file contains mutations
    - _Requirements: 1.1, 1.4, 1.5, 3.1, 3.2, 3.3_

- [x] 5. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- The implementation is ~15 lines of production code across `cdk_config.py` and `workload_factory.py`
- No property-based tests — this is a side-effect-only operation with no meaningful input domain to explore
- `save_config_snapshot()` reuses the same `JsonLoadingUtility.save()` and path logic already in `__resolved_config`
