# Deployment Stack Overrides — Future Feature Proposal

## Problem

The current config system uses flat `{{PLACEHOLDER}}` string substitution from `deployment.*.json` parameters into stack configs. This works well for simple values (account IDs, region, names) but breaks down when deployments need to control complex structures like arrays or nested objects in stack configs.

Example: one deployment needs two API Gateway custom domains, another needs one. The stack config (`api-gateway-primary.json`) is shared — you can't put an array in a `{{PLACEHOLDER}}`.

## Current Workaround

Comma-separated string parameters that the stack code splits at runtime:

```json
// deployment.beta.json
"API_DOMAIN_NAMES": "api.beta.example.com,v3.api.beta.example.com"

// api-gateway-primary.json
"custom_domain": {
  "domain_names": "{{API_DOMAIN_NAMES}}",
  "hosted_zone_name": "{{HOSTED_ZONE_NAME}}"
}
```

This works but is limited to flat lists of strings. It can't express per-item overrides (e.g., different certificates per domain).

## Proposed Solution: `stack_overrides`

Allow deployment configs to provide deep-merge overrides for specific stack config sections.

### Config Format

```json
// deployment.beta.json
{
  "parameters": { ... },
  "stack_overrides": {
    "api-gateway-primary": {
      "api_gateway.custom_domain": [
        {
          "domain_name": "api.{{HOSTED_ZONE_NAME}}",
          "hosted_zone_name": "{{HOSTED_ZONE_NAME}}"
        },
        {
          "domain_name": "v3.api.{{HOSTED_ZONE_NAME}}",
          "hosted_zone_name": "{{HOSTED_ZONE_NAME}}",
          "certificate_arn": "arn:aws:acm:..."
        }
      ]
    }
  }
}
```

```json
// deployment.prod.json — single domain, no override needed
{
  "parameters": { ... }
}
```

### How It Works

1. Stack configs are loaded and placeholders resolved as today
2. After resolution, check if the deployment has `stack_overrides` for this stack
3. For each override key (dot-notation path like `api_gateway.custom_domain`), deep-merge or replace the value at that path in the resolved stack config
4. Override values also go through placeholder resolution

### Key Design Decisions

- Override keys use dot-notation to target nested paths (`api_gateway.custom_domain`)
- Arrays replace entirely (no array merging — too complex and error-prone)
- Objects can be deep-merged or replaced (configurable per override with a `_merge: false` flag)
- Overrides are applied after `{{PLACEHOLDER}}` resolution so they can reference parameters
- Stack matching uses the stack name suffix (e.g., `api-gateway-primary` matches `workload-namespace-api-gateway-primary`)

### Implementation Location

- `CdkConfig.__resolved_config()` or a new post-resolution step
- New method: `_apply_stack_overrides(stack_config, deployment_config)`
- Called during stack config loading, after placeholder resolution

### Use Cases

- Per-deployment custom domain lists (API Gateway)
- Per-deployment CORS origins (different domains per environment)
- Per-deployment Lambda memory/timeout overrides
- Per-deployment feature flags (enable/disable stack sections)
- Per-deployment scaling configurations

### Migration Path

- Fully backward compatible — no `stack_overrides` means no change
- Existing comma-separated patterns continue to work
- Gradually migrate complex configs to overrides as needed
