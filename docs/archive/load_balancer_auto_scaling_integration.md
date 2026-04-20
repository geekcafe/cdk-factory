# Load Balancer and Auto Scaling Integration

This document explains how the Load Balancer and Auto Scaling stacks work together to create a complete, scalable web application infrastructure using SSM Parameter Store for loose coupling.

## Overview

The integration between Load Balancer and Auto Scaling stacks follows a two-stage deployment pattern where resources are shared through AWS SSM Parameter Store rather than direct CloudFormation exports/imports. This approach provides better flexibility and reduces tight coupling between stacks.

## Integration Flow

```
┌─────────────────┐    SSM Parameters    ┌──────────────────┐
│ Load Balancer   │ ──────────────────► │ Auto Scaling     │
│ Stack           │                      │ Stack            │
│                 │                      │                  │
│ • Creates ALB   │                      │ • Creates ASG    │
│ • Creates TGs   │                      │ • Imports TG ARNs│
│ • Exports ARNs  │                      │ • Attaches to TGs│
└─────────────────┘                      └──────────────────┘
```

## Stage 1: Load Balancer Deployment

The Load Balancer stack creates the infrastructure and exports key resources:

### What Gets Exported

1. **ALB DNS Name**: For external access configuration
2. **ALB ARN**: For monitoring and additional configuration
3. **ALB Zone ID**: For Route 53 alias records
4. **Target Group ARNs**: **Critical for Auto Scaling integration**

### SSM Parameter Naming Convention

Target group ARNs are exported using this pattern:
```
/{deployment_name}/load-balancer/{resource_name}/target_group_{target_group_name}_arn
```

**Example**: If you have a target group named `web-servers`, it exports as:
```
/my-app/load-balancer/my-alb/target_group_web_servers_arn
```

## Stage 2: Auto Scaling Deployment

The Auto Scaling stack imports target group ARNs and attaches instances:

### Import Process

1. **SSM Parameter Lookup**: Searches for target group ARN parameters
2. **Automatic Detection**: Finds all parameters matching `target_group_*_arn` pattern
3. **CloudFormation Override**: Uses `TargetGroupARNs` property to attach ASG to target groups

### Key Implementation Details

The Auto Scaling stack uses CloudFormation property override:
```python
cfn_asg.add_property_override("TargetGroupARNs", target_group_arns)
```

This ensures instances are automatically registered with target groups when they launch.

## Configuration Examples

### Complete Integration Example

**Load Balancer Configuration:**
```json
{
  "load_balancer": {
    "name": "web-alb",
    "type": "APPLICATION",
    "vpc_id": "vpc-12345678",
    "subnets": ["subnet-12345678", "subnet-87654321"],
    "target_groups": [
      {
        "name": "web-servers",
        "port": 80,
        "protocol": "HTTP",
        "health_check": {
          "path": "/health",
          "healthy_threshold": 2,
          "unhealthy_threshold": 3
        }
      },
      {
        "name": "api-servers", 
        "port": 8080,
        "protocol": "HTTP",
        "health_check": {
          "path": "/api/health"
        }
      }
    ],
    "listeners": [
      {
        "port": 80,
        "protocol": "HTTP",
        "default_target_group": "web-servers",
        "rules": [
          {
            "priority": 100,
            "path_patterns": ["/api/*"],
            "target_group": "api-servers"
          }
        ]
      }
    ],
    "ssm_exports": {
      "target_group_web_servers_arn_path": "/my-app/web-tg-arn",
      "target_group_api_servers_arn_path": "/my-app/api-tg-arn"
    }
  }
}
```

**Auto Scaling Configuration:**
```json
{
  "auto_scaling": {
    "name": "web-asg",
    "instance_type": "t3.micro",
    "min_capacity": 2,
    "max_capacity": 10,
    "desired_capacity": 4,
    "health_check_type": "ELB",
    "health_check_grace_period": 300,
    "ssm_imports": {
      "target_group_web_servers_arn_path": "/my-app/web-tg-arn",
      "target_group_api_servers_arn_path": "/my-app/api-tg-arn"
    }
  }
}
```

