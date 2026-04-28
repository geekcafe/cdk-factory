# Bugfix Requirements Document

## Introduction

The Docker Version Locker's `--seed` and `--list` modes fail to discover the `app-configurations` lambda because `run-lock-versions.sh` sets `CONFIG_DIR` to `cdk/configs/stacks/lambdas/resources/`, while `app-configurations` is defined inside `lambda-app-settings.json` at the parent directory (`cdk/configs/stacks/lambdas/`). This results in `app-configurations` being missing from the locked versions output and the `--list` mapping summary.

### DRY Analysis

The user raised a valid concern about whether `scan_config_directory()` in `docker_version_locker.py` duplicates logic already present in the CDK synth pipeline (`LambdaFunctionConfig` + `DockerConfig` + `ECRConfig`). After analysis, the current separation is justified:

- **`scan_config_directory()` + `_extract_docker_entry()`** is a lightweight offline scanner that reads JSON files and extracts `{name, tag, ecr}` tuples. It has no runtime dependencies — no `DeploymentConfig`, no CDK context, no template variable resolution. It runs in a developer's terminal or CI before deployment.
- **`LambdaFunctionConfig` / `DockerConfig` / `ECRConfig`** are CDK synth-time classes tightly coupled to `DeploymentConfig` for name resolution (e.g., `{{WORKLOAD_NAME}}` placeholders), IAM role setup, and CDK construct creation. They cannot be used outside a CDK synth context.

The `_extract_docker_entry()` static method is a simple ~10-line dict key check — not a complex reimplementation. Extracting it into a shared utility would create a coupling between the offline CLI tool and the CDK synth pipeline with no practical benefit. The real bug is the shell script passing the wrong directory path, not a code architecture issue.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN `run-lock-versions.sh` is invoked with `--seed` THEN the system passes `--config-dir` as `${CDK_DIR}/configs/stacks/lambdas/resources` which excludes stack-level JSON files (like `lambda-app-settings.json`) in the parent `lambdas/` directory

1.2 WHEN `run-lock-versions.sh` is invoked with `--list` THEN the system passes `--config-dir` as `${CDK_DIR}/configs/stacks/lambdas/resources` which excludes stack-level JSON files from the mapping summary

1.3 WHEN `scan_config_directory()` runs with `config_dir` set to `lambdas/resources/` THEN the system never reads `lambda-app-settings.json` (which lives in `lambdas/`) and the `app-configurations` Docker lambda is missing from the discovered entries

1.4 WHEN the locked versions file is generated after a `--seed` scan THEN the system produces output that is missing the `app-configurations` entry, so its Docker image version is never pinned

### Expected Behavior (Correct)

2.1 WHEN `run-lock-versions.sh` is invoked with `--seed` THEN the system SHALL pass `--config-dir` as `${CDK_DIR}/configs/stacks/lambdas` so that both stack-level files and resource subdirectory files are included in the scan

2.2 WHEN `run-lock-versions.sh` is invoked with `--list` THEN the system SHALL pass `--config-dir` as `${CDK_DIR}/configs/stacks/lambdas` so that both stack-level files and resource subdirectory files are included in the mapping summary

2.3 WHEN `scan_config_directory()` runs with `config_dir` set to `lambdas/` THEN the system SHALL discover `app-configurations` from `lambda-app-settings.json` via its `resources` array, alongside all individual resource files in subdirectories

2.4 WHEN the locked versions file is generated after a `--seed` scan THEN the system SHALL include an entry for `app-configurations` with its ECR repository (`acme-systems/v3/acme-saas-core-services`) and resolved version tag

### Unchanged Behavior (Regression Prevention)

3.1 WHEN `scan_config_directory()` scans a directory containing individual resource JSON files (e.g., `resources/tenants/get-tenant.json`) THEN the system SHALL CONTINUE TO discover those Docker lambdas and include them in the seed output

3.2 WHEN `scan_config_directory()` encounters non-Docker JSON files (files without `"docker": {"image": true}`) THEN the system SHALL CONTINUE TO skip them without error

3.3 WHEN `scan_config_directory()` encounters stack-level JSON files with a `resources` array containing a mix of Docker and non-Docker entries THEN the system SHALL CONTINUE TO extract only the Docker lambda entries

3.4 WHEN existing entries in the locked versions file have non-empty tags THEN the system SHALL CONTINUE TO preserve those pinned versions during seed merge and not overwrite them

3.5 WHEN `run-lock-versions.sh` is invoked with `--apply` THEN the system SHALL CONTINUE TO apply locked versions to the specified deployment without being affected by the `CONFIG_DIR` change

---

### Bug Condition

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type ShellScriptInvocation (script path + arguments + CONFIG_DIR value)
  OUTPUT: boolean
  
  // Returns true when the shell script's CONFIG_DIR points to a subdirectory
  // that excludes stack-level config files containing Docker lambda definitions
  RETURN X.CONFIG_DIR = "${CDK_DIR}/configs/stacks/lambdas/resources"
    AND EXISTS file IN parent_directory(X.CONFIG_DIR) WHERE
      file.contains_resources_array = true
      AND any_resource_in(file).is_docker_lambda = true
    AND X.mode IN {"--seed", "--list"}
END FUNCTION
```

### Fix Checking Property

```pascal
// Property: Fix Checking — CONFIG_DIR includes parent directory
FOR ALL X WHERE isBugCondition(X) DO
  X' ← X with CONFIG_DIR = "${CDK_DIR}/configs/stacks/lambdas"
  result ← scan_config_directory(X'.CONFIG_DIR)
  ASSERT "app-configurations" IN result.discovered_names
  ASSERT result.entry("app-configurations").ecr = "acme-systems/v3/acme-saas-core-services"
END FOR
```

### Preservation Property

```pascal
// Property: Preservation Checking — existing resource subdirectory lambdas still discovered
FOR ALL X WHERE NOT isBugCondition(X) DO
  // All lambdas previously discovered under lambdas/resources/ are still discovered
  // when scanning from the parent lambdas/ directory (since os.walk is recursive)
  ASSERT scan_config_directory("lambdas/") ⊇ scan_config_directory("lambdas/resources/")
END FOR
```
