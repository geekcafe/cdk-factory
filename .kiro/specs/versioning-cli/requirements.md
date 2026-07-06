# Requirements Document

## Introduction

The versioning-cli feature adds a reusable CLI module to cdk-factory that reads version information from a Node.js project's `package.json`, computes a build number using git commit history, and writes a `version.txt` file. This eliminates the need for external versioning libraries (like `aplos_saas_devops_cdk.versioning.nodejs_version_cli`) and makes versioning a built-in capability of cdk-factory. Additionally, the static website stack is enhanced to fall back to reading `package.json` directly when `version.txt` is not present, providing a seamless experience for projects that don't have an explicit version-writing build step.

## Glossary

- **Versioning_CLI**: The CLI module at `cdk_factory.utilities.versioning_cli` that reads version from `package.json`, computes a build number from git commits, writes `version.txt`, and optionally updates `package.json`
- **Version_Builder**: The existing `VersionBuilder` class in `cdk_factory.utilities.version_builder` that handles version computation from files or git tags
- **Static_Website_Stack**: The CDK stack at `cdk_factory.stack_library.websites.static_website_stack` that deploys static websites with optional versioned CloudFront origin paths
- **Package_JSON**: The Node.js `package.json` file containing a `"version"` field in semver format (major.minor.patch)
- **Version_File**: A plain text file named `version.txt` containing the computed version string
- **Project_Root**: The root directory of the consuming project, containing `package.json` and the `.git` directory
- **Build_Number**: An integer derived from the git commit count since the last matching version tag, used as the patch component of the computed version
- **Computed_Version**: The final version string in the format `major.minor.patch` where patch is the Build_Number

## Requirements

### Requirement 1: Read Version from package.json

**User Story:** As a developer, I want the Versioning_CLI to read the base version from my project's `package.json`, so that I can manage my version in the standard Node.js way without maintaining a separate version file.

#### Acceptance Criteria

1. WHEN invoked with a `--project-root` argument, THE Versioning_CLI SHALL read the `"version"` field from the `package.json` file located in the specified Project_Root directory
2. IF the `--project-root` argument is not provided, THEN THE Versioning_CLI SHALL default to the current working directory as the Project_Root
3. IF the `package.json` file does not exist at the specified Project_Root, THEN THE Versioning_CLI SHALL exit with a non-zero status code and print an error message to stderr indicating the expected file path that was not found
4. IF the `package.json` file contains invalid JSON, THEN THE Versioning_CLI SHALL exit with a non-zero status code and print an error message to stderr indicating the file could not be parsed
5. IF the `package.json` file does not contain a `"version"` field, THEN THE Versioning_CLI SHALL exit with a non-zero status code and print an error message to stderr indicating the `"version"` field is missing
6. IF the `"version"` field is not a valid semver string matching the format `MAJOR.MINOR.PATCH` where MAJOR, MINOR, and PATCH are non-negative integers, THEN THE Versioning_CLI SHALL exit with a non-zero status code and print an error message to stderr indicating the value found and the expected format

### Requirement 2: Compute Build Number from Git History

**User Story:** As a developer, I want the build number to be derived from git commit count, so that each CI build produces a unique and incrementing version without manual intervention.

#### Acceptance Criteria

1. WHEN computing the version, THE Versioning_CLI SHALL use the Version_Builder's `get_git_build_number` method to count git commits since the most recent tag matching the `v{major}.{minor}.*` pattern
2. WHERE no matching git tag exists for the major.minor version, THE Versioning_CLI SHALL use the total commit count on the current branch as the Build_Number
3. IF the git commit-counting operation fails and the `CODEBUILD_BUILD_NUMBER` environment variable is set, THEN THE Versioning_CLI SHALL use the value of `CODEBUILD_BUILD_NUMBER` as the Build_Number
4. IF the git commit-counting operation fails and no `CODEBUILD_BUILD_NUMBER` environment variable is set, THEN THE Versioning_CLI SHALL use `0` as the Build_Number

### Requirement 3: Write version.txt File

**User Story:** As a developer, I want the CLI to write a `version.txt` file to a specified output directory, so that the Static_Website_Stack can read it during CDK synthesis.

#### Acceptance Criteria

1. THE Versioning_CLI SHALL write the Computed_Version as the sole content of a file named `version.txt` in the Project_Root directory by default, with no trailing newline or additional characters beyond the version string
2. WHEN invoked with a `--output-dir` argument, THE Versioning_CLI SHALL write the `version.txt` file to the specified directory instead of the Project_Root
3. IF the specified output directory does not exist, THEN THE Versioning_CLI SHALL create the directory and any intermediate parent directories before writing the Version_File
4. IF a `version.txt` file already exists at the target location, THEN THE Versioning_CLI SHALL overwrite it with the new Computed_Version without prompting
5. IF the Versioning_CLI cannot write the Version_File due to a filesystem error, THEN THE Versioning_CLI SHALL exit with a non-zero status code and print a descriptive error message to stderr indicating the write failure reason
6. THE Versioning_CLI SHALL print the Computed_Version to stdout as its only stdout output, with no additional text or formatting, enabling shell variable capture via command substitution (e.g., `VERSION=$(python -m cdk_factory.utilities.versioning_cli --project-root .)`)

