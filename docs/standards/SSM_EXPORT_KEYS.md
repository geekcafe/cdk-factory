# SSM Export Keys - Naming Standards

This document defines the standard naming conventions for SSM parameter exports across all CDK Factory modules.

## Purpose

When resources export values to AWS Systems Manager Parameter Store, they must use **consistent key names** that match what the module expects. Mismatched keys will cause deployment failures.

---

## Standard Keys by Resource Type

### ECR (Elastic Container Registry)

**Module**: `ecr_stack`

| Key | Description | Example Value |
|-----|-------------|---------------|
| `uri` | Repository URI | `123456789.dkr.ecr.us-east-1.amazonaws.com/my-repo` |
| `arn` | Repository ARN | `arn:aws:ecr:us-east-1:123456789:repository/my-repo` |
| `name` | Repository name | `my-repo` |

**Example Config:**
```json
{
  "name": "my-ecr-repo",
  "module": "ecr_stack",
  "resources": [{
    "name": "my-app",
    "ssm_exports": {
      "uri": "/prod/myapp/ecr/app/uri",
      "arn": "/prod/myapp/ecr/app/arn"
    }
  }]
}
```

❌ **WRONG** (will fail):
```json
"ssm_exports": {
  "repository_uri": "/prod/myapp/ecr/app/uri",  // ❌ Wrong key
  "repository_arn": "/prod/myapp/ecr/app/arn"   // ❌ Wrong key
}
```

---

### RDS (Relational Database Service)

**Module**: `rds_stack`

| Key | Description | Example Value |
|-----|-------------|---------------|
| `db_endpoint` | Database endpoint | `mydb.abc123.us-east-1.rds.amazonaws.com` |
| `db_port` | Database port | `3306` |
| `db_name` | Database name | `myapp_db` |
| `db_secret_arn` | Secrets Manager ARN | `arn:aws:secretsmanager:us-east-1:123:secret:rds-abc123` |

**Example Config:**
```json
{
  "rds": {
    "engine": "mysql",
    "ssm_exports": {
      "db_endpoint": "/prod/myapp/rds/endpoint",
      "db_port": "/prod/myapp/rds/port",
      "db_name": "/prod/myapp/rds/database-name",
      "db_secret_arn": "/prod/myapp/rds/secret-arn"
    }
  }
}
```

---

### VPC (Virtual Private Cloud)

**Module**: `vpc_stack`

| Key | Description | Example Value |
|-----|-------------|---------------|
| `vpc_id` | VPC ID | `vpc-abc123` |
| `public_subnet_ids` | Public subnet IDs | `subnet-123,subnet-456` |
| `private_subnet_ids` | Private subnet IDs | `subnet-789,subnet-012` |
| `availability_zones` | Availability zones | `us-east-1a,us-east-1b` |

---

### Security Groups

**Module**: `security_group_stack`

| Key | Description | Example Value |
|-----|-------------|---------------|
| `security_group_id` | Security group ID | `sg-abc123` |
| `security_group_name` | Security group name | `my-app-sg` |

---

### ECS (Elastic Container Service)

**Module**: `ecs_service_stack`

| Key | Description | Example Value |
|-----|-------------|---------------|
| `name` | **Required** - Service identifier | `my-service` |
| `cluster_name` | ECS cluster name | `my-cluster` |
| `cluster_arn` | ECS cluster ARN | `arn:aws:ecs:us-east-1:123:cluster/my-cluster` |
| `service_name` | ECS service name | `my-service` |
| `service_arn` | ECS service ARN | `arn:aws:ecs:us-east-1:123:service/my-service` |
| `task_definition_arn` | Task definition ARN | `arn:aws:ecs:us-east-1:123:task-definition/my-task:1` |

**Important**: The `ecs` config object **must** have a top-level `name` field.

**Example Config:**
```json
{
  "ecs": {
    "name": "my-service",
    "cluster_name": "my-cluster",
    "service_name": "my-service",
    ...
  }
}
```

---

## Naming Convention Rules

### 1. Use Attribute Names, Not Resource Type Prefixes

✅ **CORRECT:**
```json
{
  "uri": "/prod/myapp/ecr/uri",
  "arn": "/prod/myapp/ecr/arn"
}
```

❌ **WRONG:**
```json
{
  "repository_uri": "/prod/myapp/ecr/uri",  // Don't prefix with resource type
  "ecr_arn": "/prod/myapp/ecr/arn"          // Don't prefix with resource type
}
```

**Reason**: The module already knows it's an ECR repository. The key should describe the **attribute**, not the resource.

### 2. SSM Parameter Path Standards

SSM parameter paths should follow this pattern:
```
/{environment}/{workload}/{resource-type}/{resource-name}/{attribute}
```

**Examples:**
```
/prod/trav-talks/ecr/infra-test/uri
/prod/trav-talks/rds/endpoint
/dev/myapp/vpc/id
```

### 3. Consistency Across Modules

If a module exports an ARN, always use the key `arn`, not `resource_arn` or `arn_value`.

**Standard attribute names:**
- `arn` - Amazon Resource Name
- `uri` - Uniform Resource Identifier
- `id` - Resource ID
- `name` - Resource name
- `endpoint` - Service endpoint
- `port` - Port number

---

## How to Find Accepted Keys

### Method 1: Check Configuration Class

Look in `/src/cdk_factory/configurations/resources/{resource}.py`:

```python
@property
def uri(self) -> str:  # ← Key name is "uri"
    return self.__config.get("uri")
```

### Method 2: Check Error Message

When you get a validation error, it will show accepted keys:

```
Missing keys: ['repository_uri', 'repository_arn']
The accepted keys are: ['name', 'uri', 'arn']
```

### Method 3: Check Existing Configs

Look at working examples in:
- `/configs/resources/{resource-type}/`
- Existing deployment configs

---

## Common Mistakes

### 1. Adding Resource Type Prefix

❌ `repository_uri` → ✅ `uri`  
❌ `vpc_id` → ✅ `id`  
❌ `db_endpoint` → ✅ `endpoint` (in resource config context)

### 2. Inconsistent Naming

If one module uses `arn`, don't use `resource_arn` in another module.

### 3. Wrong Attribute Names

Check the configuration class properties to see exact names expected.

---

## Validation

CDK Factory will validate SSM export keys during synthesis and show:

```
🚨 Missing keys: ['wrong_key']
🚨 Accepted keys: ['correct_key_1', 'correct_key_2']
```

Always check the error message for the exact keys expected.

---

## Summary

| Resource | Key Pattern | Example |
|----------|-------------|---------|
| ECR | `uri`, `arn`, `name` | `uri`, not `repository_uri` |
| RDS | `db_endpoint`, `db_port`, `db_name`, `db_secret_arn` | Prefixed with `db_` |
| VPC | `vpc_id`, `public_subnet_ids`, `private_subnet_ids` | Prefixed with resource context |
| Security Group | `security_group_id`, `security_group_name` | Full context needed |
| ECS | `cluster_name`, `service_name`, `task_definition_arn` | Resource-specific names |

**General Rule**: Check the module's configuration class for exact property names. Those property names are the keys to use in `ssm_exports`.

---

## Questions?

If unsure about a key name:
1. Check the configuration class in `/configurations/resources/{resource}.py`
2. Look at the `@property` method names
3. Use those exact names as keys in `ssm_exports`
4. Follow the SSM path pattern: `/{env}/{workload}/{type}/{name}/{attr}`
