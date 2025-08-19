# Auto Scaling Group Configuration

This directory contains sample configurations and deployment scripts for creating AWS Auto Scaling Groups using the CDK-Factory framework.

## Configuration Options

The Auto Scaling Group configuration supports the following parameters:

### Basic Configuration

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | String | Yes | Name of the Auto Scaling Group |
| `vpc_id` | String | Yes | ID of the VPC where the ASG will be deployed |
| `instance_type` | String | Yes | EC2 instance type (e.g., `t3.micro`, `m5.large`) |
| `min_capacity` | Number | Yes | Minimum number of instances |
| `max_capacity` | Number | Yes | Maximum number of instances |
| `desired_capacity` | Number | Yes | Desired number of instances |
| `subnet_group_name` | String | Yes | Subnet group name (e.g., `private`, `public`) |
| `security_group_ids` | Array | Yes | List of security group IDs |

### Health Check and Scaling Configuration

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `health_check_type` | String | No | Health check type (`EC2` or `ELB`), defaults to `EC2` |
| `health_check_grace_period` | Number | No | Grace period in seconds, defaults to `300` |
| `cooldown` | Number | No | Cooldown period in seconds, defaults to `300` |
| `termination_policies` | Array | No | List of termination policies (e.g., `OldestInstance`, `Default`) |

### Instance Configuration

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ami_id` | String | No | Specific AMI ID to use |
| `ami_type` | String | No | AMI type if no specific ID is provided (`amazon-linux-2023`, `amazon-linux-2`) |
| `managed_policies` | Array | No | List of managed IAM policies to attach to the instance role |
| `detailed_monitoring` | Boolean | No | Enable detailed CloudWatch monitoring |
| `block_devices` | Array | No | List of block device configurations |

#### Block Device Configuration

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `device_name` | String | Yes | Device name (e.g., `/dev/xvda`) |
| `volume_size` | Number | Yes | Volume size in GB |
| `volume_type` | String | No | Volume type (e.g., `gp3`, `io1`), defaults to `gp3` |
| `delete_on_termination` | Boolean | No | Whether to delete the volume on instance termination, defaults to `true` |
| `encrypted` | Boolean | No | Whether to encrypt the volume, defaults to `true` |

### Container Configuration

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `container_config` | Object | No | Container configuration for running applications |
| `container_config.ecr` | Object | No | ECR configuration for pulling container images |
| `container_config.ecr.account_id` | String | No | ECR account ID, defaults to the current account |
| `container_config.ecr.region` | String | No | ECR region, defaults to the current region |
| `container_config.ecr.repo` | String | Yes | ECR repository name |
| `container_config.ecr.tag` | String | No | Image tag, defaults to `latest` |
| `container_config.database` | Object | No | Database configuration for the container |
| `container_config.database.secret_arn` | String | Yes | ARN of the database credentials secret |
| `container_config.port` | Number | No | Port to expose from the container, defaults to `8080` |
| `container_config.run_command` | String | No | Custom command to run the container |

### User Data and Scaling Policies

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_data_commands` | Array | No | List of commands to run in the user data script |
| `scaling_policies` | Array | No | List of scaling policy configurations |
| `update_policy` | Object | No | Update policy configuration |

#### Scaling Policy Configuration

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | String | Yes | Name of the scaling policy |
| `type` | String | No | Type of scaling policy (`target_tracking` or `step`), defaults to `target_tracking` |
| `metric_name` | String | Yes | CloudWatch metric name (e.g., `CPUUtilization`) |
| `statistic` | String | No | Statistic to use (e.g., `Average`, `Sum`), defaults to `Average` |
| `period` | Number | No | Period in seconds, defaults to `60` |
| `steps` | Array | Yes | List of scaling steps |

#### Scaling Step Configuration

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `lower` | Number | No | Lower bound of the step |
| `upper` | Number | No | Upper bound of the step |
| `change` | Number | Yes | Capacity change for the step |

#### Update Policy Configuration

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `min_instances_in_service` | Number | No | Minimum instances in service during update, defaults to `1` |
| `max_batch_size` | Number | No | Maximum batch size for updates, defaults to `1` |
| `pause_time` | Number | No | Pause time between updates in seconds, defaults to `300` |

### Tagging and Exports

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tags` | Object | No | Tags to apply to the Auto Scaling Group |
| `ssm_exports` | Object | No | SSM parameter exports configuration |

## Sample Configurations

This directory includes the following sample configurations:

1. `auto_scaling_sample.json` - A comprehensive configuration with all options
2. `config_min.json` - A minimal configuration with just the essential parameters

## Deployment

To deploy an Auto Scaling Group using these configurations:

```bash
# Deploy using the comprehensive configuration
cdk deploy --app "python deploy_auto_scaling.py" --context vpc_id=vpc-12345678 --context deployment_name=dev

# Deploy using the minimal configuration
cdk deploy --app "python deploy_auto_scaling.py" --context vpc_id=vpc-12345678 --context deployment_name=dev --context config_file=config_min.json
```

## Integration with Load Balancers

To integrate your Auto Scaling Group with a Load Balancer, you can use the following pattern:

```python
# Get the target group from the load balancer stack
target_group = load_balancer_stack.target_groups.get("app-tg")

# Attach the Auto Scaling Group to the target group
if target_group and auto_scaling_stack.auto_scaling_group:
    auto_scaling_stack.auto_scaling_group.attach_to_application_target_group(target_group)
```

This will register instances in your Auto Scaling Group as targets for the Load Balancer.
