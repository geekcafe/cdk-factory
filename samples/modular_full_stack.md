# Modular Full Stack CDK Application

This is a modular implementation of the `full_stack.py` sample, using the `stack_library` components for better reusability and maintainability.

## Architecture

The modular full stack application consists of the following components:

1. **VPC** - Network infrastructure with public, private, and isolated subnets
2. **Security Groups** - Separate security groups for ALB, application instances, and database
3. **RDS** - PostgreSQL database instance
4. **Auto Scaling Group** - EC2 instances running containerized applications
5. **Load Balancer** - Application Load Balancer with HTTP/HTTPS listeners
6. **Route53** - DNS records for the application

Each component is implemented as a separate, reusable module following the established patterns in the CDK-Factory project.

## Module Structure

Each module follows a consistent pattern:

1. **Configuration Module** - Defines properties and defaults for the resource
2. **Stack Module** - Implements the CDK constructs and resources
3. **Integration** - Modules can be composed together through the workload object

## Usage

To deploy the modular full stack application:

```bash
cdk deploy ModularWebAppStack \
  --context deployment_name=dev \
  --context domain_name=example.com \
  --context hosted_zone_id=Z1234567890 \
  --context certificate_arn=arn:aws:acm:region:account:certificate/12345678-1234-1234-1234-123456789012 \
  --context db_name=appdb \
  --context db_username=admin \
  --context container_image=nginx:latest \
  --context container_port=80
```

## Context Parameters

The following context parameters can be provided:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `deployment_name` | Environment name | `dev` |
| `domain_name` | Domain name for DNS records | `example.com` |
| `hosted_zone_id` | Route53 hosted zone ID | None |
| `certificate_arn` | ACM certificate ARN for HTTPS | None |
| `db_name` | Database name | `appdb` |
| `db_username` | Database username | `admin` |
| `container_image` | Container image to run | `nginx:latest` |
| `container_port` | Container port | `80` |

## Customization

Each module can be customized by modifying its configuration. For example, to change the VPC CIDR:

```python
vpc_config = {
    "name": "app-vpc",
    "cidr": "10.1.0.0/16",  # Modified CIDR
    # Other properties...
}
```

## Benefits Over Original Implementation

1. **Modularity** - Each component can be developed, tested, and deployed independently
2. **Reusability** - Components can be reused across different applications
3. **Maintainability** - Changes to one component don't affect others
4. **Flexibility** - Components can be composed in different ways
5. **Standardization** - Consistent patterns across all components

## Future Enhancements

1. Move configuration to external JSON/YAML files
2. Add support for multiple environments
3. Implement CI/CD pipeline for automated deployments
4. Add monitoring and alerting components
5. Implement cost optimization strategies
