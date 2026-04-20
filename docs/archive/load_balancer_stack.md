# Load Balancer Stack

The Load Balancer Stack provides a reusable pattern for creating AWS Application Load Balancers (ALB) and Network Load Balancers (NLB) with comprehensive configuration options.

## Features

- **Multi-type Support**: Application Load Balancer (ALB) and Network Load Balancer (NLB)
- **Target Groups**: Configurable target groups with health checks
- **Listeners**: HTTP/HTTPS listeners with SSL/TLS support
- **DNS Integration**: Route 53 DNS records and SSL certificate management
- **SSM Parameter Export**: Automatic export of load balancer resources to SSM Parameter Store
- **Security Groups**: Configurable security group attachment (ALB only)
- **Listener Rules**: Advanced routing rules for ALB listeners

## Configuration

### Basic Configuration

```json
{
  "load_balancer": {
    "name": "my-alb",
    "type": "APPLICATION",
    "vpc_id": "vpc-12345678",
    "subnets": ["subnet-12345678", "subnet-87654321"],
    "security_groups": ["sg-12345678"],
    "internet_facing": true,
    "deletion_protection": false,
    "idle_timeout": 60,
    "http2_enabled": true
  }
}
```

### Target Groups Configuration

```json
{
  "load_balancer": {
    "target_groups": [
      {
        "name": "web-servers",
        "port": 80,
        "protocol": "HTTP",
        "target_type": "INSTANCE",
        "health_check": {
          "path": "/health",
          "port": "traffic-port",
          "healthy_threshold": 2,
          "unhealthy_threshold": 5,
          "timeout": 5,
          "interval": 30,
          "healthy_http_codes": "200,204"
        }
      },
      {
        "name": "api-servers",
        "port": 8080,
        "protocol": "HTTP",
        "target_type": "INSTANCE",
        "health_check": {
          "path": "/api/health",
          "port": 8080
        }
      }
    ]
  }
}
```

### Listeners Configuration

```json
{
  "load_balancer": {
    "listeners": [
      {
        "name": "http-listener",
        "port": 80,
        "protocol": "HTTP",
        "default_target_group": "web-servers",
        "rules": [
          {
            "priority": 100,
            "path_patterns": ["/api/*"],
            "target_group": "api-servers"
          },
          {
            "priority": 200,
            "host_headers": ["api.example.com"],
            "target_group": "api-servers"
          }
        ]
      },
      {
        "name": "https-listener",
        "port": 443,
        "protocol": "HTTPS",
        "default_target_group": "web-servers",
        "ssl_policy": "ELBSecurityPolicy-TLS-1-2-2017-01"
      }
    ]
  }
}
```

### DNS and SSL Configuration

```json
{
  "load_balancer": {
    "hosted_zone": {
      "id": "Z1234567890ABC",
      "name": "example.com",
      "record_names": ["www.example.com", "api.example.com"]
    },
    "certificate_arns": [
      "arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012"
    ],
    "ssl_cert_arn": "arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012"
  }
}
```

## SSM Parameter Export

The Load Balancer Stack automatically exports key resources to SSM Parameter Store for use by other stacks. The exported parameters follow this naming pattern:

### Exported Parameters

- **ALB DNS Name**: `/{deployment_name}/load-balancer/{lb_name}/alb_dns_name`
- **ALB Zone ID**: `/{deployment_name}/load-balancer/{lb_name}/alb_zone_id`
- **ALB ARN**: `/{deployment_name}/load-balancer/{lb_name}/alb_arn`
- **Target Group ARNs**: `/{deployment_name}/load-balancer/{lb_name}/target_group_{target_group_name}_arn`

### SSM Export Configuration

Configure which parameters to export using the `ssm_exports` property:

```json
{
  "load_balancer": {
    "ssm_exports": {
      "alb_dns_name_path": "/my-app/load-balancer/dns-name",
      "alb_arn_path": "/my-app/load-balancer/arn",
      "target_group_web_servers_arn_path": "/my-app/load-balancer/web-tg-arn",
      "target_group_api_servers_arn_path": "/my-app/load-balancer/api-tg-arn"
    }
  }
}
```

## Network Load Balancer Example

```json
{
  "load_balancer": {
    "name": "my-nlb",
    "type": "NETWORK",
    "vpc_id": "vpc-12345678",
    "subnets": ["subnet-12345678", "subnet-87654321"],
    "internet_facing": true,
    "target_groups": [
      {
        "name": "tcp-servers",
        "port": 80,
        "protocol": "TCP",
        "target_type": "INSTANCE",
        "health_check": {
          "port": "traffic-port",
          "healthy_threshold": 3,
          "unhealthy_threshold": 3,
          "timeout": 6,
          "interval": 30
        }
      }
    ],
    "listeners": [
      {
        "name": "tcp-listener",
        "port": 80,
        "protocol": "TCP",
        "default_target_group": "tcp-servers"
      }
    ]
  }
}
```

## Integration with Auto Scaling Groups

The Load Balancer Stack is designed to work seamlessly with the Auto Scaling Stack through SSM parameters. The target group ARNs are automatically exported and can be imported by Auto Scaling Groups for automatic instance registration.

**Key Integration Point**: The target group name in the Load Balancer configuration becomes part of the SSM parameter name (`target_group_{name}_arn`), which the Auto Scaling Stack uses to attach instances to the correct target groups.

## Advanced Features

### Listener Rules

ALB listeners support advanced routing rules:

```json
{
  "rules": [
    {
      "priority": 100,
      "path_patterns": ["/api/*", "/v1/*"],
      "target_group": "api-servers"
    },
    {
      "priority": 200,
      "host_headers": ["admin.example.com"],
      "http_headers": {
        "X-Forwarded-Proto": ["https"]
      },
      "target_group": "admin-servers"
    },
    {
      "priority": 300,
      "query_strings": [
        {"key": "version", "value": "v2"}
      ],
      "target_group": "v2-servers"
    }
  ]
}
```

### Health Check Configuration

Comprehensive health check options:

```json
{
  "health_check": {
    "path": "/health",
    "port": "traffic-port",
    "healthy_threshold": 2,
    "unhealthy_threshold": 5,
    "timeout": 5,
    "interval": 30,
    "healthy_http_codes": "200,204,301,302"
  }
}
```

## Stack Registration

The Load Balancer Stack is registered with multiple aliases:
- `alb_library_module`
- `alb_stack`
- `load_balancer_library_module`
- `load_balancer_stack`

## Dependencies

- **VPC**: Must be provided via `load_balancer.vpc_id` or `workload.vpc_id`
- **Subnets**: Required for load balancer placement
- **Security Groups**: Required for ALB (optional for NLB)

## Best Practices

1. **Target Group Naming**: Use descriptive names as they become part of SSM parameter paths
2. **Health Checks**: Configure appropriate health check paths and thresholds
3. **SSL/TLS**: Use ACM certificates and appropriate SSL policies
4. **DNS**: Leverage Route 53 integration for automatic DNS management
5. **SSM Parameters**: Use consistent naming patterns for cross-stack integration
