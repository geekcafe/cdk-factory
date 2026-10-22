# VERIFICATION — shared-secret seeder IAM grant (cdk-factory)

## What changed

Added a GENERIC, opt-in IAM grant on the shared pipeline CodeBuild role for the
generic shared-secret seeder post-deploy step
(`cdk_factory.utilities.shared_secret_seeder`), mirroring the AppSync key
seeder's opt-in block.

1. `src/cdk_factory/configurations/pipeline.py`
   - New property `shared_secret_seeder_secrets` → `self.pipeline.get("shared_secret_seeder_secrets", [])`.
   - Single-list shape: a list of Secrets Manager secret name/ARN patterns the
     seeder may read/write. Empty default = OFF (no grant). Presence of patterns
     IS the opt-in (parallel to `enable_appsync_key_seeder`, but generic/multi-secret).

2. `src/cdk_factory/pipeline/security/policies.py`
   - After the AppSync seeder block, append ONE `iam.PolicyStatement`
     (sid `SharedSecretSeeder`) ONLY when `shared_secret_seeder_secrets` is non-empty.
   - Actions: `secretsmanager:GetSecretValue` + `secretsmanager:PutSecretValue` (Get+Put only).
   - Resources: each configured pattern expanded to a full ARN
     `arn:aws:secretsmanager:{workload.devops.region}:{workload.devops.account}:secret:{pattern}`.
     So `event-bus/ingress/shared-secret*` → the correctly-scoped ARN (trailing `*`
     covers the Secrets Manager random suffix). NEVER `*`. No appsync actions.
   - Default OFF: no statement appended when the list is empty/absent.

3. Tests
   - `tests/unit/test_pipeline_config.py`: added `test_shared_secret_seeder_secrets_default_empty`
     and `test_shared_secret_seeder_secrets_configured`.
   - `tests/unit/test_shared_secret_seeder_policy.py` (new): asserts the statement
     is ABSENT with list unset and with empty list (default-off), PRESENT and
     scoped (Get+Put only, configured ARN, not `*`) when configured, and that
     multiple patterns each become their own scoped ARN.
   - Synthesis is CDK-only (no live boto3 / AWS calls during synth — honors
     no-live-aws-calls). No builtin `hash()` used for construct ids
     (honors deterministic-construct-ids).

## Commands run & results

```
cd /Users/eric.wilson/Projects/geek-cafe/cdk-factory/.worktrees/shared-secret-seeder-iam
python -m pytest tests/ -k 'policy or pipeline or seeder' -q
  => 154 passed, 1 skipped, 1280 deselected

python -m pytest tests/unit/test_shared_secret_seeder_policy.py \
                 tests/unit/test_appsync_key_seeder_policy.py \
                 tests/unit/test_pipeline_config.py
  => 12 passed
```

## Result

Grant appears ONLY when `shared_secret_seeder_secrets` is configured; it is
Secrets-Manager-only with Get+Put only; scoped to the configured pattern ARN(s),
never `*`. All relevant tests pass.
