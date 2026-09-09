# Deterministic Construct IDs — Never Use Builtin `hash()`

## Priority: HIGH

## Rule

NEVER use Python's builtin `hash()` to build a construct ID (or any value that
feeds a CloudFormation logical ID). Builtin `hash()` is seeded per process via
`PYTHONHASHSEED`, so it returns a DIFFERENT value for the same input on every
`cdk synth`. Use a stable content hash (`hashlib`) instead.

## Why

CDK derives a resource's CloudFormation **logical ID** from its construct ID. If
the construct ID changes between synths, the logical ID changes, and CloudFormation
treats the resource as different:

- Best case: a spurious, noisy diff on every deploy.
- Worst case: resources that `Ref` the churning one look changed too, cascading
  into updates or **replacements** of otherwise-stable resources.

Real incident (cdk-factory 1.10.x → 1.11.0): imported SSM parameters used
`hash(path) % 10000` in their construct IDs. Because the value re-randomized every
synth, an ECS service's `CapacityProviderStrategy` / `LoadBalancers` references
churned, which forced the service's Application Auto Scaling target-tracking
policies to be re-created and failed the deploy with:

```
Only one TargetTrackingScaling policy for a given metric specification is allowed.
```

## Correct Pattern

```python
import hashlib

# CORRECT — deterministic across synths, processes, and machines
suffix = int(hashlib.sha1(path.encode()).hexdigest(), 16) % 10000
construct_id = f"ssm-import-{param_key}-{suffix}"
```

Or, when the surrounding identifier is already unique, drop the numeric suffix
entirely rather than hashing at all:

```python
construct_id = f"ssm-import-{param_key}"
```

## Anti-Pattern

```python
# WRONG — builtin hash() is randomized by PYTHONHASHSEED, non-reproducible
construct_id = f"ssm-import-{param_key}-{hash(path) % 10000}"
id = f"lambda-edge-arn-{hash(ssm_param_path) % 10000}-param"
unique_id = f"CF-{domain}-{hash(cache_key) % 10000}"
```

## When This Applies

- Any construct ID, logical ID override, or resource name derived from a hash in
  `src/cdk_factory/`
- SSM import lookups, imported-resource lookups, CfnParameter IDs, cache keys used
  as construct IDs

## Notes

- `hashlib.sha1`/`sha256` here is for a stable short identifier, not security — a
  content hash of the input is all that's required.
- Prefer explicit stable construct IDs (e.g. `f"{workload}-{env}-rds-instance"`)
  over hashed ones wherever the inputs are already unique and readable.
- This complements `no-live-aws-calls.md`: both exist so `cdk synth` is fully
  reproducible and CloudFormation diffs reflect real changes only.
