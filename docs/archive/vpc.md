# VPC Stack Configuration

This document provides comprehensive configuration guidance for the CDK Factory VPC stack, including networking, security groups, and advanced features.

## Overview

The CDK Factory VPC stack creates a complete Virtual Private Cloud with public, private, and isolated subnets, along with networking components like NAT gateways, VPC endpoints, and security group management.

## Basic Configuration

### Minimal VPC Setup

```json
{
  "vpc": {
    "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-vpc",
    "cidr": "10.0.0.0/16",
    "max_azs": 2
  }
}
```

### Complete VPC Configuration

```json
{
  "vpc": {
    "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-vpc",
    "description": "VPC for {{WORKLOAD_NAME}} {{ENVIRONMENT}} environment",
    "cidr": "10.1.0.0/16",
    "max_azs": 2,
    "enable_dns_hostnames": true,
    "enable_dns_support": true,
    "restrict_default_security_group": false,
    "public_subnets": true,
    "private_subnets": true,
    "isolated_subnets": true,
    "nat_gateways": {
      "count": 0
    },
    "enable_s3_endpoint": true,
    "enable_interface_endpoints": false,
    "interface_endpoints": [],
    "subnets": {
      "public": {
        "enabled": true,
        "cidr_mask": 25
      },
      "private": {
        "enabled": true,
        "cidr_mask": 25
      },
      "isolated": {
        "enabled": true,
        "cidr_mask": 25
      }
    },
    "tags": {
      "Application": "{{WORKLOAD_NAME}}",
      "Environment": "{{ENVIRONMENT}}"
    },
    "ssm": {
      "exports": {
        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id",
        "vpc_cidr": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/cidr",
        "public_subnet_ids": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/public-subnet-ids",
        "private_subnet_ids": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/private-subnet-ids",
        "isolated_subnet_ids": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/isolated-subnet-ids"
      }
    }
  }
}
```

## Configuration Properties

### Core Properties

| Property | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `name` | string | Yes | - | VPC name (supports template variables) |
| `description` | string | No | - | VPC description |
| `cidr` | string | Yes | "10.0.0.0/16" | VPC CIDR block |
| `max_azs` | integer | No | 2 | Maximum number of availability zones |

### DNS Properties

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `enable_dns_hostnames` | boolean | true | Enable DNS hostnames for EC2 instances |
| `enable_dns_support` | boolean | true | Enable DNS resolution in VPC |

### Subnet Configuration

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `public_subnets` | boolean | true | Enable public subnet creation |
| `private_subnets` | boolean | true | Enable private subnet creation |
| `isolated_subnets` | boolean | false | Enable isolated subnet creation |
| `subnets` | object | - | Detailed subnet configuration |

#### Subnet Object Properties

Each subnet type (public, private, isolated) supports:

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `enabled` | boolean | true | Enable this subnet type |
| `cidr_mask` | integer | 24 | CIDR mask for subnets (recommended: 25-28) |

### NAT Gateway Configuration

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `nat_gateways.count` | integer | 1 | Number of NAT gateways (0 = none) |

### VPC Endpoints

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `enable_s3_endpoint` | boolean | true | Create S3 VPC gateway endpoint |
| `enable_interface_endpoints` | boolean | false | Enable interface endpoints |
| `interface_endpoints` | array | [] | List of interface endpoint services |

## Default Security Group Restriction

### Overview

The VPC stack can restrict the default security group for enhanced security. This feature uses a CloudFormation custom resource to modify the default security group.

### Configuration

```json
{
  "vpc": {
    "restrict_default_security_group": false
  }
}
```

### Behavior

| Setting | Behavior | IAM Requirements | Cleanup |
|---------|----------|------------------|---------|
| `false` | Default SG remains unrestricted | None required | N/A |
| `true` | Default SG gets "deny all inbound" rule | Auto-added permissions | Manual cleanup required |

### ⚠️ Important: Toggle Behavior

When you toggle `restrict_default_security_group` from `true` to `false`:

1. **Custom resource is deleted** automatically
2. **Security group rules PERSIST** - this is AWS CDK behavior
3. **Manual cleanup required** to revert restrictions

### Manual Cleanup Steps

If you disable the feature and need to clean up:

#### AWS Console
1. Navigate to EC2 → Security Groups
2. Find the default security group (usually named "default")
3. Remove any "deny all inbound" rules
4. Ensure "allow self-referential" rule exists if needed

#### AWS CLI
```bash
# List current rules
aws ec2 describe-security-groups --group-ids sg-xxxxxxxxx

# Remove deny rule (get rule ID from describe output)
aws ec2 revoke-security-group-ingress \
  --group-id sg-xxxxxxxxx \
  --security-group-rules RuleId=sg-rule-xxxxxxxxx

# Add back default self rule if needed
aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxxxxxx \
  --protocol all \
  --port -1 \
  --source-group sg-xxxxxxxxx
```

### Recommendations

