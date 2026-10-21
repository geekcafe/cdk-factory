# Realtime Push Infrastructure (AppSync Events)

How cdk-factory provisions the infrastructure behind **realtime push notifications** — a managed
WebSocket-style pub/sub channel that pushes "something changed" signals to a browser while the tab is
open. This is the infra half of the feature. The application side (the publisher Lambda, the channel
grammar, the Vue client, the authorizer business logic) lives in the `geek-cafe-saas-sdk` repo — see
[Companion SDK doc](#companion-sdk-doc).

The feature was first proven end-to-end in the geek-cafe Message Center (contact-thread triage). Those
identifiers are used below as concrete examples; nothing in cdk-factory is app-specific.

---

## Overview

The transport is **AWS AppSync Events** (a managed WebSocket pub/sub service with a channel-namespace
primitive) gated by a **Lambda authorizer** that reuses the same Cognito User Pool JWT the REST API
already uses. cdk-factory provides two net-new stack modules plus the SSM/IAM wiring the chain depends
on:

```
Domain event ─► EventBridge rule (detail.platform = "realtime")  ◄── eventbridge_stack
                     │
                     ▼
                 SQS queue  ─►  realtime-publisher Lambda  (app/SDK side)
                                     │  HTTP POST (x-api-key) to the Events endpoint
                                     ▼
                              AppSync Events API            ◄── appsync_events_stack
                               • CfnApi + EventConfig
                               • CfnChannelNamespace ("inboxes")
                               • Lambda authorizer (connect + subscribe scoping)
                                     │  pushes {event, tenantId, inboxId, threadId}
                                     ▼
                              Browser subscribed to its channel (Cognito JWT auth)
                                     │  push the signal → pull the detail via REST
                                     ▼
                              UI updates live, no refresh
```

Two independent identities authenticate to the API, and the infra provisions for both:

- **Browser subscribers** connect/subscribe with the **Cognito login JWT** (same User Pool as REST),
  validated by the Lambda authorizer.
- **The backend publisher** publishes with an **API key** read from a Secrets Manager secret
  (`realtime/appsync-events/api-key`). The key is created and seeded by an opt-in post-deploy pipeline
  step (see [AppSync key post-deploy automation](#appsync-key-post-deploy-automation)).

### What cdk-factory provisions

| Piece | Module | Produces |
|---|---|---|
| AppSync Events API + channel namespace(s) + authorizer invoke grant | `appsync_events_stack` | `AWS::AppSync::Api` (`CfnApi` + `EventConfig`), one `AWS::AppSync::ChannelNamespace` per namespace, an `AWS::Lambda::Permission` for AppSync→authorizer invoke |
| EventBridge rule → SQS routing | `eventbridge_stack` | `AWS::Events::Rule` + `AWS::SQS::QueuePolicy` granting the rule `sqs:SendMessage` |
| Cognito app-client id → SSM (for `/app/config`) | `cognito_stack` | `AWS::Cognito::UserPoolClient` + SSM exports (user-pool id/arn/name, app-client id) |
| Post-deploy api-key seeder IAM (opt-in) | pipeline `enable_appsync_key_seeder` flag | CodeBuild role statements for the seeder step |

The authorizer Lambda and the realtime-publisher Lambda themselves are ordinary `lambda_stack`
functions in the consuming repo; cdk-factory does not ship their code.

---

## Enabling realtime infra via cdk-factory config

Realtime is composed from standalone stack configs, each in its own pipeline stage (so adding or
removing one never perturbs another's CloudFormation stack identity — see
[the `__imports__` footgun](#ssm-export-conflict--imports-stack-name-footgun)). The established stage
order (from the realtime runbook) is:

```
deploy-realtime-secrets      SecretsManager secret placeholder for the publish api-key
deploy-realtime-queue        SQS queue + DLQ (realtime publish lane)
deploy-realtime-lambdas      Cognito authorizer λ + realtime-publisher consumer λ (lambda_stack)
deploy-realtime-appsync      AppSync Events API + namespace "inboxes"        (appsync_events_stack)
seed-realtime-appsync-key    post-deploy: create + seed the publish api-key  (opt-in)
deploy-realtime-eventbridge  EventBridge rule, detail.platform = "realtime"  (eventbridge_stack)
```

### `appsync_events_stack`

Module `appsync_events_stack`. The `appsync_events` block configures a single Events API, its channel
namespaces, and its auth providers. Real config (geek-cafe):

```json
{
    "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-realtime-appsync-events",
    "module": "appsync_events_stack",
    "enabled": true,
    "appsync_events": {
        "name": "realtime",
        "user_pool_id_ssm_path": "/{{WORKLOAD_NAME}}/{{ENVIRONMENT}}/cognito/user-pool/user-pool-id",
        "authorizer_lambda_arn_ssm_path": "/{{WORKLOAD_NAME}}/{{ENVIRONMENT}}/realtime/authorizer/arn",
        "authorizer_result_ttl_seconds": 300,
        "api_key_publish": true,
        "auth": {
            "providers": ["lambda", "api_key"],
            "connection_auth_modes": ["lambda"],
            "subscribe_auth_modes": ["lambda"],
            "publish_auth_modes": ["api_key"]
        },
        "channel_namespaces": ["inboxes"],
        "ssm": {
            "namespace": "{{WORKLOAD_NAME}}/{{ENVIRONMENT}}/appsync-events"
        }
    }
}
```

Config keys (from `AppSyncEventsConfig`):

| Key | Required | Meaning |
|---|---|---|
| `name` | yes | Logical API name; also the deterministic construct-id seed and the SSM export leaf. |
| `user_pool_id_ssm_path` | yes | SSM path to the Cognito user-pool id. Resolved at **deploy time** as a CloudFormation token (`ssm.StringParameter.value_for_string_parameter`) — never a literal, never a live boto3 call at synth. Synth fails if omitted. |
| `authorizer_lambda_arn_ssm_path` | yes | SSM path to the authorizer Lambda ARN (deploy-time token). Synth fails if omitted. |
| `authorizer_result_ttl_seconds` | no (300) | Authorizer result cache TTL. |
| `api_key_publish` | no (`true`) | Register the `API_KEY` publish provider so the server-side publisher can POST. |
| `auth.providers` | no | Ordered friendly tokens — `lambda`, `cognito`, `api_key`. When **absent**, the stack inherits the legacy set `[cognito, lambda]` (+ `api_key` when `api_key_publish`). When present, exactly those providers are emitted in order. geek-cafe uses `["lambda", "api_key"]` (Cognito deliberately dropped — see the gotcha below). |
| `auth.connection_auth_modes` / `subscribe_auth_modes` / `publish_auth_modes` | no | Friendly-token overrides for connect / default-subscribe / default-publish modes. Absent → defaults (`AWS_LAMBDA` for connect/subscribe; `API_KEY` or `AWS_LAMBDA` for publish depending on `api_key_publish`). |
| `channel_namespaces` | no | One `CfnChannelNamespace` per entry. A plain string is the namespace name; an object may also set per-namespace `publish_auth_modes` / `subscribe_auth_modes`. AppSync requires the **first** channel-path segment to be a literal, pre-registered namespace — here `inboxes`. Duplicate names fail synth. |
| `ssm.namespace` | no | SSM export prefix. Falls back to `/{workload}/{environment}/appsync-events`. |

The stack exports three parameters the downstream publisher and the browser client consume:

```
/{ssm.namespace}/{name}/api-id              e.g. /geekcafe/prod/appsync-events/realtime/api-id
/{ssm.namespace}/{name}/http-endpoint       the publish (HTTP POST) endpoint
/{ssm.namespace}/{name}/realtime-endpoint   the subscribe (WebSocket) endpoint
```

### `eventbridge_stack`

Module `eventbridge_stack`. Adds a rule on the existing chatops EventBridge spine that fans a domain
event out to the realtime SQS queue when `detail.platform = "realtime"` — a second delivery branch
beside the existing Slack branch, driven by the **same** domain event. The target queue is imported by
ARN from SSM (deploy-time token); because the imported queue is immutable, the stack also attaches an
`AWS::SQS::QueuePolicy` granting `events.amazonaws.com` `sqs:SendMessage`, scoped to the rule ARN via
`aws:SourceArn`. Real config (geek-cafe):

```json
{
    "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-realtime-eventbridge",
    "module": "eventbridge_stack",
    "enabled": true,
    "event_bridge_rules": [
        {
            "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-realtime-publish-rule",
            "event_bus_name": "default",
            "event_pattern": {
                "source": ["geekcafe.chatops"],
                "detail-type": ["ChatOpsMessage"],
                "detail": { "platform": ["realtime"] }
            },
            "target_queue_ssm_path": "/realtime/{{ENVIRONMENT}}/sqs/{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-realtime-publish/arn"
        }
    ]
}
```

Per-rule keys: `name` (also the construct-id seed — slugged, so a second rule can never collide on
ids), `event_bus_name` (`default` or a named bus), `event_pattern` (`source` / `detail-type` /
`detail`), and `target_queue_ssm_path` (required). `event_pattern` and `target_queue_ssm_path` are
each required or synth fails.

### Authorizer Lambda configuration (consumer side)

The authorizer is a normal `lambda_stack` function whose behavior is injected by env vars, so the SDK
authorizer stays generic (no app role names baked in). The real env block:

```json
[
    { "name": "REALTIME_USER_POOL_ID",
      "ssm_parameter": "/{{WORKLOAD_NAME}}/{{ENVIRONMENT}}/cognito/user-pool/user-pool-id" },
    { "name": "REALTIME_CHANNEL_NAMESPACE", "value": "inboxes" },
    { "name": "REALTIME_CROSS_TENANT_ROLES",
      "value": "platform_admin,support_admin,support_staff,admin" }
]
```

- `REALTIME_USER_POOL_ID` drives JWKS/issuer validation (resolved from SSM as a deploy-time token).
- `REALTIME_CHANNEL_NAMESPACE` must equal the AppSync channel namespace (`inboxes`) — the authorizer
  rejects any channel whose leading segment is not this literal.
- `REALTIME_CROSS_TENANT_ROLES` is the concrete app role list that opens the platform lane; the SDK
  hardcodes none of these.

### Naming & SSM conventions

All SSM paths above follow cdk-factory's conventions. See [Naming & SSM](naming-and-ssm.md) and
[SSM Parameter Naming Convention](ssm-parameter-naming-convention.md). Note the hard rule that an
`ssm` block is a **top-level** peer of `name`/`module` — misplacing it (nesting under the resource
block) silently disables export (this is exactly what broke the Cognito client-id export; see
[gotchas](#cognito-clientid-ssm-export)). For wiring `/app/config` and the Cognito app-client id
through the API Gateway, see [API Gateway + Cognito SSM](API_GATEWAY_COGNITO_SSM.md).

---

## Authorizer invoke permission & tenant-isolation scoping

### The AppSync → authorizer invoke permission

The raw L1 `CfnApi` (unlike the L2 `appsync.Api`) does **not** auto-grant AppSync permission to invoke
the Lambda authorizer. `appsync_events_stack` emits the grant explicitly, and only when an `AWS_LAMBDA`
provider is actually configured:

```python
_lambda.CfnPermission(
    self,
    f"{base}-authorizer-invoke-permission",
    action="lambda:InvokeFunction",
    function_name=authorizer_fn_arn,          # deploy-time SSM token (ARN-only, no IFunction)
    principal="appsync.amazonaws.com",
    source_arn=self.api.attr_api_arn,         # the BARE API ARN — see below
)
```

The `source_arn` is the **bare** API ARN (`arn:aws:appsync:{region}:{account}:apis/{apiId}`), **not**
a `{apiId}/*` glob. This was confirmed empirically on the live stack: AppSync Events invokes the
authorizer with `SourceArn` equal to the bare API ARN, so a resource policy scoped to `.../apis/{id}/*`
matches nothing, AppSync is denied, the authorizer is never invoked, and `connection_init` fails with
`400 BadRequestException`. Granting on the bare ARN moved the live error from 400 → 401 (AppSync now
invokes the authorizer, which then makes its own allow/deny decision). Both ARNs are deploy-time
CloudFormation tokens, so nothing is resolved at synth and no account/region/apiId is hardcoded.

### Tenant-isolation scoping (where it lives)

Tenant isolation is enforced by the **authorizer Lambda's own logic** (SDK side), not by IAM. The
infra's job is only to (a) wire the authorizer as the connect/subscribe auth provider and grant AppSync
the invoke permission above, and (b) feed it the right env (`REALTIME_USER_POOL_ID`,
`REALTIME_CHANNEL_NAMESPACE`, `REALTIME_CROSS_TENANT_ROLES`). Given that wiring, the authorizer:

- validates the Cognito idToken, then
- splits the requested channel and enforces that `segments[0]` equals the literal namespace
  (`inboxes`), the tenant segment equals the token's `tenant_id`, and any `users/{userId}` segment
  equals the token's `user_id` — so an authenticated user of tenant A **cannot** subscribe to tenant
  B's channel.

The `platform` lane (`/inboxes/platform/...`) is opened by the `REALTIME_CROSS_TENANT_ROLES` roles (in
addition to a platform-tenant token). This is deliberately app-configured, not baked into the SDK.
Full authorizer behavior, the channel grammar, and the staged RBAC roadmap are documented SDK-side —
see the `appsync-authorizer-invoke-permission` and `realtime-authorizer-tenant-isolation-findings`
notes referenced in the [companion SDK doc](#companion-sdk-doc).

---

## Learnings / gotchas (infra)

Each of the following was a real failure peeled off during the realtime work. Symptom → cause → fix.

### AppSync → authorizer invoke permission (connect 400)

- **Symptom:** every `connection_init` returns `400 BadRequestException`; the authorizer Lambda shows
  **zero** invocations and zero logs.
- **Cause:** the L1 `CfnApi` does not auto-grant AppSync `lambda:InvokeFunction` on the authorizer, and
  — the subtle part — AppSync Events invokes with `SourceArn` = the **bare** API ARN, so a grant scoped
  to `.../apis/{id}/*` never matches.
- **Fix:** `appsync_events_stack` emits an `AWS::Lambda::Permission` with
  `principal="appsync.amazonaws.com"` and `source_arn=self.api.attr_api_arn` (bare ARN), only when an
  `AWS_LAMBDA` provider is configured. Live error moved 400 → 401 once the bare-ARN grant landed.

### AppSync api-key seeder ARN fix (`resources=["*"]`)

- **Symptom:** the `seed-realtime-appsync-key` post-deploy step fails with
  `is not authorized to perform: appsync:ListApiKeys` — even after the operator confirmed the
  `AppSyncEventsApiKeySeeder` statement is present on the running CodeBuild role.
- **Cause:** `appsync:ListApiKeys` / `CreateApiKey` / `GetApiKey` have an **empty resource-type column**
  in the AWS Service Authorization Reference — they are not resource-scopable, so the only `Resource`
  that matches them is `"*"`. The grant had scoped them to `arn:aws:appsync:{region}:{account}:apis/*`,
  which matches nothing for these actions (the Events api-key resource IAM actually evaluates is
  `.../v1/apis/{apiId}/apikeys`). IAM's generic "no identity-based policy allows the action" denial is
  the same text for *absent* and *present-but-non-matching* statements.
- **Fix:** set the `AppSyncEventsApiKeySeeder` statement `resources=["*"]` (the Secrets Manager
  statement, `.../secret:realtime/appsync-events/api-key*`, is correctly resource-scoped and unchanged).
  This supersedes an earlier (wrong) diagnosis that blamed self-mutate propagation timing and claimed
  `apis/*` was correct.

### SSM export conflict / `__imports__` stack-name footgun

- **Symptom:** a lambdas deploy fails with ~27 `already exists` errors on SSM parameters
  (`/{ns}/{lambda}/arn`, `/function-name`).
- **Cause:** appending a 4th named file to a multi-file `__imports__` **list** renamed the merged
  CloudFormation stack. cdk-factory merges `__imports__` scalar keys by *override, last-file-wins*, and
  the merged `name` is used verbatim as both the construct id and the physical `stack_name`. A changed
  `stack_name` is a *new* stack, which tries to CREATE SSM params whose fixed physical names the old
  (still-live) stack already owns. This is distinct from the prior `stable_id` fix, which stabilized
  **stage** construct ids, not **stack** names — a genuine coverage gap.
- **Fix / safe-authoring rule:** never append/reorder/remove a named file in a multi-file `__imports__`
  list. Add new lambdas either as `resources[]` **inside** an already-imported file (merged by extend,
  name unchanged) or as their **own stage** via a single-file `__inherits__` — which is exactly why the
  realtime stacks (and `app-config`) are each isolated stages. Optionally pin the merged name with an
  explicit `"name"` sibling of `__imports__`. See [Naming & SSM](naming-and-ssm.md) guardrails.

### Cognito clientId SSM export

- **Symptom:** `/app/config` returns an empty `userPoolClientId` (and no app-client / user-pool
  parameters export at all) — the browser then cannot build a Cognito auth config to connect.
- **Cause:** the geek-cafe cognito stack placed its `ssm` block **nested inside** `cognito`
  (`cognito.ssm`). `cognito_stack` (and `StackConfig`) read the `ssm` block only at the **stack top
  level**, so `auto_export` resolved false and the export loop early-returned. (A second, historical
  factor: an old installed `cdk-factory 0.8.0` had no app-client support at all.)
- **Fix:** add a **top-level** `ssm` block (`auto_export: true` + a `namespace`) as a sibling of
  `cognito`. With no per-client `ssm_namespace`, the id exports at the pool-fallback key
  `/{ns}/app-client-{client-name}-id`; adding a per-client `ssm_namespace` changes it to
  `/{client-ns}/client-id`. Pick whichever path the app-config Lambda's `COGNITO_*_SSM` env var reads
  so write and read paths agree. See [API Gateway + Cognito SSM](API_GATEWAY_COGNITO_SSM.md).

### Cognito + Lambda provider collision (connect 400, ambiguous JWT)

- **Symptom:** connect 400s while the API has **both** Cognito and Lambda auth providers and the client
  sends a bare Cognito JWT.
- **Cause:** with both providers registered, a bare JWT is ambiguous to AppSync.
- **Fix:** the `appsync_events_stack` auth providers are config-driven; geek-cafe sets
  `auth.providers = ["lambda", "api_key"]` (Cognito dropped) so connect/subscribe go through the Lambda
  authorizer and publish through the api-key. This is why the `auth` block exists — the legacy default
  would otherwise register `[cognito, lambda]`.

### cdk-nag wildcard assessment

- **Question:** does the seeder's `resources=["*"]` trigger a cdk-nag `AwsSolutions-IAM5` finding or
  fail synth?
- **Answer:** no. cdk-nag (`AwsSolutionsChecks`) is applied only via `StackBase` / `NestedStackBase`,
  never globally. The seeder statement lives on the pipeline's CodeBuild role inside
  `PipelineFactoryStack` (an `IStack`, never nag-scoped), the same un-nagged scope as the long-standing
  `SSMPolicy` (`ssm:*` on `*`) and sibling `ec2:*` / `s3:*` / `ecr:*` wildcards. **No suppression is
  needed** — it matches the existing precedent exactly. (If the pipeline stack were ever migrated to
  `StackBase`, *all* of these wildcards would need matching IAM5 suppressions.)

### AppSync key post-deploy automation

- **Symptom:** after `deploy-realtime-appsync`, there is no API key to publish with — the
  `deploy-realtime-secrets` secret still holds its `REPLACE_ME` placeholder, and registering an
  `API_KEY` auth *provider* does **not** create an `AWS::AppSync::ApiKey` (a separate resource).
- **Cause:** the key must be created and written into the secret out-of-band; the API doesn't exist at
  secret-creation time, and secrets are never hardcoded in IaC.
- **Fix:** the `seed-realtime-appsync-key` post-deploy step runs
  `python -m cdk_factory.utilities.appsync_key_seeder`: it resolves the api-id from SSM
  (`/{workload}/{env}/appsync-events/realtime/api-id`), creates a ~1-year key if none is usable, and
  writes it into `realtime/appsync-events/api-key` only when it differs (idempotent and
  rotation-self-healing; the key value is never logged). IAM for this step is opt-in via the pipeline
  flag `enable_appsync_key_seeder` (default **off** in cdk-factory; the consumer sets it `true`). The
  module exists only in a published cdk-factory that contains it, so the consumer must pick up that
  release before this stage can run.

### Seeder IAM not attached (self-mutate timing) — superseded

- An earlier diagnosis attributed the first `appsync:ListApiKeys` denial to CDK Pipelines self-mutate
  **timing** (the brand-new `AppSyncEventsApiKeySeeder` statement not yet propagated onto the executing
  CodeBuild role, while the grandfathered `SSMPolicy` worked) and concluded a re-run would fix it with
  no ARN change. The operator later confirmed the statement **was** present on the running role and the
  step still failed — so the real root cause is the non-matching ARN above (fix: `resources=["*"]`),
  not propagation timing. Noted here because both reports exist in the task history.

---

## Deploy / QA pointer

The full operator + QA procedure is the realtime **Deployment & QA Runbook** (SDK task folder). The
infra-relevant highlights:

1. **Publish cdk-factory first.** The lambda pipeline installs cdk-factory from the package registry
   (CodeArtifact), not the local tree. A stale version means the realtime stacks won't synth and the
   `seed-realtime-appsync-key` module won't exist. (The same publish also carries the Lambda-packaging
   size fix that keeps the synth artifact under the CodePipeline S3 artifact limit.)
2. **Deploy stages in order** (secrets → queue → lambdas → appsync → seed-key → eventbridge). Pushing
   the branch triggers the pipeline; stacks with no template diff no-op — so a lambdas-only change does
   not disturb the AppSync stack's invoke permission, but a cdk-factory bump that re-synths the AppSync
   stack **will** reconcile it.
3. **Confirm the api-key seed.** The `seed-realtime-appsync-key` stage should be green and the
   `realtime/appsync-events/api-key` secret should hold a real `da2-…`-style key, not `REPLACE_ME`
   (`aws secretsmanager get-secret-value ...` / `aws appsync list-api-keys --api-id <id>`).
4. **Point the web app at the exports** and flip the feature flag. The browser reads the AppSync Events
   endpoint / api-id / region (exported to `/{ns}/{name}/{api-id,http-endpoint,realtime-endpoint}`) and
   the Cognito client id (from `/app/config`). The whole feature ships behind an off-by-default
   `realtimeEnabled` flag; rollback is flipping it off.

QA validates: a WebSocket connection opens and stays open; a new thread/reply appears live without
refresh; reconnect catches up missed changes; and — the security check — **tenant isolation holds**
(tenant A never sees tenant B's activity).

---

## Companion SDK doc

This doc covers only the cdk-factory infrastructure. The application/publisher/client side — the
`RealtimeEventsPublisher`, the `RealtimeAuthorizer` logic, the channel grammar, the `useRealtimeChannel`
Vue composable, and the `@log_lambda_event` observability decorator — is documented in the
**`geek-cafe-saas-sdk`** repo (the Branch 1 deliverable), under its `docs/` tree (the events/realtime
area, alongside `docs/events/EVENTS_DOMAIN.md`). Consult that doc for anything above the AppSync Events
API boundary; consult this one for how the API, the authorizer wiring, the EventBridge→SQS routing, and
the SSM/IAM glue are provisioned.

---

## Related cdk-factory docs

- [Naming & SSM](naming-and-ssm.md) — stack naming, the top-level `ssm` block, the `__imports__` rename guardrail.
- [SSM Parameter Naming Convention](ssm-parameter-naming-convention.md) — parameter path structure.
- [API Gateway + Cognito SSM](API_GATEWAY_COGNITO_SSM.md) — importing the Cognito pool/client id and wiring `/app/config`.
- [Stack Modules](stack-modules.md) — per-module config reference.
- [Lambda Permissions](lambda-permissions.md) — Lambda resource permission blocks.
- [Cross-Account](cross-account.md) — multi-account / SSM import nuances.
