# New Unit Tests - ACM Stack & Load Balancer SSM Imports

## Test Coverage Summary

### ✅ ACM Stack Tests (`test_acm_stack.py`) - **9 tests, all passing**

Tests for the new dedicated ACM (AWS Certificate Manager) stack module:

1. **test_basic_certificate_creation** - Validates basic ACM certificate creation with DNS validation
2. **test_certificate_with_sans** - Tests certificates with Subject Alternative Names (SANs)
3. **test_certificate_ssm_export** - Verifies certificate ARN export to SSM Parameter Store
4. **test_certificate_with_tags** - Tests custom tagging on certificates
5. **test_certificate_without_hosted_zone_no_validation** - Tests certificate without DNS validation
6. **test_acm_config_domain_name_required** - Validates domain_name is required
7. **test_acm_config_subject_alternative_names** - Tests SAN configuration
8. **test_acm_config_default_ssm_exports** - Tests default SSM export paths
9. **test_acm_stack_module_exists** - Validates module can be imported

### ✅ ACM Config Tests (`test_acm_config.py`) - **21 tests, all passing**

Comprehensive tests for AcmConfig class:

1. **test_domain_name_required** - Domain name validation
2. **test_domain_name_provided** - Domain name property
3. **test_name_default** - Default certificate name
4. **test_name_custom** - Custom certificate name
5. **test_subject_alternative_names** - SANs property
6. **test_alternate_names_backward_compatibility** - Backward compatibility with alternate_names
7. **test_subject_alternative_names_priority** - SANs takes priority over alternate_names
8. **test_subject_alternative_names_default_empty** - Default empty SANs
9. **test_hosted_zone_id** - Hosted zone ID property
10. **test_hosted_zone_id_none** - None when not provided
11. **test_hosted_zone_name** - Hosted zone name property
12. **test_validation_method_default** - Default DNS validation
13. **test_validation_method_custom** - Custom validation method
14. **test_certificate_transparency_logging_preference** - CT logging preference
15. **test_certificate_transparency_logging_preference_none** - None when not set
16. **test_ssm_exports_custom** - Custom SSM export paths
17. **test_ssm_exports_default_with_deployment** - Default SSM paths with deployment
18. **test_ssm_exports_empty_without_deployment** - Empty exports without deployment
19. **test_tags_empty_default** - Default empty tags
20. **test_tags_custom** - Custom tags
21. **test_full_configuration** - Full configuration with all properties

### ✅ Load Balancer SSM Import Tests (`test_load_balancer_ssm_imports.py`) - **7 tests, all passing**

Tests for ALB SSM import features (subnet IDs, certificates, security groups):

**Status**: ✅ **All tests passing!**

**Fixes Applied**:
1. Added `ssm_exports` and `ssm_parameters` properties to LoadBalancerConfig to prevent attempting to export imported SSM values
2. Updated test assertions to check actual CloudFormation template structure instead of wildcard parameter name matching

**Tests included**:
1. **test_alb_subnet_ids_ssm_import_with_fn_split** - ✅ Verifies Fn::Split usage for comma-separated subnet IDs
2. **test_alb_certificate_arns_ssm_import** - ✅ Verifies certificate ARN import from SSM
3. **test_alb_multiple_ssm_imports** - ✅ Verifies multiple SSM imports (VPC, subnets, security groups, certificates)
4. **test_alb_vpc_from_attributes_with_dummy_subnets** - ✅ Verifies VPC import with token resolution
5. **test_alb_certificate_fallback_to_config** - ✅ Verifies fallback to hardcoded certificate ARNs
6. **test_alb_subnet_ids_token_detection** - ✅ Verifies CDK token detection for subnet IDs
7. **test_alb_security_groups_ssm_import** - ✅ Verifies multiple security group imports

## Running the Tests

```bash
# Run all new tests (37 tests - all passing)
.venv/bin/python -m pytest tests/unit/test_acm_*.py tests/unit/test_load_balancer_ssm_imports.py -v

# Run ACM tests only (30 tests)
.venv/bin/python -m pytest tests/unit/test_acm_*.py -v

# Run LoadBalancer SSM tests only (7 tests)
.venv/bin/python -m pytest tests/unit/test_load_balancer_ssm_imports.py -v

# Run with coverage
.venv/bin/python -m pytest tests/unit/test_acm_*.py tests/unit/test_load_balancer_ssm_imports.py \
  --cov=cdk_factory.stack_library.acm \
  --cov=cdk_factory.configurations.resources.acm \
  --cov=cdk_factory.configurations.resources.load_balancer
```

## Test Artifacts Created

1. `/tests/unit/test_acm_stack.py` - ACM stack synthesis and CloudFormation template tests (9 tests)
2. `/tests/unit/test_acm_config.py` - AcmConfig class configuration tests (21 tests)
3. `/tests/unit/test_load_balancer_ssm_imports.py` - ALB SSM import feature tests (7 tests)

## Features Tested

### ACM Stack
- ✅ Certificate creation with DNS validation
- ✅ Route53 hosted zone integration
- ✅ Subject Alternative Names (wildcard certificates)
- ✅ SSM Parameter Store exports
- ✅ CloudFormation outputs
- ✅ Custom tagging
- ✅ Configuration validation

### Load Balancer SSM Imports
- ✅ SSM imports for VPC ID
- ✅ SSM imports for subnet IDs with Fn::Split
- ✅ SSM imports for security group IDs (including multiple groups)
- ✅ SSM imports for certificate ARNs
- ✅ VPC from_attributes with token resolution
- ✅ Token detection and CloudFormation escape hatch
- ✅ Fallback to hardcoded values when SSM not configured

## Test Results

```
============================== 37 passed in 3.93s ==============================
```

**100% passing!** All tests pass successfully with comprehensive coverage of:
- ACM certificate lifecycle management
- Configuration validation and backward compatibility
- SSM import/export separation
- CloudFormation template generation
- LoadBalancer SSM integration patterns