### Requirement 4: Update package.json Version

**User Story:** As a developer, I want the option to update the version in `package.json` with the computed version, so that the built artifacts reflect the exact version that was deployed.

#### Acceptance Criteria

1. WHEN invoked with the `--update-package-json` flag, THE Versioning_CLI SHALL update the `"version"` field in the `package.json` file located in the Project_Root directory to the Computed_Version
2. WHEN the `--update-package-json` flag is not provided, THE Versioning_CLI SHALL leave the `package.json` file unchanged
3. WHEN updating `package.json`, THE Versioning_CLI SHALL preserve all other JSON fields, key ordering, and indentation style present in the original file
4. IF the `--update-package-json` flag is provided and no `package.json` file exists in the Project_Root directory, THEN THE Versioning_CLI SHALL exit with a non-zero exit code and output an error message indicating the file was not found

### Requirement 5: CLI Invocation Pattern

**User Story:** As a developer, I want to invoke the versioning CLI using the standard Python module pattern, so that it integrates consistently with other cdk-factory CLI utilities.

#### Acceptance Criteria

1. THE Versioning_CLI SHALL be invocable via `python -m cdk_factory.utilities.versioning_cli`
2. THE Versioning_CLI SHALL accept a `--project-root` argument specifying the path to the Node.js project root directory
3. WHEN the `--project-root` argument is not provided, THE Versioning_CLI SHALL default to the current working directory
4. THE Versioning_CLI SHALL accept a `--output-dir` argument specifying where to write the Version_File, defaulting to the `--project-root` directory when not provided
5. THE Versioning_CLI SHALL accept an `--update-package-json` flag to enable updating the package.json version field
6. THE Versioning_CLI SHALL accept a `--version-source` argument with values `package-json` or `git-tag`, defaulting to `package-json`
7. IF the path specified by `--project-root` does not exist or is not a directory, THEN THE Versioning_CLI SHALL exit with a non-zero exit code and print an error message indicating the invalid path
8. WHEN the CLI completes version file generation successfully, THE Versioning_CLI SHALL exit with exit code 0
9. IF an unrecognized value is provided for `--version-source`, THEN THE Versioning_CLI SHALL exit with a non-zero exit code and print a usage error message indicating the accepted values

### Requirement 6: Static Website Stack Fallback to package.json

**User Story:** As a developer, I want the Static_Website_Stack to read the version from `package.json` when `version.txt` is not present, so that versioning works without requiring an explicit build step that writes `version.txt`.

#### Acceptance Criteria

1. WHEN `version.txt` exists in the assets directory, THE Static_Website_Stack SHALL read the version from `version.txt` as the primary source
2. WHEN `version.txt` does not exist in the assets directory, THE Static_Website_Stack SHALL search for a `package.json` file by traversing parent directories starting from the assets directory, stopping when a `package.json` is found or the filesystem root is reached, up to a maximum of 10 parent directories
3. WHEN a `package.json` file is found containing a `"version"` field with a valid semver string (containing at least major and minor components), THE Static_Website_Stack SHALL use that version value
4. IF `package.json` is found but contains invalid JSON or does not contain a `"version"` field with a valid semver string, THEN THE Static_Website_Stack SHALL treat it as not found and use the default version `"0.0.1.cdk.factory"` and log a warning indicating the reason
5. IF neither `version.txt` nor a `package.json` with a valid `"version"` field can be found within the traversal limit, THEN THE Static_Website_Stack SHALL use the default version `"0.0.1.cdk.factory"` and log a warning

### Requirement 7: Integration with Existing Version_Builder

**User Story:** As a maintainer, I want the Versioning_CLI to reuse the existing Version_Builder class, so that version computation logic is not duplicated.

#### Acceptance Criteria

1. THE Versioning_CLI SHALL delegate git commit counting and tag-based build number computation to the Version_Builder class's `get_git_build_number` method
2. WHEN the `--version-source` argument is `package-json`, THE Versioning_CLI SHALL read the base version from `package.json` and pass the extracted major.minor value to Version_Builder's `get_git_build_number` method for patch number computation
3. WHEN the `--version-source` argument is `git-tag`, THE Versioning_CLI SHALL instantiate Version_Builder with `VersionSource.GIT_TAG` and delegate both base version resolution and build number computation to Version_Builder
4. THE Versioning_CLI SHALL NOT reimplement git tag parsing, commit counting, or `CODEBUILD_BUILD_NUMBER` fallback logic that already exists in Version_Builder
