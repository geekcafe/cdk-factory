# Enable CodePipeline Monitoring (self-contained: CodePipeline/CodeBuild → Slack + SNS)

How cdk-factory turns AWS **CodePipeline** (and optional **CodeBuild**) execution state changes into
direct **Slack** (bot token + `chat.postMessage`) and **SNS** (email) notifications — with **no shared
event_bus spine**, **no adapter Lambda**, and **no `geek-cafe-saas-sdk` dependency**. This is the
`codepipeline_notifier_stack` module: a single stack that owns the whole self-contained graph, so the
monitor is a **reusable, per-customer** deployment unit.

> **Spine variant.** If you are already running the geek-cafe `event_bus` spine and want CodePipeline
> events to flow through *it* (fanning out via the existing Slack/SNS/realtime lanes), use the
> original `codepipeline_monitor_stack` + the SDK adapter handler instead — see
> [§7 The spine variant](#7-the-spine-variant-codepipeline_monitor_stack). Everything else in this doc
> describes the **self-contained** `codepipeline_notifier_stack`.

> **Scope.** v1 is **same account only** (`867915409343` / `us-east-1` / profile `geekcafe`).
> Cross-account monitoring is OUT of scope. git / package-publish / deploy are **user-managed**; this
> guide describes the stand-up, it does not run it.

---

## 1. What this provisions

```
AWS CodePipeline / CodeBuild
  └─ emits a native state-change event ─► EventBridge "default" bus
        (source=aws.codepipeline | aws.codebuild)
                                              │
                                 events.Rule (built by codepipeline_notifier_stack)
                                   • event_pattern keyed on source + detail-type + detail.state
                                   • target = OWNED notifier Lambda (packaged by this stack)
                                   • auto AWS::Lambda::Permission (events.amazonaws.com → the rule ARN)
                                              ▼  invoke
                                   notifier Lambda  (handler + notify/ packaged from the project's src)
                                   • _map_event(): one normalized MonitorNotice
                                   • deliver-gate (priority) BEFORE routing
                                   • resolve routing: pipeline_routes[name] ∪ {central}
                                              ▼
                        ┌──────────────── per channel ─────────────────┐
                        ▼                                               ▼
              Slack chat.postMessage                         SNS Publish (per-channel topic)
              (bot token from Secrets Manager)               (email subscriptions)
```

| Piece | Produced by `codepipeline_notifier_stack` |
|---|---|
| per-channel SNS topics + one email `Subscription` per address | `AWS::SNS::Topic` + `AWS::SNS::Subscription` |
| the CodePipeline (and optional CodeBuild) rule → **owned** notifier Lambda | `AWS::Events::Rule` + auto `AWS::Lambda::Permission` (scoped to the rule ARN) |
| the **owned** notifier Lambda (code packaged from the project's `src`) | `AWS::Lambda::Function` + its role |
| scoped IAM on the function role (`GetSecretValue` on the bot-token secret, `sns:Publish` on exactly the created topics) | `AWS::IAM::Policy` (never `*`) |
| rule / topic / lambda ARN SSM exports | `AWS::SSM::Parameter` (fallback literal `codepipeline-notifier`) |

Unlike the spine variant, this module **creates the notifier Lambda itself** (it does not import a
Lambda by ARN), and delivery is direct — there is no second hop through a shared bus.

---

## 2. The two stacks (config)

A self-contained deploy is **two ordered stages** (plus an optional post-deploy assertion):

### 2.1 The bot-token secret — a `secrets_manager_stack` config

```jsonc
{
  "module": "secrets_manager_stack",
  "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-codepipeline-notifier-secrets",
  "enabled": true,
  "secrets": [
    { "name": "codepipeline-notifier/slack/bot-token",
      "description": "Slack bot token (xoxb-...) read by the notifier Lambda; seed the real value out-of-band.",
      "placeholder": "REPLACE_ME",
      "removal_policy": "RETAIN" }
  ]
}
```

Ordered **first** so the secret exists before the notifier stage's Lambda role references it by ARN
name-pattern. The real token is pasted **out-of-band** once after deploy (§6.3).

### 2.2 The notifier — a `codepipeline_notifier_stack` config

```jsonc
{
  "module": "codepipeline_notifier_stack",
  "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-codepipeline-notifier",
  "enabled": true,
  "ssm": { "namespace": "{{WORKLOAD_NAME}}/{{ENVIRONMENT}}/codepipeline-notifier" },
  "codepipeline_notifier": {
    "pipelines": {
      "mode": "all",                 // "none" | "all" | "selected"
      "names": [],                   // used only when mode == "selected"
      "exclude_names": [             // mode == "all" only — self-exclude the monitor's own pipeline
        "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-devops-monitoring-pipeline"
      ]
    },
    "slack_bot_token_secret_name": "codepipeline-notifier/slack/bot-token",
    "channels": {
      "central":   { "slack_channel_id": "C0CENTRAL000", "sns_emails": ["devops-oncall@example.com"] },
      "team-web":  { "slack_channel_id": "C0WEBTEAM000", "sns_emails": ["web-team@example.com"] },
      "team-data": { "slack_channel_id": "C0DATATEAM00", "sns_emails": [] }   // Slack-only
    },
    "central": "central",
    "pipeline_routes": {
      "web-app-prod-pipeline": ["team-web"],
      "etl-prod-pipeline":     ["team-data"]
    },
    "state_priority_map": { "FAILED": "critical", "SUCCEEDED": "normal",
                            "CANCELED": "normal", "SUPERSEDED": "normal" },
    "deliver_priorities": ["critical"],
    "codebuild": { "enabled": false,
                   "detail_types": ["CodeBuild Build State Change"],
                   "build_status_priority_map": { "FAILED": "critical" } },
    "approval_rejection": { "enabled": false, "subscribe_action_execution": false,
                            "treat_as": "distinct_event" },
    "lambda": {
      "src": "./src/devops_monitoring_lambdas",                       // PACKAGE root (so notify/ is bundled)
      "handler": "handlers.codepipeline_notifier.app.lambda_handler", // AWS dotted path inside that root
      "runtime": "python3.11", "timeout": 30, "memory_size": 256,
      "include_power_tools_layer": true                              // powertools via managed layer
    },
    "console_base_url": "https://{region}.console.aws.amazon.com"
  }
}
```

**Validation (fail synth):** `mode` ∈ `{none,all,selected}`; `central` is a key in `channels`; every
`pipeline_routes` channel is a key in `channels`; every channel has a `slack_channel_id` OR ≥1
`sns_emails`; priorities ∈ `{critical,normal}`; `slack_bot_token_secret_name` non-empty if any channel
uses Slack.

**The three pipeline-selection modes:**

| `pipelines.mode` | Rule behavior |
|---|---|
| `none` (or stack `enabled: false`) | The stack builds **zero** resources. Monitors nothing. |
| `all` | One rule with **no** `detail.pipeline` filter → every pipeline. With `exclude_names`, adds `detail.pipeline = [{ "anything-but": [<exclude_names>] }]` (self-exclude the monitor's own pipeline). |
| `selected` | `detail.pipeline` = the configured `names` list → only those pipelines. |

---

## 3. Config → Lambda env (the module builds the wire format)

The customer never hand-writes env vars. The **module** creates the per-channel SNS topics, then zips
the channel list with the created topic ARNs + each channel's `slack_channel_id` into the handler env.
Scalars are plain strings; maps/lists are JSON-encoded strings the handler `json.loads` back.
Present-but-malformed is a **fatal cold-start error**.

| Env var | Wire type | Meaning |
|---|---|---|
| `MONITOR_CENTRAL_CHANNEL` | scalar | channel that gets every delivered in-scope notice |
| `MONITOR_CHANNELS` | JSON object | `name → {slack_channel_id, sns_topic_arn}` (ARNs are deploy-time tokens) |
| `MONITOR_SLACK_BOT_TOKEN_SECRET_ID` | scalar | secret id holding the bot token |
| `MONITOR_STATE_PRIORITY_MAP` | JSON object | `state → priority` (default `{"FAILED":"critical"}`) |
| `MONITOR_BUILD_STATUS_PRIORITY_MAP` | JSON object | `build-status → priority` |
| `MONITOR_DELIVER_PRIORITIES` | JSON array | priorities that actually deliver (default `["critical"]`) |
| `MONITOR_PIPELINE_ROUTES` | JSON object | `pipeline → [channel,...]` (central always added) |
| `MONITOR_APPROVAL_REJECTION` | JSON object | `{enabled, treat_as}` (off by default) |
| `MONITOR_CONSOLE_BASE_URL` | scalar | console URL template |

---

## 4. Routing semantics

- **Deliver-gate runs BEFORE routing.** `should_deliver(notice) = notice.priority ∈ deliver_priorities`.
  A below-threshold notice reaches **no** channel — not even `central`.
- **central is always added.** Resolved channels = `pipeline_routes.get(name, []) ∪ {central}`.
- **Value-dedup, but distinct topics are NOT collapsed.** Two channel *names* that resolve to the same
  Slack id / topic ARN collapse; distinct `central` + team topic ARNs do **not** — the intentional
  double-publish that gives both the central overview and the team its own copy.

---

## 5. The two usage modes

### 5.1 Centralized — the `geek-cafe-devops-monitoring` project (recommended)

A **standalone DevOps project** owns the monitor on its own independent pipeline (three ordered stages:
secrets → notifier → assertion; see that repo's README). `mode: all` + self-exclude gives an
account-wide central overview without the monitor paging itself.

### 5.2 Drop into an individual project's pipeline

The **same single notifier stack** (+ its secret stage) drops into an individual project's pipeline to
monitor **only that pipeline** (`mode: "selected"`, `names: ["<that-pipeline>"]`). No adapter, no spine,
no SDK.

---

## 6. Gotchas (the walls to not re-hit)

### 6.1 Role finalization ordering (load-bearing)

`LambdaFunctionUtilities.create` freezes the role via `role.without_policy_updates()`. A statement
added to the role **after** `create()` silently does **not** attach — the Lambda synths and deploys
clean but fails every delivery at runtime with `AccessDenied`. The module's build order is therefore
fixed: **create SNS topics (so `topic.topic_arn` tokens exist) → fully populate the role with all
statements → create the Lambda.**

### 6.2 Scoped IAM, never `*`

The function role gets `secretsmanager:GetSecretValue` on
`arn:aws:secretsmanager:<region>:<account>:secret:<secret-name>*` (trailing `*` for the random suffix,
never `*`), `sns:Publish` on **exactly** the created topic ARNs (never `*`, never `topic/*`), and Logs
on its own group. The rule → Lambda invoke is an auto `AWS::Lambda::Permission` scoped to the **rule
ARN** (owned function → `add_target` adds it; no hand-rolled `CfnPermission`).

### 6.3 Seeding the Slack bot token (operator-supplied, not generated)

The token is an externally-issued credential, so the pipeline never *generates* it (that would clobber
it). Seed it out-of-band once:

```bash
aws secretsmanager put-secret-value \
  --secret-id codepipeline-notifier/slack/bot-token \
  --secret-string 'xoxb-REAL-TOKEN'
```

The pipeline reuses the `SharedSecretSeeder` **pattern** (placeholder secret + opt-in scoped IAM via
the pipeline's `shared_secret_seeder_secrets`) but **not** the generate-a-value CLI. What the pipeline
*does* automate is a read-only **token-present assertion** (`GetSecretValue` only) that fails the
pipeline if the secret is still `REPLACE_ME`.

> **Stage-ordering accuracy.** The role's `GetSecretValue` grant is an ARN **name-pattern** grant, so
> it **synthesizes and deploys even if the secret stage ran out of order or the secret is unseeded** —
> IAM name-pattern grants don't require the resource to exist. So mis-ordering does **not** fail at
> synth; it fails at runtime (or silently never pages). The **post-deploy assertion is the guard** that
> makes an unseeded/missing token a loud failure — do not rely on synth to catch it.

Also: `chat.postMessage` only succeeds in channels the bot is a **member** of — invite the bot to each
configured channel, or posts return `not_in_channel` (logged, not retried). And because `central` and
a team channel are distinct SNS topics, an operator subscribed to **both** email lists gets **two**
emails for a team-routed failure (intentional; tell operators to pick one).

### 6.4 No builtin `hash()` / no live boto3 at synth

Construct IDs are explicit slugged strings (`re.sub(r"[^a-zA-Z0-9]+","-", name).strip("-").lower()`);
builtin `hash()` is randomized per process (`PYTHONHASHSEED`) so it churns logical IDs between synths
(`hashlib` if a suffix is ever needed). A guard test asserts no builtin `hash()`
(`tests/unit/test_no_builtin_hash_in_codepipeline_notifier.py`). No live boto3 / `value_from_lookup` at
synth — topic ARNs and the like are CloudFormation tokens, keeping `cdk synth` credential-free.

### 6.5 Lambda asset root (so `notify/` is bundled)

`lambda.src` is the **package root** `./src/devops_monitoring_lambdas` (NOT the handler sub-dir), and
`lambda.handler` is the dotted `handlers.codepipeline_notifier.app.lambda_handler`. The packaging helper
computes `relative_path.replace("/" + handler, "")`; because the dotted handler is never a
`/`-substring of the src path, the whole package — both `handlers/` and the sibling `notify/` — is the
`copytree` source. An asset-root test pins this.

---

## 7. The spine variant (`codepipeline_monitor_stack`)

The original `codepipeline_monitor_stack` still exists for the **event_bus spine** use case: it builds
the EventBridge rule(s) and targets an **adapter Lambda imported by ARN** (handler in
`geek-cafe-saas-sdk`, `modules/event_bus/handlers/codepipeline_adapter/app.py`) that publishes
`EventEnvelope`s onto the shared bus for the existing lanes to deliver. Use it only when you are already
running the spine. It is unchanged by the self-contained work; its config shape and the adapter env
contract are documented inline in that module and in
[event-bus-infrastructure.md](event-bus-infrastructure.md).

---

## 8. Verification

The `codepipeline_notifier_stack` module ships credential-free unit tests (pure CDK synth assertions;
run with `SKIP_PIP=1` so the Lambda asset build does not pip-install):

```bash
cd /Users/eric.wilson/Projects/geek-cafe/cdk-factory && SKIP_PIP=1 pytest tests/unit/test_codepipeline_notifier_stack.py
```

They assert: `mode all`/`all`+exclude (self-exclude name present in the `anything-but` list) / `selected`
/ `none`; zero resources when disabled; N channels-with-emails → N topics + correct subscription count;
the owned Lambda's auto scoped `AWS::Lambda::Permission`; the function role scoped for `GetSecretValue`
+ `sns:Publish` (not `*`); the CodeBuild rule when enabled; `MONITOR_CHANNELS` carrying the created
topic ARNs; invalid config → `ValueError` at synth; both registry aliases; the SSM fallback literal
`codepipeline-notifier`; plus the no-builtin-`hash()` and asset-root guards.

The notifier handler + `notify/` package behavior (pure `_map_event`, the deliver-gate, Slack poster
classification, SNS publish, routing) is tested in the standalone project:

```bash
cd /Users/eric.wilson/Projects/geek-cafe/geek-cafe-devops-monitoring && pytest tests/unit
```

---

## Related cdk-factory docs

- [Event Bus Infrastructure](event-bus-infrastructure.md) — the spine + lanes the **spine variant** (§7)
  feeds.
- [Naming & SSM](naming-and-ssm.md) · [SSM Parameter Naming Convention](ssm-parameter-naming-convention.md)
  — export/import path structure and the `__imports__` stage-isolation guardrail.
- [Stack Modules](stack-modules.md) · [Lambda Permissions](lambda-permissions.md).
