# Implementation Plan: Versioning CLI

## Overview

Implement a standalone CLI module (`cdk_factory.utilities.versioning_cli`) that reads version information from `package.json`, computes a build number via git commit history using the existing `VersionBuilder`, writes a `version.txt` file, and optionally updates `package.json`. Also enhance `StaticWebSiteStack.__get_version_number` with a `package.json` fallback when `version.txt` is absent.

## Tasks

- [x] 1. Extend VersionSource enum and set up module structure
  - [x] 1.1 Add `PACKAGE_JSON` member to `VersionSource` enum in `version_builder.py`
    - Add `PACKAGE_JSON = "package_json"` to the existing `VersionSource` enum
    - _Requirements: 7.1_

  - [x] 1.2 Create the `versioning_cli.py` module with class skeleton and CLI entry point
    - Create `src/cdk_factory/utilities/versioning_cli.py`
    - Define `VersioningCli` class with `__init__(self, project_root, output_dir)` signature
    - Add stub methods: `read_package_json_version`, `compute_version`, `write_version_file`, `update_package_json`
    - Add `main()` function with `argparse` setup for `--project-root`, `--output-dir`, `--update-package-json`, `--version-source`
    - Add `if __name__ == "__main__"` guard
    - Follow the same pattern as `ssm_resolver.py` (class + main + guard)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [x] 2. Implement package.json reading and validation
  - [x] 2.1 Implement `read_package_json_version` method
    - Read `package.json` from `project_root` directory
    - Validate file exists, is valid JSON, contains `"version"` field
    - Validate version matches `MAJOR.MINOR.PATCH` format (non-negative integers)
    - Exit with code 1 and descriptive stderr messages on each failure mode
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6_

  - [ ]* 2.2 Write property test for invalid package.json rejection
    - **Property 2: Invalid package.json content rejection**
    - Generate invalid JSON strings and invalid semver strings via Hypothesis
    - Assert CLI exits with non-zero status and produces stderr output
    - Test file: `tests/properties/versioning_cli/test_versioning_cli_properties.py`
    - **Validates: Requirements 1.4, 1.5, 1.6**

  - [ ]* 2.3 Write unit tests for package.json reading
    - Test missing file, invalid JSON, missing version field, invalid semver format
    - Test valid package.json returns correct version string
    - Test `--project-root` defaults to cwd when not provided
    - Test file: `tests/unit/utilities/test_versioning_cli.py`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 3. Implement version computation with VersionBuilder delegation
  - [x] 3.1 Implement `compute_version` method
    - For `version_source="package-json"`: extract major.minor from package.json version, call `VersionBuilder.get_git_build_number(major_minor, project_root)`, return `major.minor.build_number`
    - For `version_source="git-tag"`: instantiate `VersionBuilder(VersionSource.GIT_TAG)` and delegate both base version resolution and build number computation
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 7.1, 7.2, 7.3, 7.4_

  - [ ]* 3.2 Write unit tests for version computation
    - Mock `VersionBuilder.get_git_build_number` to verify delegation
    - Test `package-json` source passes correct major.minor to `get_git_build_number`
    - Test `git-tag` source delegates to VersionBuilder with `VersionSource.GIT_TAG`
    - Test file: `tests/unit/utilities/test_versioning_cli.py`
    - _Requirements: 2.1, 7.1, 7.2, 7.3_

