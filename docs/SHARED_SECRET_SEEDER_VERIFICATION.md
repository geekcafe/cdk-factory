# SharedSecretSeeder — Verification (cdk-factory)

## What was added

- `src/cdk_factory/utilities/shared_secret_seeder.py` — a GENERIC post-deploy
  utility that fills a Secrets Manager secret (created by IaC with a placeholder)
  with a strong, randomly generated value exactly once.
  - Mirrors `appsync_key_seeder.py` exactly in structure, cross-account
    `_get_client` / `read_secret` helpers, never-log-value discipline, CLI/env
    contract, exit codes, and idempotency. Differs only in that it GENERATES a
    value (`secrets.token_urlsafe(32)`) instead of discovering an AppSync key.
  - Behavior:
    - secret missing/empty value OR equals placeholder (`REPLACE_ME`) -> generate + `put_secret_value`
    - secret already holds a real value -> NO-OP (never overwrites; not rotated on every deploy)
    - secret does not exist (`ResourceNotFoundException`) -> hard ERROR
      (`SecretNotFoundError`, a `RuntimeError` subclass). The IaC secrets stack is
      responsible for creating the secret with its placeholder; this seeder only
      fills a placeholder and never creates secrets.
  - Configurable `placeholder` (default `REPLACE_ME`) and `token_bytes`
    (default 32). CLI env: `SECRET_ID` (required), `AWS_REGION` (default
    `us-east-1`), optional `CROSS_ACCOUNT_ROLE_ARN`, optional
    `SECRET_PLACEHOLDER`. Invocable as
    `python -m cdk_factory.utilities.shared_secret_seeder` (exit 0 success,
    1 on error).
  - The generated value is NEVER logged (only secret-id + booleans).
  - No builtin `hash()` introduced; no synth-time live AWS calls (this is a
    post-deploy boto3 CLI, same as the appsync seeder).

- `tests/unit/test_shared_secret_seeder.py` — unit tests mirroring
  `test_appsync_key_seeder.py`'s mocking style
  (`@patch.object(SharedSecretSeeder, "_get_client")` + `MagicMock` +
  `botocore.exceptions.ClientError`; no moto, no live AWS).

## Test command + results

Run from the cdk-factory worktree
(`/Users/eric.wilson/Projects/geek-cafe/cdk-factory/.worktrees/shared-secret-seeder`):

```
python -m pytest tests/unit/test_shared_secret_seeder.py -v
```

Result: **9 passed** in ~0.34s. Coverage:

| Test | Asserts |
|---|---|
| `test_placeholder_generates_and_writes` | placeholder -> generates + writes; written != placeholder; len >= 32 |
| `test_empty_value_generates_and_writes` | empty value -> generates + writes |
| `test_none_value_generates_and_writes` | `SecretString` None -> generates + writes |
| `test_already_set_is_noop` | real value -> `put_secret_value` NOT called (no overwrite) |
| `test_missing_secret_raises` | missing secret -> `SecretNotFoundError`; no write |
| `test_custom_placeholder_is_honored` | configurable placeholder treated as needs-seeding |
| `test_custom_token_length` | larger `token_bytes` -> longer value |
| `test_generated_value_never_logged` | written value absent from all log records |
| `test_generate_values_are_random` | two generations differ (not a fixed constant) |

## Live effect

No live effect from this repo change. The seeder only runs as a deployed
pipeline post-deploy step (see geek-cafe-lambdas wiring). No AWS deploy or live
AWS call was performed here.

## IAM — FLAG (action needed before the geek-cafe-lambdas step will succeed)

The existing AppSync seeder step relies on the OPT-IN IAM block in
`src/cdk_factory/pipeline/security/policies.py` gated by
`pipeline.enable_appsync_key_seeder`. That block adds a `RealtimeApiKeySecretSeeder`
statement scoped **only** to:

```
arn:aws:secretsmanager:<region>:<account>:secret:realtime/appsync-events/api-key*
```

The shared CodeBuild role has **no other `secretsmanager:*` grant** (the default
policies grant `ssm:*`, `ecr`, `ec2`, `s3`, `codeartifact`, `sts` — but NOT
Secrets Manager). Therefore the new event-bus seeder step, which needs
`secretsmanager:GetSecretValue` + `secretsmanager:PutSecretValue` on
`event-bus/ingress/shared-secret*`, is **NOT covered** by any existing grant.

**This was intentionally NOT changed here** (broadening IAM is a behavior change
outside the additive-wiring scope). A scoped grant must be added before the
pipeline step can succeed. Recommended minimal, scoped options (pick one):

1. Extend the existing opt-in block in `policies.py` to also emit a statement for
   `event-bus/ingress/shared-secret*` (ideally behind its own opt-in flag, e.g.
   `enable_shared_secret_seeder`, to keep the default-off contract), **or**
2. Add a single scoped statement for
   `arn:aws:secretsmanager:<region>:<account>:secret:event-bus/ingress/shared-secret*`
   with only `secretsmanager:GetSecretValue` + `secretsmanager:PutSecretValue`.

Do NOT broaden to `secretsmanager:*` / `Resource: "*"`.
