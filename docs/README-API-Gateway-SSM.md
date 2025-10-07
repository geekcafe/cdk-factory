# API Gateway SSM Integration - Documentation Overview

## 📚 Documentation Suite

This documentation suite covers the new API Gateway SSM integration features in CDK Factory:

1. **[API Gateway SSM Integration](./api-gateway-ssm-integration.md)** - Complete feature overview and technical details
2. **[Configuration Reference](./api-gateway-configuration-reference.md)** - Comprehensive configuration options and examples
3. **[Migration Guide](./api-gateway-migration-guide.md)** - Step-by-step migration from existing configurations

## 🚀 Quick Start

### New Project (Recommended Approach)

1. **Create Infrastructure Stack:**
```json
{
  "name": "infrastructure-stack",
  "api_gateway": {
    "name": "main-api",
    "export_to_ssm": true,
    "cognito_authorizer": {
      "user_pool_arn": "arn:aws:cognito-idp:region:account:userpool/pool-id"
    }
  }
}
```

2. **Create Service Stack:**
```json
{
  "name": "user-service-stack",
  "api_gateway": {
    "id_ssm_path": "/my-cool-app/infrastructure-stack/api-gateway/id",
    "root_resource_id_ssm_path": "/my-cool-app/infrastructure-stack/api-gateway/root-resource-id",
    "authorizer": {
      "id_ssm_path": "/my-cool-app/infrastructure-stack/api-gateway/authorizer/id"
    }
  },
  "lambda_functions": [
    {
      "name": "get-users",
      "src": "src/handlers/users",
      "handler": "get_users.handler",
      "api": {
        "method": "GET",
        "route": "/users",
        "authorization_type": "COGNITO"
      }
    }
  ]
}
```

3. **Deploy:**
```bash
cdk deploy infrastructure-stack
cdk deploy user-service-stack
```

### Existing Project (Migration)

1. **Read the [Migration Guide](./api-gateway-migration-guide.md)**
2. **Choose your migration strategy**
3. **Test in development first**
4. **Follow the step-by-step process**

## 🔧 Key Features

### ✅ What's New

- **SSM Parameter Support**: Import/export API Gateway configuration via SSM
- **Fallback Chain**: Direct config → SSM → Environment variables
- **Cross-Stack References**: Share API Gateway across multiple stacks
- **Automatic Export**: Export API Gateway config to SSM when `export_to_ssm: true`
- **Configurable Environment Variables**: Custom environment variable names
- **Comprehensive Testing**: 17 unit tests covering all scenarios

### ✅ What's Maintained

- **Backward Compatibility**: All existing configurations work unchanged
- **Environment Variables**: Existing environment variable support
- **Direct Configuration**: Direct ID/ARN configuration still works
- **All API Gateway Features**: CORS, authorization, custom domains, etc.

## 📋 Configuration Priority

The system uses this priority order for configuration resolution:

1. **Direct Configuration** (highest priority)
   ```json
   {"api_gateway": {"id": "direct-value"}}
   ```

2. **SSM Parameters**
   ```json
   {"api_gateway": {"id_ssm_path": "/path/to/parameter"}}
   ```

3. **Environment Variables** (lowest priority)
   ```json
   {"api_gateway": {"id_env_var": "CUSTOM_API_GATEWAY_ID"}}
   ```

## 🏗️ Architecture Patterns

### Pattern 1: Centralized Infrastructure
```
┌─────────────────────┐
│ Infrastructure Stack │ ──► Creates API Gateway
│ export_to_ssm: true │ ──► Exports to SSM
└─────────────────────┘
           │
           ▼ (SSM Parameters)
┌─────────────────────┐
│   Service Stack A   │ ──► Imports from SSM
└─────────────────────┘
┌─────────────────────┐
│   Service Stack B   │ ──► Imports from SSM
└─────────────────────┘
```