| Use Case | Recommended Setting |
|----------|---------------------|
| Development/Testing | `false` (simpler, no cleanup needed) |
| Production Compliance | `true` (if required by security policies) |
| Multi-tenant | `true` (additional security layer) |

## CIDR Planning

### Subnet CIDR Allocation

CDK automatically allocates CIDR blocks within your VPC CIDR. Consider these guidelines:

| VPC Size | Recommended Subnet Mask | Subnets per AZ | IPs per Subnet |
|----------|-------------------------|----------------|----------------|
| /16 (65,536 IPs) | /25 | 6 (2 AZs × 3 types) | 128 |
| /16 (65,536 IPs) | /26 | 6 (2 AZs × 3 types) | 64 |
| /16 (65,536 IPs) | /27 | 6 (2 AZs × 3 types) | 32 |

### Example CIDR Layout

With VPC CIDR `10.1.0.0/16` and `/25` subnets:
- Public: `10.1.0.0/25`, `10.1.0.128/25`
- Private: `10.1.1.0/25`, `10.1.1.128/25`  
- Isolated: `10.1.2.0/25`, `10.1.2.128/25`

## SSM Integration

The VPC stack exports network parameters to SSM Parameter Store for use by other stacks:

### Exported Parameters

| Parameter | SSM Path | Description |
|-----------|----------|-------------|
| `vpc_id` | `/{ENVIRONMENT}/{WORKLOAD_NAME}/vpc/id` | VPC ID |
| `vpc_cidr` | `/{ENVIRONMENT}/{WORKLOAD_NAME}/vpc/cidr` | VPC CIDR block |
| `public_subnet_ids` | `/{ENVIRONMENT}/{WORKLOAD_NAME}/vpc/public-subnet-ids` | Public subnet IDs (comma-separated) |
| `private_subnet_ids` | `/{ENVIRONMENT}/{WORKLOAD_NAME}/vpc/private-subnet-ids` | Private subnet IDs (comma-separated) |
| `isolated_subnet_ids` | `/{ENVIRONMENT}/{WORKLOAD_NAME}/vpc/isolated-subnet-ids` | Isolated subnet IDs (comma-separated) |

### Importing in Other Stacks

```json
{
  "rds": {
    "ssm": {
      "imports": {
        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id",
        "subnet_ids": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/isolated-subnet-ids"
      }
    }
  }
}
```

## Troubleshooting

### Common Issues

#### CIDR Conflicts
**Error**: "The CIDR '10.0.0.0/24' conflicts with another subnet"

**Solution**: 
1. Use a different VPC CIDR range (e.g., `10.1.0.0/16` instead of `10.0.0.0/16`)
2. Use smaller subnet masks (/25, /26) for better allocation
3. Check for existing VPCs in the region

#### Dummy Availability Zones
**Error**: "Value (dummy1b) for parameter availabilityZone is invalid"

**Solution**: 
- This is fixed in CDK Factory v0.17.4+ with explicit AZ mapping
- Ensure you're using the latest version

#### IAM Permission Errors
**Error**: "Not authorized to perform ec2:AuthorizeSecurityGroupIngress"

**Solution**:
- Set `restrict_default_security_group: false` 
- Or ensure proper IAM permissions are in place

### Best Practices

1. **Use unique VPC CIDRs** across your AWS accounts
2. **Plan subnet sizes** based on expected growth
3. **Enable isolated subnets** for databases and sensitive workloads
4. **Use SSM exports** for consistent cross-stack configuration
5. **Test with `restrict_default_security_group: false`** first
6. **Document any manual cleanup** if toggling security group restrictions

## Migration from Previous Versions

### Breaking Changes in v0.17.4+

- **CIDR allocation**: Improved to avoid conflicts
- **Availability zones**: Explicit mapping to prevent dummy AZs
- **Default SG restriction**: Now configurable with proper IAM handling

### Migration Steps

1. Update CDK Factory version: `pip install cdk_factory>=0.17.4`
2. Review VPC CIDR - consider changing if conflicts occur
3. Add `restrict_default_security_group` setting explicitly
4. Test deployment in non-production environment first

## Advanced Features

### Custom Subnet Naming

See [VPC Custom Subnet Naming](vpc_custom_subnet_naming.md) for detailed information on customizing subnet names.

### VPC Endpoints

Configure interface endpoints for private connectivity:

```json
{
  "vpc": {
    "enable_interface_endpoints": true,
    "interface_endpoints": [
      "com.amazonaws.<region>.ecr.api",
      "com.amazonaws.<region>.ecr.dkr",
      "com.amazonaws.<region>.s3"
    ]
  }
}
```

### Tagging

Apply custom tags to all VPC resources:

```json
{
  "vpc": {
    "tags": {
      "Application": "{{WORKLOAD_NAME}}",
      "Environment": "{{ENVIRONMENT}}",
      "Team": "platform",
      "CostCenter": "engineering"
    }
  }
}
```
