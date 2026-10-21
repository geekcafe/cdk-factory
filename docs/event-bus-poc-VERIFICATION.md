# event_bus PoC — cdk-factory verification

## Decision: NO cdk-factory source changes

The event_bus PoC is wired **entirely with existing cdk-factory stack modules**
plus the geek-cafe-lambdas cdk config. **No `src/cdk_factory/` source was
changed.**

### Why no change is needed

The PoC delivery topology is the proven ChatOps shape:

```
EventBridge rule (match detail.delivery_lane) -> SQS (+DLQ) -> consumer Lambda -> transport
```

Every piece is already a first-class cdk-factory module, exercised today by the
chat-ops / realtime stacks:

| PoC need | Existing cdk-factory module | Status |
|---|---|---|
| EventBridge rule matching `detail.delivery_lane` → SQS target (realtime/slack/sns) | `stack_library/event_bridge/eventbridge_stack.py` (`aws_events_targets.SqsQueue`) | reused as-is |
| Per-lane SQS queues + DLQ | `stack_library/simple_queue_service` | reused as-is |
| Ingress Lambda (public HTTP) + SQS-trigger consumer Lambdas | `stack_library/aws_lambdas/lambda_stack.py` (`api_gateway` + `sqs` trigger) | reused as-is |
| Ingress shared secret | `stack_library/secrets_manager` | reused as-is |
| Critical-event SNS topic | `stack_library/sns/sns_stack.py` | reused as-is |
| AppSync Events (realtime web monitor) | `stack_library/appsync_events` | reused as-is |

The design/deep-dive flagged that `eventbridge_stack` is **SQS-target-only** (no
direct rule→SNS or rule→Lambda target). That limitation is **not on the PoC
critical path**: the PoC routes every lane through SQS → consumer (which is also
the recommended shape — per-branch DLQ/retry/batch control), so the SQS-only
target is exactly what's used. A direct rule→SNS/Lambda target would only be
needed for a post-PoC hardening optimization and is explicitly deferred
(DESIGN §6, §12). No IoT or SES module was added (out of scope).

### Verified by running

Against the cdk-factory repo venv (`.venv`), confirming the untouched modules
the PoC depends on still synth/behave correctly:

```
.venv/bin/python -m pytest \
  tests/unit/test_eventbridge_rule_sqs_stack.py \
  tests/unit/test_eventbridge_multi_rule_stack.py \
  tests/unit/test_eventbridge_ssm_export.py \
  tests/unit/test_chatops_sqs_queue.py \
  tests/unit/test_lambda_sqs_trigger_consume_grant.py
    => 22 passed
```

(Run from the `event-bus-poc` worktree; the worktree has no separate venv, so the
main cdk-factory `.venv`, which has `aws_cdk` installed, was used.)

### Guardrails honored

- No live AWS calls at synth (no module source touched; existing modules already
  resolve cross-stack values via SSM/CF tokens).
- No builtin `hash()` for construct ids introduced (no source touched).

The actual event_bus stack wiring lives in geek-cafe-lambdas
(`cdk/configs/stacks/...`), modeled on the chatops/realtime configs — see that
repo's `event-bus-poc-VERIFICATION.md`.