### Pattern 2: Environment-Based
```
┌─────────────────────┐
│   Dev Environment   │ ──► /my-cool-app/dev/api-gateway/*
└─────────────────────┘
┌─────────────────────┐
│ Staging Environment │ ──► /my-cool-app/staging/api-gateway/*
└─────────────────────┘
┌─────────────────────┐
│  Prod Environment   │ ──► /my-cool-app/prod/api-gateway/*
└─────────────────────┘
```

## 🔍 Troubleshooting Quick Reference

| Issue | Solution |
|-------|----------|
| SSM Parameter Not Found | Check parameter exists: `aws ssm get-parameter --name "/path/to/param"` |
| Access Denied | Add SSM permissions to deployment role |
| Missing Root Resource ID | Provide via config, SSM, or environment variable |
| Authorization Failures | Configure `user_pool_id` or `user_pool_arn` |

## 📖 Documentation Structure

### [api-gateway-ssm-integration.md](./api-gateway-ssm-integration.md)
- **Overview**: Feature introduction and benefits
- **Configuration Options**: All available parameters
- **Usage Examples**: Real-world scenarios
- **Deployment Patterns**: Infrastructure-first, environment-based
- **Best Practices**: Security, naming conventions, fallback strategies
- **API Reference**: Method signatures and return values
- **Troubleshooting**: Common issues and solutions

### [api-gateway-configuration-reference.md](./api-gateway-configuration-reference.md)
- **Quick Start**: Basic examples to get started
- **Configuration Hierarchy**: How settings are resolved
- **Lambda Function API Config**: Individual function settings
- **Stack-Level Config**: Shared API Gateway settings
- **Advanced Patterns**: Multi-environment, microservices
- **CORS Configuration**: Function and stack-level CORS
- **Security Configuration**: API keys, usage plans, policies
- **Validation**: Request parameter validation

### [api-gateway-migration-guide.md](./api-gateway-migration-guide.md)
- **Migration Scenarios**: Common migration paths
- **Step-by-Step Process**: Detailed migration instructions
- **Migration Strategies**: Big bang, gradual, parallel
- **Environment-Specific**: Dev, staging, production
- **Rollback Procedures**: How to revert changes
- **Common Issues**: Migration-specific problems
- **Validation Scripts**: Pre and post-migration checks
- **Migration Checklist**: Complete task list

## 🧪 Testing

All features are covered by comprehensive unit tests:

```bash
# Run API Gateway SSM tests
python -m pytest tests/unit/test_api_gateway_ssm_fallback.py -v

# Run all API Gateway tests
python -m pytest tests/unit/test_api_gateway* tests/unit/test_lambda_stack.py -v

# Run full test suite
python -m pytest tests/unit/ -v
```

## 🔐 Security Considerations

### Required IAM Permissions
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter",
        "ssm:GetParameters",
        "ssm:PutParameter"
      ],
      "Resource": "arn:aws:ssm:*:*:parameter/my-cool-app/*"
    }
  ]
}
```

### SSM Parameter Security
- Use SecureString for sensitive values
- Implement least-privilege access
- Use parameter hierarchies for workload
- Enable parameter store logging

## 📊 Migration Impact

### Zero Breaking Changes
- All existing configurations continue to work
- No changes required for current deployments
- New features are opt-in only

### Benefits After Migration
- ✅ Cross-stack API Gateway references
- ✅ Centralized infrastructure management
- ✅ Environment-specific configurations
- ✅ Reduced configuration duplication
- ✅ Improved deployment flexibility

## 🎯 Next Steps

1. **Read the appropriate documentation** for your use case
2. **Test in development** before production migration
3. **Choose your migration strategy** based on project size
4. **Follow the migration checklist** for systematic approach
5. **Monitor deployments** during and after migration

## 📞 Support

For questions or issues:
1. Check the troubleshooting sections in the documentation
2. Review configuration examples
3. Enable debug logging for configuration resolution
4. Verify IAM permissions for SSM access
5. Test configuration in isolation

---

**Documentation Version**: 1.0  
**Last Updated**: September 2025  
**CDK Factory Version**: Compatible with all versions
