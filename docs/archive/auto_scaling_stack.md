# Auto Scaling Stack

The Auto Scaling Stack provides a reusable pattern for creating AWS Auto Scaling Groups with EC2 instances, including comprehensive configuration options for launch templates, scaling policies, and target group integration.

## Features

- **Launch Templates**: Configurable EC2 launch templates with AMI selection
- **Auto Scaling Groups**: Full ASG configuration with capacity and health checks
- **Target Group Integration**: Automatic attachment to load balancer target groups via SSM parameters
- **Container Support**: Built-in Docker and ECR integration
- **IAM Roles**: Automatic instance role creation with managed policies
- **Scaling Policies**: Target tracking and step scaling policies
- **Update Policies**: CloudFormation update policy configuration
- **Block Devices**: EBS volume configuration

## Configuration

### Basic Configuration

```json
{
  "auto_scaling": {
    "name": "web-servers",
    "vpc_id": "vpc-12345678",
    "subnet_group_name": "private",
    "instance_type": "t3.micro",
    "ami_type": "amazon-linux-2023",
    "min_capacity": 1,
    "max_capacity": 10,
    "desired_capacity": 2,
    "security_group_ids": ["sg-12345678"],
    "health_check_type": "ELB",
    "health_check_grace_period": 300,
    "cooldown": 300
  }
}
```

### Launch Template Configuration

```json
{
  "auto_scaling": {
    "ami_id": "ami-12345678",
    "instance_type": "t3.small",
    "detailed_monitoring": true,
    "managed_policies": [
      "AmazonSSMManagedInstanceCore",
      "CloudWatchAgentServerPolicy"
    ],
    "user_data_commands": [
      "yum update -y",
      "yum install -y amazon-cloudwatch-agent",
      "/opt/aws/amazon-cloudwatch-agent/bin/config-wizard"
    ],
    "block_devices": [
      {
        "device_name": "/dev/xvda",
        "volume_size": 20,
        "volume_type": "gp3",
        "delete_on_termination": true,
        "encrypted": true
      }
    ]
  }
}
```

### Container Configuration

The Auto Scaling Stack includes built-in support for containerized applications:

```json
{
  "auto_scaling": {
    "container_config": {
      "ecr": {
        "account_id": "123456789012",
        "region": "us-east-1",
        "repo": "my-app",
        "tag": "latest"
      },
      "database": {
        "secret_arn": "arn:aws:secretsmanager:us-east-1:123456789012:secret:db-credentials"
      },
      "port": 8080,
      "run_command": "docker run -d --name app -p 8080:8080 --restart=always my-app:latest"
    }
  }
}
```

### Scaling Policies

Configure automatic scaling based on metrics:

```json
{
  "auto_scaling": {
    "scaling_policies": [
      {
        "name": "cpu-scaling",
        "type": "target_tracking",
        "metric_name": "CPUUtilization",
        "statistic": "Average",
        "period": 300,
        "steps": [
          {
            "lower": 0,
            "upper": 50,
            "change": 0
          },
          {
            "lower": 50,
            "upper": 80,
            "change": 1
          },
          {
            "lower": 80,
            "change": 2
          }
        ]
      }
    ]
  }
}
```

### Update Policy Configuration

Control how instances are updated during deployments:

```json
{
  "auto_scaling": {
    "update_policy": {
      "min_instances_in_service": 1,
      "max_batch_size": 2,
      "pause_time": 300
    }
  }
}
```

## Target Group Integration

The Auto Scaling Stack automatically integrates with Load Balancer target groups through SSM parameters. This enables seamless registration of instances with load balancers.

### SSM Import Configuration

Configure which target group ARNs to import:

```json
{
  "auto_scaling": {
    "ssm_imports": {
      "target_group_web_servers_arn_path": "/my-app/load-balancer/web-tg-arn",
      "target_group_api_servers_arn_path": "/my-app/load-balancer/api-tg-arn"
    }
  }
}
```

### Automatic Target Group Attachment

The stack automatically:
1. Imports target group ARNs from SSM parameters
2. Attaches the Auto Scaling Group to all imported target groups
3. Uses CloudFormation property override: `TargetGroupARNs`

**Key Integration Point**: The target group name from the Load Balancer configuration becomes part of the SSM parameter name that this stack imports. For example, a target group named `web-servers` in the Load Balancer will export its ARN as `target_group_web_servers_arn`, which this stack can import.

## AMI Configuration

### Predefined AMI Types

```json
{
  "auto_scaling": {
    "ami_type": "amazon-linux-2023"  // or "amazon-linux-2"
  }
}
```

### Custom AMI

```json
{
  "auto_scaling": {
    "ami_id": "ami-12345678"
  }
}
```

## Instance Types

Support for various instance type formats:

```json
{
  "auto_scaling": {
    "instance_type": "t3.micro"     // Standard format
    // or
    "instance_type": "m5.large"     // Will be parsed as M5.LARGE
  }
}
```

## Security Groups

Multiple security group formats supported:

```json
{
  "auto_scaling": {
    "security_group_ids": [
      "sg-12345678",
      "sg-87654321,sg-11111111"  // Comma-separated list also supported
    ]
  }
}
```

## Health Checks

Configure health check behavior:

```json
{
  "auto_scaling": {
    "health_check_type": "ELB",           // or "EC2"
    "health_check_grace_period": 300,     // seconds
    "termination_policies": [
      "OldestInstance",
      "Default"
    ]
  }
}
```

## Container Integration Features

### ECR Integration
- Automatic ECR login
- Docker image pulling from ECR repositories
- Support for custom account IDs and regions

### Database Integration
- AWS Secrets Manager integration
- Automatic database credential injection
- Environment variable setup for containerized applications

### Docker Management
- Automatic Docker installation
- Container lifecycle management
- Port mapping and restart policies

## Pipeline Integration Pattern

The Auto Scaling Stack is designed to work in a multi-stage deployment pipeline:

1. **Stage 1**: Load Balancer stack deploys and exports target group ARNs to SSM
2. **Stage 2**: Auto Scaling stack deploys and imports target group ARNs from SSM
3. **Result**: Instances automatically register with the correct target groups

## Stack Registration

The Auto Scaling Stack (standardized) is registered with these aliases:
- `auto_scaling_library_module`
- `auto_scaling_stack`

## Dependencies

- **VPC**: Must be provided via `auto_scaling.vpc_id` or `workload.vpc_id`
- **Subnets**: Specified via `subnet_group_name` for subnet selection
- **Security Groups**: Required for instance network access
- **Target Groups**: Optional, imported from Load Balancer stack via SSM

## Best Practices

1. **Target Group Integration**: Use consistent naming between Load Balancer target groups and Auto Scaling SSM imports
2. **Health Checks**: Use ELB health checks when integrating with load balancers
3. **Update Policies**: Configure appropriate update policies for zero-downtime deployments
4. **Instance Types**: Choose appropriate instance types for your workload
5. **Container Security**: Use IAM roles and Secrets Manager for secure container deployments
6. **Monitoring**: Enable detailed monitoring for better scaling decisions

## Common Integration Example

Load Balancer configuration:
```json
{
  "load_balancer": {
    "target_groups": [
      {
        "name": "web-servers",
        "port": 80,
        "protocol": "HTTP"
      }
    ]
  }
}
```

Auto Scaling configuration:
```json
{
  "auto_scaling": {
    "ssm_imports": {
      "target_group_web_servers_arn_path": "/my-app/load-balancer/target_group_web_servers_arn"
    }
  }
}
```

This configuration ensures that instances launched by the Auto Scaling Group are automatically registered with the `web-servers` target group created by the Load Balancer stack.
