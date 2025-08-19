# Load Balancer Configuration Samples

This directory contains sample configurations for AWS Load Balancers using the CDK-Factory framework.

## Configuration Files

- `load_balancer_sample.json`: Comprehensive Application Load Balancer (ALB) configuration with multiple target groups, listeners, and rules
- `network_load_balancer_sample.json`: Network Load Balancer (NLB) configuration example
- `config_min.json`: Minimal configuration to get started with a simple ALB

## Using the Load Balancer Stack

### Basic Usage

```python
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.workload.workload_factory import WorkloadConfig
from cdk_factory.stack_library.load_balancer.load_balancer_stack import LoadBalancerStack

# Create deployment and workload configurations
deployment = DeploymentConfig({"name": "dev"})
workload = WorkloadConfig({"name": "webapp", "vpc_id": "vpc-12345"})

# Create load balancer stack configuration
load_balancer_config = {
    "name": "app-alb",
    "type": "APPLICATION",
    "internet_facing": True,
    "vpc_id": "vpc-12345",
    "security_groups": ["sg-12345"],
    "target_groups": [
        {
            "name": "app-tg",
            "port": 80,
            "protocol": "HTTP",
            "target_type": "instance",
            "health_check": {
                "path": "/"
            }
        }
    ],
    "listeners": [
        {
            "name": "http",
            "port": 80,
            "protocol": "HTTP",
            "default_target_group": "app-tg"
        }
    ]
}

stack_config = StackConfig({"load_balancer": load_balancer_config})

# Create and build the load balancer stack
load_balancer_stack = LoadBalancerStack(scope, "LoadBalancerStack")
load_balancer_stack.build(stack_config, deployment, workload)

# Access the created load balancer and target groups
load_balancer = load_balancer_stack.load_balancer
target_group = load_balancer_stack.target_groups.get("app-tg")
```

### Configuration Options

#### Load Balancer Properties

| Property | Type | Description | Default |
|----------|------|-------------|---------|
| `name` | string | Name of the load balancer | `"load-balancer"` |
| `type` | string | Type of load balancer (`"APPLICATION"` or `"NETWORK"`) | `"APPLICATION"` |
| `internet_facing` | boolean | Whether the load balancer is internet-facing | `true` |
| `vpc_id` | string | ID of the VPC for the load balancer | Required |
| `subnets` | string[] | List of subnet IDs for the load balancer | `[]` |
| `security_groups` | string[] | List of security group IDs (for ALB only) | `[]` |
| `deletion_protection` | boolean | Whether deletion protection is enabled | `false` |
| `idle_timeout` | number | Idle timeout in seconds (for ALB only) | `60` |
| `http2_enabled` | boolean | Whether HTTP/2 is enabled (for ALB only) | `true` |
| `certificate_arns` | string[] | List of certificate ARNs for HTTPS listeners | `[]` |
| `ssl_policy` | string | SSL policy for HTTPS listeners | `"ELBSecurityPolicy-2016-08"` |
| `tags` | object | Tags to apply to the load balancer | `{}` |
| `ssm_exports` | object | SSM parameter paths for exporting load balancer resources | `{}` |

#### Target Group Properties

| Property | Type | Description | Default |
|----------|------|-------------|---------|
| `name` | string | Name of the target group | Required |
| `port` | number | Port on which targets receive traffic | `80` |
| `protocol` | string | Protocol for routing traffic (`"HTTP"`, `"HTTPS"`, `"TCP"`, `"TLS"`) | `"HTTP"` or `"TCP"` |
| `target_type` | string | Type of target (`"instance"`, `"ip"`, `"lambda"`) | `"instance"` |
| `health_check` | object | Health check configuration | See below |

#### Health Check Properties

| Property | Type | Description | Default |
|----------|------|-------------|---------|
| `path` | string | Health check path (for HTTP/HTTPS) | `"/"` |
| `port` | string | Health check port | `"traffic-port"` |
| `healthy_threshold` | number | Number of consecutive successful checks | `5` |
| `unhealthy_threshold` | number | Number of consecutive failed checks | `2` |
| `timeout` | number | Timeout in seconds | `5` |
| `interval` | number | Interval between checks in seconds | `30` |
| `healthy_http_codes` | string | HTTP codes for healthy targets | `"200"` |

#### Listener Properties

| Property | Type | Description | Default |
|----------|------|-------------|---------|
| `name` | string | Name of the listener | Required |
| `port` | number | Port on which the load balancer listens | Required |
| `protocol` | string | Listener protocol | `"HTTP"` or `"TCP"` |
| `default_target_group` | string | Name of the default target group | Optional |
| `rules` | object[] | Listener rules (for ALB only) | `[]` |

## SSM Parameter Integration

The load balancer stack supports exporting resources to SSM Parameter Store using the `ssm_exports` configuration:

```json
"ssm_exports": {
  "alb_dns_name": "/{deployment_name}/load-balancer/dns-name",
  "alb_zone_id": "/{deployment_name}/load-balancer/zone-id"
}
```

These parameters can be imported by other stacks using the SSM parameter pattern.

## Route53 Integration

The load balancer can be integrated with Route53 by configuring the `hosted_zone` property:

```json
"hosted_zone": {
  "id": "Z1234567890ABC",
  "name": "example.com",
  "record_names": ["app.example.com", "api.example.com"]
}
```

This will create both A and AAAA records pointing to the load balancer.
