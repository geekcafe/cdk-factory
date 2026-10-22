# Event Bus Infrastructure (generalized event ingress → spine → multi-lane delivery)

How cdk-factory provisions the infrastructure behind the **generalized event platform**: an
authenticated HTTP ingress that persists + publishes an event to an EventBridge spine, which fans out
per-lane — **AppSync Events realtime for ALL events**, plus **Slack + SNS for CRITICAL events**, with
a web monitor subscribing over AppSync Events.

This is the infra half. The application side (the `EventEnvelope`, `EventBusPublisher`,
`EventIngressService` + the HTTP ingress adapter, the Slack/SNS consumers, and the web client) lives
in the **`geek-cafe-saas-sdk`** repo — see [Companion SDK doc](#companion-sdk-doc).

This guide grew out of [`realtime-push-infrastructure.md`](realtime-push-infrastructure.md) (the
ChatOps realtime MVP). That doc is still the reference for the AppSync Events stack, the Lambda
authorizer wiring, and the EventBridge→SQS routing — all of which this platform **reuses**. This guide
adds the generic ingress + multi-lane + event-table stand-up and the from-scratch runbook, and
cross-links the hard-won gotchas now captured in sibling docs rather than restating them.

> **Scope note (mirrors the SDK design doc).** The in-scope consumers of this platform are
> **home-security** and **life-alerts**. **Aplos is an example DOWNSTREAM consumer that is OUT of
> scope** — it will consume geek-cafe event notices for its own purposes, but it is not part of the
> security / life-alert system. It is mentioned only to show the platform is generic.

The feature was first proven in the geek-cafe event-bus PoC; those identifiers are concrete examples.
Nothing in cdk-factory is app-specific.

---

## 1. What cdk-factory provisions

Every piece is an **existing** cdk-factory stack module — the event-bus PoC was wired with **no
`src/cdk_factory/` source changes** (see [event-bus-poc-VERIFICATION.md](event-bus-poc-VERIFICATION.md)).

```
Producer ─► HTTPS POST (shared secret) ─► API Gateway route (NONE auth + CORS/OPTIONS)
                                               │  allow_public_override: true
                                               ▼
                                        ingress Lambda  ──►  DynamoDB event table (forensic row)
                                               │
                                               ▼  one put_events PER lane
                                     EventBridge "default" bus
                                               │  rules keyed on detail.delivery_lane
              ┌────────────────────────────────┼────────────────────────────────┐
              ▼ "realtime" (ALL)                ▼ "slack" (critical)              ▼ "sns" (critical)
        SQS (+DLQ)                         SQS (+DLQ)                        SQS (+DLQ, dedicated critical queue)
              ▼                                  ▼                                  ▼
     realtime consumer λ                 event_bus Slack consumer λ        event_bus SNS consumer λ
              ▼  HTTP POST (x-api-key)                                              ▼  sns:Publish
     AppSync Events API                                                       SNS topic
       • CfnApi + EventConfig
       • CfnChannelNamespace "channels"   ◄── alphanumeric + hyphen, NO underscore (synth-guarded)
       • Lambda authorizer (Cognito JWT; REALTIME_CHANNEL_NAMESPACE allowlist)
              ▼  pushes the event
     Browser web monitor subscribed on /channels/{tenant}/...
```

| Piece | Module | Produces |
|---|---|---|
| AppSync Events API + channel namespace(s) + authorizer invoke grant | `appsync_events_stack` | `AWS::AppSync::Api`, one `AWS::AppSync::ChannelNamespace` per namespace, the AppSync→authorizer `AWS::Lambda::Permission` |
| EventBridge rule → SQS routing (one per lane) | `eventbridge_stack` | `AWS::Events::Rule` + `AWS::SQS::QueuePolicy` per lane |
| Per-lane SQS queues + DLQ (incl. a dedicated **critical** queue) | `simple_queue_service` / `sqs_stack` | queues + redrive |
| Critical-event SNS topic | `sns_stack` | `AWS::SNS::Topic` |
| Ingress Lambda (public HTTP) + SQS-trigger consumer Lambdas | `lambda_stack` (`api_gateway` route + `sqs` trigger) | functions, route integration, event-source mappings |
| Ingress shared secret (placeholder) | `secrets_manager` | the secret the seeder later fills |
| Forensic event table | `dynamodb_stack` | the DynamoDB table the ingress writes the `Event` row to |
| Cognito app-client id → SSM (for `/app/config`) | `cognito_stack` | app-client id + user-pool SSM exports |
| Post-deploy shared-secret seeder IAM (opt-in) | pipeline `shared_secret_seeder_secrets` | CodeBuild role statement for the seeder step |

The authorizer Lambda, the ingress Lambda, and the consumer Lambdas are ordinary `lambda_stack`
functions in the consuming repo; cdk-factory does not ship their code.

---

## 2. The pieces (config, with cross-links not re-explanations)

### 2.1 AppSync Events API + the `channels` namespace

Use `appsync_events_stack` exactly as [`realtime-push-infrastructure.md` → `appsync_events_stack`](realtime-push-infrastructure.md#appsync_events_stack)
documents it (config keys, exported SSM triplet, `auth.providers` collision fix). The platform
differences from the ChatOps example:

- `channel_namespaces` includes **`channels`** (the event-bus web-monitor namespace). The ChatOps
  `inboxes` namespace can live on the SAME API; both are just entries in `channel_namespaces`.
- **Namespace name constraint (synth-guarded).** `AWS::AppSync::ChannelNamespace` names must be
  **1–50 chars, alphanumeric + hyphen, start/end alphanumeric — NO underscore**. `appsync_events_stack`
  validates this at **synth** (`_CHANNEL_NAMESPACE_NAME_PATTERN` in
  `src/cdk_factory/stack_library/appsync_events/appsync_events_stack.py`) and fails fast with a clear
  message, so a name like `event_bus` can't reach CloudFormation and blow up as a CREATE_FAILED
  rollback in a pipeline. This is why the namespace is `channels`, not `event_bus`. The guard is
  documented in full in [`realtime-push-infrastructure.md`](realtime-push-infrastructure.md) and the
  source above — **cross-linked, not re-explained here**.

### 2.2 The multi-namespace authorizer env (`REALTIME_CHANNEL_NAMESPACE`)

The authorizer Lambda is a normal `lambda_stack` function configured by env vars (so the SDK
authorizer stays generic). For a shared API that serves both ChatOps and the event bus, the namespace
env is a **comma-separated allowlist**:

```json
[
    { "name": "REALTIME_USER_POOL_ID",
      "ssm_parameter": "/{{WORKLOAD_NAME}}/{{ENVIRONMENT}}/cognito/user-pool/user-pool-id" },
    { "name": "REALTIME_CHANNEL_NAMESPACE", "value": "inboxes,channels" },
    { "name": "REALTIME_CROSS_TENANT_ROLES",
      "value": "platform_admin,support_admin,support_staff,admin" }
]
```

`REALTIME_CHANNEL_NAMESPACE` must include **every** registered namespace the authorizer should accept
(it gates the channel's first path segment against the set). If `channels` is missing from the
allowlist, every `/channels/...` subscribe is denied even though connect succeeds. The authorizer
accepts either a comma-separated string (as above) or a single value; the SDK default is `inboxes`.
See [the companion SDK doc §7](#companion-sdk-doc) for the scope invariant.

### 2.3 The per-lane EventBridge → SQS fan-out

Use `eventbridge_stack` as in
[`realtime-push-infrastructure.md` → `eventbridge_stack`](realtime-push-infrastructure.md#eventbridge_stack),
one rule per lane, keyed on `detail.delivery_lane` (the generalized discriminator; the ingress also
writes the `platform` read-alias so legacy `detail.platform` rules keep working). The event-bus spine
publishes with `Source=geekcafe.event_bus` and `DetailType=Event` (config-driven on the SDK publisher),
so the rules match on those plus the lane:

```jsonc
"event_pattern": {
  "source": ["geekcafe.event_bus"],
  "detail-type": ["Event"],
  "detail": { "delivery_lane": ["realtime"] }   // one rule each: realtime / slack / sns
}
```

`eventbridge_stack` is **SQS-target-only**; that is exactly the shape used here (per-lane SQS → consumer
gives per-branch DLQ/retry/batch control). A direct rule→SNS/Lambda target is a deferred hardening
optimization, not on the critical path — see [event-bus-poc-VERIFICATION.md](event-bus-poc-VERIFICATION.md).

Each lane gets its own SQS queue + DLQ (`simple_queue_service` / `sqs_stack`). Per DESIGN §12.I, the
**critical** lane uses a **dedicated queue** so a CI/CD or bulk flood cannot head-of-line-block a
life-alert (SQS has no intra-queue priority ordering — a separate queue is the only real mechanism).

### 2.4 The SNS topic

`sns_stack` provisions the critical-event SNS topic. The event_bus SNS consumer Lambda reads the topic
ARN from `EVENT_BUS_SNS_TOPIC_ARN` (set from the topic's SSM export at deploy time) and calls
`sns:Publish`. Grant the consumer `sns:Publish` on the topic via its `lambda_stack` permissions block.

### 2.5 The ingress Lambda + API Gateway route (NONE auth + CORS + `allow_public_override`)

The ingress is a **public** route — producers (devices, CI) authenticate with the shared secret in the
body, not with Cognito. On the `api_gateway_stack` route:

- `"authorization_type": "NONE"` (public).
- `"allow_public_override": true` — **required**. cdk-factory refuses to synth a `NONE` route when a
  Cognito authorizer is available on the API, to prevent *accidental* public endpoints
  (`api_gateway_integration_utility.py` raises a "SECURITY CONFLICT DETECTED" `ValueError`). Setting
  `allow_public_override: true` is the explicit, reviewed opt-in that this endpoint is public by design.
- **CORS / OPTIONS must be configured on the route** so a browser preflight succeeds (the web UI test
  page and any browser producer send an `OPTIONS` preflight before the `POST`). Enable CORS on the
  route (methods incl. `OPTIONS`, the `content-type` header, and the allowed origin). A missing OPTIONS
  method / CORS config surfaces as a browser CORS error even though `curl` works.

The ingress function's env carries the shared-secret source (`EVENT_BUS_SHARED_SECRET_ID` → the
Secrets Manager secret id, preferred; or `EVENT_BUS_SHARED_SECRET` for local/dev) and the event table
name. See the SDK doc §4 for the resolution precedence.

### 2.6 The DynamoDB event table

`dynamodb_stack` provisions the forensic event table the ingress writes each `Event` row to (primary
`event#{id}`; a tenant GSI `tenant#{tenantId}` / `created#{ts}` for newest-first listing). The ingress
Lambda needs read/write on it; the write is best-effort (a table hiccup does not block delivery).

---

## 3. The SSM export/import agreement (the mismatch that broke the deploy)

The event-bus ingress is an **API Gateway route backed by a Lambda in a lambda stack** — the exact
cross-stack shape that is cdk-factory's #1 deployment footgun. The lambda stack **exports** each
function ARN at `/{lambda_stack.ssm.namespace}/{lambda_name}/arn`; the API Gateway stack **reads**
`/{api_gateway.ssm.imports.namespace}/{lambda_name}/arn`. **These two namespaces must be identical.**

If the ingress lambda stack uses a suffixed namespace its API-routed siblings don't (e.g.
`.../lambda/event_bus` or `.../event_bus` instead of the shared flat `.../lambda` namespace the API
Gateway imports), the API Gateway auto-discovery builds a path that was never written and the API
Gateway stack's **`prepare` phase fails at synth** with `Unable to fetch parameters [...] from
parameter store` — even though the Lambda deployed fine and its ARN *is* in SSM, just under a
different path.

**The rule:** every lambda stack that backs routes on the same API Gateway shares ONE flat
`ssm.namespace`, and the API Gateway's `ssm.imports.namespace` equals it exactly. Fix the exporter;
don't paper over it with a per-route `lambda_arn_ssm_path`. This is documented in full — including the
clean export→import rules and why renaming replaces (not orphans) the parameter — in
[Naming & SSM](naming-and-ssm.md) (its "Export/import path agreement — the #1 cross-stack deployment
footgun" section) and [SSM Parameter Naming Convention](ssm-parameter-naming-convention.md).
**Cross-linked, not duplicated.**

---

## 4. The shared-secret seeder (post-deploy) + its opt-in IAM grant

The ingress shared secret is created by the `secrets_manager` stack with a **`REPLACE_ME`
placeholder** (secrets are never hardcoded in IaC). A post-deploy step fills it with a strong random
value exactly once — mirroring the AppSync api-key seeder.

- **Seeder:** `python -m cdk_factory.utilities.shared_secret_seeder`. Behavior
  (see [SHARED_SECRET_SEEDER_VERIFICATION.md](SHARED_SECRET_SEEDER_VERIFICATION.md)): if the secret is
  missing/empty or equals the placeholder (`REPLACE_ME`) → generate (`secrets.token_urlsafe(32)`) +
  `put_secret_value`; if it already holds a real value → NO-OP (never overwrites, not rotated every
  deploy); if the secret resource does not exist → hard error (the `secrets_manager` stack owns
  creation). The generated value is **never logged**. CLI env: `SECRET_ID` (required), `AWS_REGION`,
  optional `CROSS_ACCOUNT_ROLE_ARN`, optional `SECRET_PLACEHOLDER`.
- **Opt-in IAM grant:** add the secret name/pattern to the pipeline config's
  **`shared_secret_seeder_secrets`** list (e.g. `["event-bus/ingress/shared-secret*"]`). The
  **presence of patterns IS the opt-in** (mirroring `enable_appsync_key_seeder`, but generic and
  multi-secret). When non-empty, `src/cdk_factory/pipeline/security/policies.py` adds a single
  `SharedSecretSeeder` statement granting only `secretsmanager:GetSecretValue` +
  `secretsmanager:PutSecretValue`, scoped to the expanded ARN
  `arn:aws:secretsmanager:{region}:{account}:secret:{pattern}` (the trailing `*` covers the Secrets
  Manager random suffix). Default empty = OFF; never broaden to `secretsmanager:*` / `Resource:"*"`.

> The AppSync publish api-key has its own analogous seeder + opt-in flag (`enable_appsync_key_seeder`)
> — see [`realtime-push-infrastructure.md` → AppSync key post-deploy automation](realtime-push-infrastructure.md#appsync-key-post-deploy-automation).
> The shared-secret seeder is the ingress-auth analogue of that pattern.

---

## 5. Implementing in a new project — RUNBOOK

A from-scratch stand-up, in dependency order. Each step calls out the gotcha that bites **at that
step** so you don't re-hit the walls the PoC did. Deploy each as its own pipeline stage (so adding or
removing one never perturbs another's CloudFormation stack identity — see the `__imports__` guardrail
in [Naming & SSM](naming-and-ssm.md)).

1. **Deploy SSM-exported prerequisites + the secret placeholder.**
   - Cognito (`cognito_stack`) exporting the user-pool id + app-client id to SSM (top-level `ssm`
     block — a nested one silently disables export; see
     [`realtime-push-infrastructure.md` → Cognito clientId SSM export](realtime-push-infrastructure.md#cognito-clientid-ssm-export)).
   - The `secrets_manager` secret for the ingress shared secret, created with the **`REPLACE_ME`**
     placeholder.
   - The DynamoDB event table (`dynamodb_stack`) and the SNS topic (`sns_stack`).

2. **Deploy the lambdas using the FLAT SSM namespace that API-routed lambdas require.**
   Ingress + consumer + authorizer functions via `lambda_stack`.
   - **⚠️ Gotcha — SSM export/import agreement.** The lambda stack that backs the ingress **route**
     must export function ARNs to the **same flat `ssm.namespace`** the API Gateway stack imports from
     (step 4). A suffixed namespace (`.../lambda/event_bus`, `.../event_bus`) makes the API Gateway's
     `prepare` phase fail at synth with `Unable to fetch parameters`. Align the exporter — don't patch
     with per-route `lambda_arn_ssm_path`. (§3; [Naming & SSM](naming-and-ssm.md).)

3. **Deploy the AppSync Events namespaces + the authorizer allowlist.**
   `appsync_events_stack` with `channel_namespaces` including **`channels`**; point its
   `authorizer_lambda_arn_ssm_path` at the authorizer from step 2.
   - **⚠️ Gotcha — namespace name: alphanumeric + hyphen, NO underscore.** Use `channels`, never
     `event_bus`. The synth guard rejects underscores before CloudFormation can CREATE_FAILED-rollback
     the stack (§2.1).
   - **⚠️ Gotcha — authorizer allowlist must include the new namespace.** Set the authorizer's
     `REALTIME_CHANNEL_NAMESPACE` to the comma-separated allowlist that contains `channels` (e.g.
     `inboxes,channels`). Otherwise every `/channels/...` subscribe is denied (§2.2).
   - (If AppSync had both Cognito and Lambda providers, drop Cognito via the `auth` block — see the
     connect-400 provider-collision gotcha in
     [`realtime-push-infrastructure.md`](realtime-push-infrastructure.md#cognito--lambda-provider-collision-connect-400-ambiguous-jwt).)

4. **Deploy the API Gateway route with CORS/OPTIONS.**
   The public ingress route via `api_gateway_stack`.
   - **⚠️ Gotcha — the route must be public, intentionally.** `"authorization_type": "NONE"` **plus**
     `"allow_public_override": true` (cdk-factory refuses a bare `NONE` route when a Cognito authorizer
     is present — a safety check). (§2.5)
   - **⚠️ Gotcha — CORS/OPTIONS on the route.** Configure CORS (incl. the `OPTIONS` method, the
     `content-type` header, allowed origin) so the browser preflight succeeds; `curl` working is not
     enough. (§2.5)
   - **⚠️ Gotcha — import namespace must equal step 2's export namespace.** The route's
     `ssm.imports.namespace` must match the lambda stack's flat `ssm.namespace` exactly (§3).

5. **Deploy the per-lane EventBridge rules + SQS queues, then run the shared-secret seeder post-deploy
   step.**
   - `eventbridge_stack` rules keyed on `detail.delivery_lane` (`realtime` / `slack` / `sns`) → per-lane
     SQS (+DLQ), with a **dedicated critical queue** (§2.3). Wire each consumer's `sqs` trigger and the
     SNS consumer's `sns:Publish` grant.
   - Run `python -m cdk_factory.utilities.shared_secret_seeder` as a post-deploy step, with the
     pipeline opted-in via **`shared_secret_seeder_secrets: ["event-bus/ingress/shared-secret*"]`** (§4).
   - **⚠️ Gotcha — the shared secret AUTO-SEEDS on first deploy.** After this step the secret holds a
     generated value, NOT `REPLACE_ME`. **Test scripts and producers must send the generated value**
     (read it from Secrets Manager), or the ingress returns `403 EVENT_BUS_UNAUTHORIZED`. The web UI
     works precisely because it uses the real seeded value; a stale script still sending `REPLACE_ME`
     (or an old value) will 403.

6. **Configure the web monitor.**
   Point the browser at the AppSync Events endpoint / api-id / region (exported to
   `/{ssm.namespace}/{name}/{api-id,http-endpoint,realtime-endpoint}`) and the Cognito client id (from
   `/app/config`), then subscribe on the `channels` namespace via the SDK's `useRealtimeChannel`
   composable. The whole feature should ship behind an off-by-default feature flag; rollback is flipping
   it off. See the [companion SDK doc](#companion-sdk-doc).

---

## 6. Verification

What was spot-checked this documentation pass (every concrete identifier below was grepped/read in
real source, not guessed). Items that could not be confirmed are marked **UNVERIFIED**.

**cdk-factory (this repo) — confirmed in source:**
- Channel-namespace synth guard `_CHANNEL_NAMESPACE_NAME_PATTERN =
  ^[A-Za-z0-9](?:[A-Za-z0-9-]{0,48}[A-Za-z0-9])?$` and the "no underscores" validation message —
  `src/cdk_factory/stack_library/appsync_events/appsync_events_stack.py`
  (`_validate_namespace_names`).
- `allow_public_override` route key — `src/cdk_factory/configurations/resources/apigateway_route_config.py`;
  the "SECURITY CONFLICT DETECTED" `NONE`-without-override guard —
  `src/cdk_factory/utilities/api_gateway_integration_utility.py`.
- `shared_secret_seeder_secrets` opt-in list + the `SharedSecretSeeder` IAM statement (scoped Get/Put
  on the pattern ARN, never `*`) — `src/cdk_factory/configurations/pipeline.py`,
  `src/cdk_factory/pipeline/security/policies.py`; the `enable_appsync_key_seeder` sibling confirmed in
  the same files.
- SSM export/import agreement rule — [naming-and-ssm.md](naming-and-ssm.md); point-in-time PoC records
  [event-bus-poc-VERIFICATION.md](event-bus-poc-VERIFICATION.md) and
  [SHARED_SECRET_SEEDER_VERIFICATION.md](SHARED_SECRET_SEEDER_VERIFICATION.md).

**geek-cafe-saas-sdk — confirmed in source:**
- `EventEnvelope` / `build_event_envelope` / `validate_envelope`, lanes `realtime|slack|sns`
  (`EVENT_BUS_ALLOWED_LANES` widen), priorities incl. `critical`, `Source=geekcafe.event_bus` /
  `DetailType=Event` on `EventBusPublisher` — `modules/event_bus/models/event_envelope.py`,
  `modules/event_bus/services/publisher.py`.
- `EventIngressService` + `HttpEventIngressAdapter` (shared-secret auth, tenant from body/`x-tenant-id`),
  the ingress `handlers/ingress/app.py` secret precedence + `EVENT_BUS_UNAUTHORIZED`, the Slack/SNS
  consumers (`EVENT_BUS_SNS_TOPIC_ARN`) — `modules/event_bus/...`.
- Multi-namespace authorizer: `REALTIME_CHANNEL_NAMESPACE` comma-separated allowlist,
  `DEFAULT_CHANNEL_NAMESPACE="inboxes"`, `channels` as a second namespace —
  `modules/notifications/realtime/authorizer.py`.
- Web monitor subscribe (AppSync Events, `authMode:'lambda'`, leading-slash strip) —
  `geek-cafe-web/geek-cafe-web-app/composables/useRealtimeChannel.ts`.

**UNVERIFIED (carried from the SDK design doc, confirm before relying):**
- The exact AppSync `EVENT_SUBSCRIBE` channel field — `RealtimeAuthorizer._extract_channels` still
  reads it defensively (`TODO(phase-2-capture)`); the subscribe-scope contract is working-but-defensive.
- Whether a direct EventBridge rule→Lambda (off an existing domain-event rule) is possible — the design
  uses the SQS-fronted default to avoid depending on it.
- Runtime/deployment state of any specific tenant's stacks (static source read only, no live AWS call).

No build is required (docs-only change).

---

## Companion SDK doc

The application/publisher/client side is documented in the **`geek-cafe-saas-sdk`** repo:
[`geek-cafe-saas-sdk` → `docs/realtime/EVENT_BUS_PLATFORM.md`](../../geek-cafe-saas-sdk/docs/realtime/EVENT_BUS_PLATFORM.md)
(the generalized platform), with [`docs/realtime/REALTIME_PUSH_NOTIFICATIONS.md`](../../geek-cafe-saas-sdk/docs/realtime/REALTIME_PUSH_NOTIFICATIONS.md)
as the realtime-transport/authorizer reference it reuses.

---

## Related cdk-factory docs

- [Realtime Push Infrastructure](realtime-push-infrastructure.md) — the ChatOps realtime MVP infra this platform reuses (AppSync Events stack, authorizer invoke grant, EventBridge→SQS, api-key seeder). Full channel-namespace guard + provider-collision write-ups live here.
- [Naming & SSM](naming-and-ssm.md) — the export/import path-agreement rule (§3) and the `__imports__` rename guardrail.
- [SSM Parameter Naming Convention](ssm-parameter-naming-convention.md) — parameter path structure + the API Gateway constraint.
- [event-bus-poc-VERIFICATION.md](event-bus-poc-VERIFICATION.md) — point-in-time PoC verification (no cdk-factory source change; modules reused).
- [SHARED_SECRET_SEEDER_VERIFICATION.md](SHARED_SECRET_SEEDER_VERIFICATION.md) — point-in-time seeder verification + the IAM opt-in.
- [Stack Modules](stack-modules.md) · [Lambda Permissions](lambda-permissions.md) · [API Gateway + Cognito SSM](API_GATEWAY_COGNITO_SSM.md).
