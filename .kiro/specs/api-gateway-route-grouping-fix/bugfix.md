# Bugfix Requirements Document

## Introduction

The API Gateway nested stack auto-grouping mechanism fails to distribute routes across multiple nested stacks. All routes accumulate in a single "default" nested stack, exceeding CloudFormation's 500-resource limit and causing deployment failures. The root cause is a placeholder mismatch: `_build_lambda_folder_cache()` stores raw unresolved placeholder names from disk (e.g., `"{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-asset-handler"`) while `_discover_routes_from_dependencies()` provides fully resolved names (e.g., `"asset-workbench-dev-asset-handler"`). The cache lookup always misses, returning an empty string, which routes everything to the "default" group.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN auto-grouping is active (no explicit `nested_stacks.grouping` configured) AND Lambda resource configs on disk contain placeholder names like `"{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-asset-handler"` THEN the system stores these raw unresolved names as keys in the lambda folder cache

1.2 WHEN `_resolve_lambda_folder()` is called with a resolved lambda name (e.g., `"asset-workbench-dev-asset-handler"`) THEN the system fails to find a match in the cache and returns an empty string

1.3 WHEN the folder resolution returns an empty string for all routes THEN the system assigns every route to the "default" group, producing a single nested stack that exceeds CloudFormation's 500-resource limit

### Expected Behavior (Correct)

2.1 WHEN auto-grouping is active AND Lambda resource configs on disk contain placeholder names THEN the system SHALL resolve placeholders in the `name` field using the workload's parameter values before storing them in the lambda folder cache

2.2 WHEN `_resolve_lambda_folder()` is called with a resolved lambda name THEN the system SHALL find the correct match in the cache and return the relative folder path (e.g., `"assets"`, `"admin"`, `"categories"`)

2.3 WHEN folder resolution succeeds for routes across multiple resource subdirectories THEN the system SHALL distribute routes into separate nested stacks per folder, each well within CloudFormation's resource limits

### Unchanged Behavior (Regression Prevention)

3.1 WHEN explicit `nested_stacks.grouping` is configured in the API Gateway config THEN the system SHALL CONTINUE TO use the explicit grouping map to assign routes to named groups

3.2 WHEN `nested_stacks.enabled` is false or absent THEN the system SHALL CONTINUE TO create all routes in the main stack without nested stacks

3.3 WHEN a Lambda resource config does not contain an `api` section THEN the system SHALL CONTINUE TO skip that resource during route discovery

3.4 WHEN a Lambda resource config's folder cannot be determined (resource not found on disk) THEN the system SHALL CONTINUE TO assign that route to the "default" group as a fallback

3.5 WHEN a Lambda resource config contains a `route_group` field in its `api` section THEN the system SHALL use that value as the group name, bypassing folder resolution entirely

---

## Bug Condition

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type RouteGroupingInput
  OUTPUT: boolean
  
  // Returns true when auto-grouping is active and disk configs have unresolved placeholders
  RETURN X.nested_stacks.enabled = true
     AND X.nested_stacks.grouping IS EMPTY
     AND X.lambda_resource_configs_on_disk CONTAIN placeholder tokens (e.g., "{{WORKLOAD_NAME}}")
END FUNCTION
```

## Property Specification

```pascal
// Property: Fix Checking — Placeholder Resolution in Cache
FOR ALL X WHERE isBugCondition(X) DO
  cache ← buildLambdaFolderCache'(X)
  FOR ALL resolved_name IN X.discovered_route_lambda_names DO
    folder ← cache.get(resolved_name)
    ASSERT folder ≠ "" 
       AND folder = relative_path_of_resource_on_disk(resolved_name)
  END FOR
END FOR
```

## Preservation Goal

```pascal
// Property: Preservation Checking — Non-buggy inputs unchanged
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT groupRoutes(X) = groupRoutes'(X)
END FOR
```

This ensures that explicit grouping, disabled nested stacks, and resources without API sections all behave identically before and after the fix.
