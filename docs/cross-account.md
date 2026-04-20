# Cross-Account Setup

## Account Roles

| Account | Purpose | Example |
|---------|---------|---------|
| **DevOps** | Runs CodePipeline, hosts ECR repos | `974817967438` |
| **Target** | Stacks deploy here (per-tenant or per-env) | `959096737760` |
| **Management** | Owns root domain DNS (Route53 parent zone) | `833510414569` |

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  DevOps Account  │────▶│  Target Account  │     │  Mgmt Account   │
│  (Pipeline)      │     │  (Stacks)        │     │  (DNS Root)     │
│                  │────▶│                  │     │                 │
│  CodePipeline    │     │  Lambda, DynamoDB │◀───│  Route53 parent │
│  ECR repos       │     │  S3, API GW      │     │  zone           │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

---

## Pipeline Cross-Account Roles

Configure in `pipeline.cross_account_role_arns`:

```json
{
  "pipeline": {
    "cross_account_role_arns": [
      "arn:aws:iam::{{AWS_ACCOUNT}}:role/DevOpsCrossAccountAccessRole",
      "{{MANAGEMENT_ACCOUNT_ROLE_ARN}}"
    ]
  }
}
```

These roles are assumed by pipeline build steps for:
- CDK deploy to target accounts
- DNS delegation to management account
- SSM parameter lookups across accounts

---

## CDK Bootstrap Trust

Each target account must be CDK-bootstrapped with trust to the DevOps account:

```bash
# In the TARGET account
npx cdk bootstrap aws://TARGET_ACCOUNT/us-east-1 \
  --trust DEVOPS_ACCOUNT \
  --cloudformation-execution-policies arn:aws:iam::aws:policy/AdministratorAccess
```

---

## DevOpsCrossAccountAccessRole

Each target and management account needs an IAM role that the DevOps account can assume:

```
Role Name: DevOpsCrossAccountAccessRole
Trust Policy: Allow DevOps account to assume
Permissions: Scoped to what pipeline steps need
  - Route53 (for DNS delegation)
  - SSM (for parameter lookups)
  - STS (for further role chaining if needed)
```

---

## Route53 DNS Delegation

Automates subdomain delegation between management account (parent zone) and target account (child zone).

### How It Works

1. Management account owns root domain: `example.com` (zone `Z0123456789`)
2. Target account creates subdomain zone: `dev.example.com`
3. Pipeline post-step creates NS records in parent zone pointing to child zone's name servers

### Pipeline Post-Step

```json
{
  "builds": [
    {
      "enabled": true,
      "post_steps": [
        {
          "id": "dns-delegation",
          "name": "Cross-Account DNS Delegation",
          "commands": [
            "pip install cdk-factory boto3",
            "export TARGET_ACCOUNT_ROLE_ARN=arn:aws:iam::{{AWS_ACCOUNT}}:role/DevOpsCrossAccountAccessRole",
            "export TARGET_R53_ZONE_NAME={{HOSTED_ZONE_NAME}}",
            "export MANAGEMENT_ACCOUNT_ROLE_ARN={{MANAGEMENT_ACCOUNT_ROLE_ARN}}",
            "export MGMT_R53_HOSTED_ZONE_ID={{MGMT_R53_HOSTED_ZONE_ID}}",
            "python -m cdk_factory.utilities.route53_delegation"
          ]
        }
      ]
    }
  ]
}
```

### Programmatic Usage

```python
from cdk_factory.utilities.route53_delegation import Route53Delegation

delegation = Route53Delegation()
delegation.delegate(
    target_role_arn="arn:aws:iam::111111111111:role/DevOpsCrossAccountAccessRole",
    management_role_arn="arn:aws:iam::222222222222:role/DevOpsCrossAccountAccessRole",
    target_zone_name="dev.example.com",
    management_zone_id="Z0123456789",
)
```

### Environment Variables (CLI mode)

| Variable | Description |
|----------|-------------|
| `TARGET_ACCOUNT_ROLE_ARN` | Role in target account (has Route53 access to child zone) |
| `MANAGEMENT_ACCOUNT_ROLE_ARN` | Role in management account (has Route53 access to parent zone) |
| `TARGET_R53_ZONE_NAME` | Subdomain zone name (e.g., `dev.example.com`) |
| `MGMT_R53_HOSTED_ZONE_ID` | Parent hosted zone ID in management account |