## Critical Naming Relationships

### Target Group Name → SSM Parameter Name

The target group `name` in the Load Balancer configuration directly affects the SSM parameter name:

| Target Group Name | SSM Parameter Key | SSM Parameter Name |
|-------------------|-------------------|-------------------|
| `web-servers` | `target_group_web_servers_arn` | `target_group_web_servers_arn` |
| `api-servers` | `target_group_api_servers_arn` | `target_group_api_servers_arn` |
| `admin` | `target_group_admin_arn` | `target_group_admin_arn` |

### Path Mapping

You can customize the SSM parameter paths using `ssm_exports` and `ssm_imports`:

**Load Balancer exports to custom path:**
```json
{
  "ssm_exports": {
    "target_group_web_servers_arn_path": "/custom/path/web-tg"
  }
}
```

**Auto Scaling imports from custom path:**
```json
{
  "ssm_imports": {
    "target_group_web_servers_arn_path": "/custom/path/web-tg"
  }
}
```

## Deployment Pipeline

### Recommended Deployment Order

1. **Deploy Load Balancer Stack**
   ```bash
   cdk deploy LoadBalancerStack
   ```
   - Creates ALB and target groups
   - Exports target group ARNs to SSM

2. **Deploy Auto Scaling Stack**
   ```bash
   cdk deploy AutoScalingStack
   ```
   - Imports target group ARNs from SSM
   - Creates ASG with target group attachment
   - Instances automatically register with target groups

### Validation Steps

After deployment, verify the integration:

1. **Check SSM Parameters**:
   ```bash
   aws ssm get-parameters-by-path --path "/my-app/load-balancer"
   ```

2. **Verify Target Group Health**:
   ```bash
   aws elbv2 describe-target-health --target-group-arn <target-group-arn>
   ```

3. **Check ASG Target Groups**:
   ```bash
   aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names <asg-name>
   ```

## Troubleshooting

### Common Issues

1. **Instances Not Registering**
   - Verify SSM parameter exists and contains correct target group ARN
   - Check Auto Scaling Group has `TargetGroupARNs` property set
   - Ensure health check configuration is correct

2. **SSM Parameter Not Found**
   - Confirm Load Balancer stack deployed successfully
   - Verify target group name matches expected SSM parameter name
   - Check `ssm_exports` configuration in Load Balancer

3. **Health Check Failures**
   - Verify application is running on correct port
   - Check security group rules allow health check traffic
   - Confirm health check path returns expected status codes

### Debug Commands

```bash
# List all SSM parameters for the deployment
aws ssm get-parameters-by-path --path "/<deployment-name>" --recursive

# Check target group health
aws elbv2 describe-target-health --target-group-arn <arn>

# View ASG details including target groups
aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names <name>
```

## Best Practices

1. **Consistent Naming**: Use descriptive, consistent names for target groups that clearly indicate their purpose

2. **Health Check Configuration**: Ensure health check paths and ports match your application configuration

3. **SSM Parameter Organization**: Use hierarchical paths that reflect your deployment structure

4. **Deployment Validation**: Always verify target group health after Auto Scaling deployment

5. **Monitoring**: Set up CloudWatch alarms for target group health and Auto Scaling metrics

## Advanced Scenarios

### Multiple Target Groups per ASG

An Auto Scaling Group can be attached to multiple target groups:

```json
{
  "auto_scaling": {
    "ssm_imports": {
      "target_group_web_servers_arn_path": "/app/web-tg-arn",
      "target_group_api_servers_arn_path": "/app/api-tg-arn",
      "target_group_admin_arn_path": "/app/admin-tg-arn"
    }
  }
}
```

### Cross-Account Integration

For cross-account deployments, use full SSM parameter ARNs:

```json
{
  "ssm_imports": {
    "target_group_web_servers_arn_path": "arn:aws:ssm:us-east-1:123456789012:parameter/shared/web-tg-arn"
  }
}
```

This integration pattern provides a robust, scalable foundation for web applications with automatic load balancing and scaling capabilities.
