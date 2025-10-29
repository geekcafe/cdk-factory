# ACM Certificate Management

## Overview

The `acm_stack` module provides dedicated AWS Certificate Manager (ACM) certificate management following the **single responsibility principle**. This separates certificate lifecycle from DNS management.

## Features

- ✅ DNS validation via Route53
- ✅ Subject Alternative Names (SANs) support
- ✅ SSM Parameter Store export
- ✅ CloudFormation outputs
- ✅ Tagging support
- ✅ Backward compatible with Route53Stack certificate creation (deprecated)

## Architecture

```
ACM Stack (Certificate Management)
    ↓ exports certificate ARN to SSM
ALB Stack / CloudFront / API Gateway
    ↑ imports certificate ARN from SSM
```

## Configuration

### Basic Certificate

```json
{
  "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-certificate",
  "module": "acm_stack",
  "enabled": true,
  "dependencies": ["{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-dns"],
  "certificate": {
    "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-cert",
    "domain_name": "example.com",
    "hosted_zone_id": "Z1234567890ABC",
    "ssm_exports": {
      "certificate_arn": "{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/certificate/arn"
    }
  }
}
```

### Wildcard Certificate with SANs

```json
{
  "certificate": {
    "name": "wildcard-cert",
    "domain_name": "example.com",
    "subject_alternative_names": [
      "*.example.com",
      "*.api.example.com"
    ],
    "hosted_zone_id": "Z1234567890ABC",
    "validation_method": "DNS",
    "ssm_exports": {
      "certificate_arn": "/prod/myapp/certificate/arn"
    },
    "tags": {
      "Environment": "prod",
      "ManagedBy": "CDK-Factory"
    }
  }
}
```

## Usage in ALB

### Import Certificate from SSM

```json
{
  "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-alb",
  "module": "load_balancer_library_module",
  "dependencies": [
    "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-certificate"
  ],
  "load_balancer": {
    "ssm": {
      "imports": {
        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id",
        "subnet_ids": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/public-subnet-ids",
        "certificate_arns": ["/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/certificate/arn"]
      }
    }
  }
}
```

### Hardcoded Certificate ARN (Legacy)

```json
{
  "load_balancer": {
    "certificate_arns": [
      "arn:aws:acm:us-east-1:123456789012:certificate/abc-123"
    ]
  }
}
```

## Backward Compatibility

### Route53Stack Certificate Creation (Deprecated)

The Route53Stack still supports certificate creation for backward compatibility, but it's **deprecated**:

```json
{
  "route53": {
    "domain_name": "example.com",
    "create_certificate": true,
    "subject_alternative_names": ["*.example.com"]
  }
}
```

⚠️ **Warning**: You'll see a deprecation warning. Migrate to `acm_stack` for new projects.

## Migration Guide

### From Route53Stack to ACM Stack

**Before:**
```json
{
  "name": "my-dns",
  "module": "route53_stack",
  "route53": {
    "hosted_zone_id": "Z123",
    "domain_name": "example.com",
    "create_certificate": true
  }
}
```

**After:**
```json
{
  "name": "my-certificate",
  "module": "acm_stack",
  "dependencies": ["my-dns"],
  "certificate": {
    "domain_name": "example.com",
    "hosted_zone_id": "Z123",
    "ssm_exports": {
      "certificate_arn": "/prod/myapp/certificate/arn"
    }
  }
}
```

## Validation Methods

- **DNS** (default): Automatic validation via Route53
- **EMAIL**: Manual validation via email (not recommended for automation)

## SSM Export Paths

Convention: `/{environment}/{workload}/certificate/arn`

Example: `/prod/trav-talks/certificate/arn`

## Certificate Transparency Logging

```json
{
  "certificate": {
    "certificate_transparency_logging_preference": "ENABLED"
  }
}
```

## Best Practices

1. ✅ **Use dedicated ACM stack** instead of Route53Stack certificate creation
2. ✅ **Export to SSM** for cross-stack references
3. ✅ **Use wildcard certificates** to cover subdomains
4. ✅ **Add SANs** for multiple domains/subdomains
5. ✅ **Tag certificates** for cost allocation and compliance
6. ✅ **Set dependencies** to ensure certificate is created before ALB/CloudFront

## CloudFormation Outputs

- `CertificateArn`: The ARN of the created certificate
- `DomainName`: Primary domain name

## Troubleshooting

### Certificate Validation Stuck

- Ensure Route53 hosted zone is accessible
- Check DNS propagation: `dig _acme-challenge.example.com TXT`
- Verify hosted zone ID matches the domain

### SSM Import Fails in ALB

- Check certificate stack deployed first (dependencies)
- Verify SSM parameter path matches exactly
- Ensure cross-stack references use correct format

## Related Stacks

- `route53_stack`: DNS records and hosted zone management
- `load_balancer_library_module`: ALB with HTTPS listeners
- `cloudfront_stack`: CloudFront distributions with custom domains
- `api_gateway_stack`: API Gateway custom domains
