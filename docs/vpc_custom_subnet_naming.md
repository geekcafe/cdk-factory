# VPC Custom Resource Naming

This document describes how to use the custom resource naming features in the CDK Factory VPC stack, including subnet and NAT Gateway naming.

## Overview

By default, AWS CDK creates resources with generic names like "publicSubnet1", "privateSubnet1", and "NatGateway1". The CDK Factory now allows you to customize these resource names to better reflect their purpose in your architecture.

## Configuration

To use custom subnet names, add the following properties to your VPC configuration:

```json
{
  "vpc": {
    "name": "my-vpc",
    "public_subnet_name": "web-tier",
    "private_subnet_name": "app-tier",
    "isolated_subnet_name": "data-tier"
  }
}
```

### Available Properties

| Property | Description | Default Value |
|----------|-------------|---------------|
| `public_subnet_name` | Name for public subnets | "public" |
| `private_subnet_name` | Name for private subnets | "private" |
| `isolated_subnet_name` | Name for isolated subnets | "isolated" |
| `nat_gateway_name` | Name for NAT gateways | "nat" |

## Examples

### Custom Subnet Names

Here's an example of a VPC configuration with custom subnet names:

```json
{
  "vpc": {
    "name": "custom-subnet-vpc",
    "cidr": "10.0.0.0/16",
    "max_azs": 2,
    "public_subnets": true,
    "private_subnets": true,
    "isolated_subnets": true,
    "public_subnet_name": "web-tier",
    "private_subnet_name": "app-tier",
    "isolated_subnet_name": "data-tier",
    "public_subnet_mask": 24,
    "private_subnet_mask": 24,
    "isolated_subnet_mask": 24
  }
}
```

This configuration will create subnets with names like "web-tier1", "app-tier1", and "data-tier1" instead of the default "publicSubnet1", "privateSubnet1", and "isolatedSubnet1".

### NAT Gateway Configuration

You can configure the number of NAT Gateways to be created:

```json
{
  "vpc": {
    "name": "natgw-vpc",
    "cidr": "10.0.0.0/16",
    "max_azs": 2,
    "public_subnets": true,
    "private_subnets": true,
    "nat_gateways": {
      "count": 2
    }
  }
}
```

This configuration will create 2 NAT Gateways, one in each availability zone.

## Impact on Resource Naming

### Subnet Naming

When using custom subnet names, the AWS resources will be named according to the pattern:

```
{deployment-name}/<stage-name>/{vpc-name}/{vpc-name}/{subnet-name}{index}
```

For example, with the subnet configuration above, you might see resources named:
- `my-app-dev-pipeline/Deploy/my-app-dev-vpc/my-app-dev-vpc/custom-subnet-vpc/web-tier1`
- `my-app-dev-pipeline/Deploy/my-app-dev-vpc/my-app-dev-vpc/custom-subnet-vpc/app-tier1`
- `my-app-dev-pipeline/Deploy/my-app-dev-vpc/my-app-dev-vpc/custom-subnet-vpc/data-tier1`


These naming patterns make it easier to identify the purpose of each resource in your AWS Console and CloudFormation templates.