- [x] 4. Implement version.txt writing and CLI output
  - [x] 4.1 Implement `write_version_file` method
    - Write computed version string to `version.txt` in `output_dir` with no trailing newline
    - Create `output_dir` and parent directories if they don't exist
    - Overwrite existing `version.txt` without prompting
    - Exit with code 1 and stderr message on filesystem write failures
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 4.2 Wire `main()` to print computed version to stdout and exit 0 on success
    - Print only the computed version string to stdout (no extra text)
    - Enable shell variable capture: `VERSION=$(python -m cdk_factory.utilities.versioning_cli --project-root .)`
    - Exit with code 0 on success
    - _Requirements: 3.6, 5.8_

  - [ ]* 4.3 Write property test for version file write round-trip
    - **Property 1: Version file write round-trip**
    - Generate random valid `MAJOR.MINOR.PATCH` version strings via Hypothesis
    - Write via `write_version_file`, read back, assert exact string match with no trailing newline
    - Assert stdout output matches written version
    - Test file: `tests/properties/versioning_cli/test_versioning_cli_properties.py`
    - **Validates: Requirements 3.1, 3.6**

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement package.json update functionality
  - [x] 6.1 Implement `update_package_json` method
    - Detect original file indentation (2 spaces, 4 spaces, tab)
    - Update only the `"version"` field to the computed version
    - Preserve all other fields, key ordering, and indentation style
    - Exit with code 1 if package.json doesn't exist or write fails
    - _Requirements: 4.1, 4.3, 4.4_

  - [ ]* 6.2 Write property test for package.json update preserves structure
    - **Property 3: package.json update preserves structure**
    - Generate random valid package.json objects with various fields via Hypothesis
    - Update version, assert only `"version"` field changed, all other fields/ordering/indentation preserved
    - Test file: `tests/properties/versioning_cli/test_versioning_cli_properties.py`
    - **Validates: Requirements 4.1, 4.3**

  - [ ]* 6.3 Write property test for package.json unchanged without update flag
    - **Property 4: package.json unchanged without update flag**
    - Generate random valid package.json content, run CLI without `--update-package-json`
    - Assert file is byte-for-byte identical after CLI execution
    - Test file: `tests/properties/versioning_cli/test_versioning_cli_properties.py`
    - **Validates: Requirements 4.2**

- [x] 7. Implement CLI argument validation and error handling
  - [x] 7.1 Add `--project-root` path validation in `main()`
    - Validate path exists and is a directory before proceeding
    - Exit with code 1 and descriptive stderr message for invalid paths
    - Default to current working directory when not provided
    - _Requirements: 5.7, 1.2_

  - [x] 7.2 Add `--version-source` validation in argparse
    - Use `choices=["package-json", "git-tag"]` in argparse definition
    - argparse handles invalid values automatically with usage error
    - _Requirements: 5.9_

  - [ ]* 7.3 Write unit tests for CLI argument parsing and validation
    - Test all argument combinations and defaults
    - Test invalid `--project-root` exits with non-zero code and correct error
    - Test invalid `--version-source` produces argparse usage error
    - Test file: `tests/unit/utilities/test_versioning_cli.py`
    - _Requirements: 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.9_

- [x] 8. Implement StaticWebSiteStack package.json fallback
  - [x] 8.1 Enhance `__get_version_number` with parent-directory package.json traversal
    - Keep existing `version.txt` read as primary source
    - When `version.txt` not found: traverse parent directories from `assets_path` up to 10 levels
    - If `package.json` found with valid semver version field, use that version
    - If invalid or missing package.json: use default `"0.0.1.cdk.factory"` with warning log
    - If nothing found within traversal limit: use default with warning log
    - Modify `src/cdk_factory/stack_library/websites/static_website_stack.py`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 8.2 Write property test for parent directory traversal
    - **Property 5: Parent directory traversal finds package.json**
    - Generate random depths 1-10 and valid package.json content via Hypothesis
    - Create nested temp directory structures, place package.json at ancestor
    - Assert `__get_version_number` returns the correct version
    - Test file: `tests/properties/versioning_cli/test_versioning_cli_properties.py`
    - **Validates: Requirements 6.2, 6.3**

  - [ ]* 8.3 Write unit tests for static website stack version fallback
    - Test version.txt present → uses it (existing behavior)
    - Test version.txt absent, package.json at parent → uses package.json version
    - Test version.txt absent, no package.json → uses default
    - Test invalid package.json → uses default with warning
    - Test file: `tests/unit/stack_library/test_static_website_version_fallback.py`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The CLI follows the established `ssm_resolver.py` pattern: class + `main()` + `__name__` guard
- All git/build-number logic is delegated to the existing `VersionBuilder` class — no reimplementation
- The project uses pytest for unit tests and Hypothesis for property-based testing

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "7.1", "7.2"] },
    { "id": 2, "tasks": ["2.2", "2.3", "3.1"] },
    { "id": 3, "tasks": ["3.2", "4.1", "4.2"] },
    { "id": 4, "tasks": ["4.3", "6.1", "7.3"] },
    { "id": 5, "tasks": ["6.2", "6.3", "8.1"] },
    { "id": 6, "tasks": ["8.2", "8.3"] }
  ]
}
```
