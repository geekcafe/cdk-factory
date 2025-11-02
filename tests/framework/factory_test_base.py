"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

"""
Factory Test Base - Base testing infrastructure for all CDK Factory tests

Provides the foundation for testing CDK Factory modules from the factory level
through to CloudFormation template output, including proper token resolution.
"""

import os
import tempfile
import json
from typing import Dict, Any, List, Optional
from unittest.mock import Mock

import aws_cdk as cdk
from aws_cdk.assertions import Template
from aws_cdk.cx_api import CloudAssembly
from constructs import Construct

from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig
from cdk_factory.validation.config_validator import ConfigValidator


class FactoryTestBase:
    """
    Base class for all CDK Factory tests.
    
    Provides:
    - Standard test environment setup
    - Mock configurations for testing
    - Stack synthesis and template extraction
    - Template validation utilities
    - SSM parameter and reference extraction
    - CDK token analysis
    """
    
    def setUp(self):
        """Setup test environment with mocked configurations."""
        # Setup test CDK app with context for testing
        self.app = cdk.App(context={
            "cdk-factory": {
                "testing": True,
                "environment": "test"
            },
            "ENVIRONMENT": "test",
            "WORKLOAD_NAME": "test-workload",
            "AWS_REGION": "us-east-1"
        })
        
        # Setup test configurations
        self.test_deployment = self._create_test_deployment()
        self.test_workload = self._create_test_workload()
        self.test_stack_config = self._create_test_stack_config()
        
        # Setup validator
        self.validator = ConfigValidator()
        
        # Setup temporary directory for synthesis
        self.temp_dir = tempfile.mkdtemp()
        
        # Setup environment variables for template resolution
        os.environ["ENVIRONMENT"] = "test"
        os.environ["WORKLOAD_NAME"] = "test-workload"
        os.environ["AWS_REGION"] = "us-east-1"
    
    def tearDown(self):
        """Cleanup test environment."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def _create_test_deployment(self) -> DeploymentConfig:
        """Create test deployment configuration."""
        workload = {
            "name": "test-workload",
            "environment": "test",
            "owner": "test-team",
            "description": "Test workload for CDK Factory testing"
        }
        deployment = {
            "name": "test-deployment",
            "environment": "test",
            "region": "us-east-1",
            "profile": "test",
            "workload_name": "test-workload"
        }
        return DeploymentConfig(workload, deployment)
    
    def _create_test_workload(self) -> WorkloadConfig:
        """Create test workload configuration."""
        return WorkloadConfig({
            "name": "test-workload",
            "environment": "test",
            "owner": "test-team",
            "description": "Test workload for CDK Factory testing",
            "devops": {
                "aws_account": "123456789012",
                "region": "us-east-1"
            }
        })
    
    def _create_test_stack_config(self, config_dict: Dict[str, Any] = None) -> StackConfig:
        """Create test stack configuration."""
        default_workload = {
            "name": "test-workload",
            "environment": "test",
            "owner": "test-team",
            "description": "Test workload for CDK Factory testing"
        }
        
        default_config = {
            "name": "test-stack",
            "module": "test_module",
            "enabled": True,
            "dependencies": []
        }
        
        if config_dict:
            default_config.update(config_dict)
        
        return StackConfig(default_config, default_workload)
    
    def synthesize_stack(self, stack_class, config_override: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Synthesize stack and return CloudFormation template.
        
        Args:
            stack_class: The CDK Factory stack class to test
            config_override: Configuration overrides for testing
            
        Returns:
            CloudFormation template dictionary
        """
        # Create stack configuration
        stack_config = self._create_test_stack_config(config_override)
        
        # Instantiate stack
        stack = stack_class(self.app, "TestStack")
        
        # Build stack
        stack.build(stack_config, self.test_deployment, self.test_workload)
        
        # Synthesize to CloudFormation template
        cloud_assembly = self.app.synth()
        stack_template = cloud_assembly.get_stack_by_name("TestStack").template
        
        return stack_template
    
    def synthesize_stack_with_context(self, stack_class, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Synthesize stack with specific CDK context (for token testing).
        
        Args:
            stack_class: Stack class to synthesize
            context: CDK context variables
            
        Returns:
            CloudFormation template dictionary
        """
        app = cdk.App(context=context)
        stack = stack_class(app, "TestStack")
        stack.build(self.test_stack_config, self.test_deployment, self.test_workload)
        
        cloud_assembly = app.synth()
        return cloud_assembly.get_stack_by_name("TestStack").template
    
    def validate_template_structure(self, template: Dict[str, Any]) -> List[str]:
        """
        Validate basic CloudFormation template structure.
        
        Args:
            template: CloudFormation template to validate
            
        Returns:
            List of validation errors
        """
        errors = []
        
        # Check required sections
        # Note: AWSTemplateFormatVersion is optional in modern CDK templates
        if "Resources" not in template:
            errors.append("Missing Resources section")
        
        # Check that resources exist
        if len(template.get("Resources", {})) == 0:
            errors.append("No resources found in template")
        
        # Check for valid CloudFormation structure
        if not isinstance(template.get("Resources"), dict):
            errors.append("Resources section must be a dictionary")
        
        if not isinstance(template.get("Outputs"), dict):
            errors.append("Outputs section must be a dictionary")
        
        return errors
    
    def extract_ssm_parameters(self, template: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract SSM parameters from CloudFormation template.
        
        Args:
            template: CloudFormation template
            
        Returns:
            List of SSM parameter information
        """
        ssm_params = []
        
        resources = template.get("Resources", {})
        for resource_id, resource in resources.items():
            if resource.get("Type") == "AWS::SSM::Parameter":
                properties = resource.get("Properties", {})
                ssm_params.append({
                    "logical_id": resource_id,
                    "properties": properties,
                    "parameter_name": properties.get("Name", ""),
                    "parameter_value": properties.get("Value", ""),
                    "description": properties.get("Description", ""),
                    "type": properties.get("Type", "String"),
                    "resource_id": resource_id
                })
        
        return ssm_params
    
    def extract_ssm_references(self, template: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract SSM parameter references from CloudFormation template.
        
        Args:
            template: CloudFormation template
            
        Returns:
            List of SSM reference information
        """
        ssm_refs = []
        
        def find_refs(obj, path=""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    current_path = f"{path}.{key}" if path else key
                    
                    # Check for SSM parameter references
                    if key == "Ref" and isinstance(value, str):
                        # This could be an SSM parameter reference
                        if "ssm" in value.lower() or "parameter" in value.lower():
                            ssm_refs.append({
                                "path": current_path,
                                "reference": value,
                                "type": "Ref"
                            })
                    
                    # Check for Fn::GetAtt with SSM parameters
                    elif key == "Fn::GetAtt" and isinstance(value, list):
                        if len(value) >= 2 and "ssm" in value[0].lower():
                            ssm_refs.append({
                                "path": current_path,
                                "reference": value,
                                "type": "Fn::GetAtt"
                            })
                    
                    # Check for Fn::ImportValue with SSM parameters
                    elif key == "Fn::ImportValue" and isinstance(value, str):
                        if "ssm" in value.lower():
                            ssm_refs.append({
                                "path": current_path,
                                "reference": value,
                                "type": "Fn::ImportValue"
                            })
                    
                    find_refs(value, current_path)
            
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    find_refs(item, f"{path}[{i}]")
        
        find_refs(template)
        return ssm_refs
    
    def extract_cdk_tokens(self, template: Dict[str, Any]) -> List[str]:
        """
        Extract CDK tokens from CloudFormation template.
        
        Args:
            template: CloudFormation template
            
        Returns:
            List of CDK tokens found
        """
        tokens = []
        
        def find_tokens(obj):
            if isinstance(obj, str):
                # CDK tokens typically start with ${Token[
                if obj.startswith("${Token["):
                    tokens.append(obj)
                # Also look for other CDK token patterns
                elif "${" in obj and "[" in obj and "]" in obj:
                    tokens.append(obj)
            elif isinstance(obj, dict):
                for value in obj.values():
                    find_tokens(value)
            elif isinstance(obj, list):
                for item in obj:
                    find_tokens(item)
        
        find_tokens(template)
        return tokens
    
    def extract_resource_types(self, template: Dict[str, Any]) -> Dict[str, int]:
        """
        Extract and count resource types from template.
        
        Args:
            template: CloudFormation template
            
        Returns:
            Dictionary mapping resource types to counts
        """
        resource_types = {}
        
        resources = template.get("Resources", {})
        for resource in resources.values():
            resource_type = resource.get("Type", "Unknown")
            resource_types[resource_type] = resource_types.get(resource_type, 0) + 1
        
        return resource_types
    
    def validate_ssm_integration(self, template: Dict[str, Any], 
                                expected_imports: List[str] = None, 
                                expected_exports: List[str] = None) -> Dict[str, Any]:
        """
        Validate SSM integration in template.
        
        Args:
            template: CloudFormation template
            expected_imports: List of expected SSM import parameter names
            expected_exports: List of expected SSM export parameter names
            
        Returns:
            Validation result with detailed information
        """
        result = {
            "valid": True,
            "errors": [],
            "ssm_parameters": [],
            "ssm_references": [],
            "missing_imports": [],
            "missing_exports": [],
            "token_analysis": {}
        }
        
        # Extract SSM parameters and references
        ssm_params = self.extract_ssm_parameters(template)
        ssm_refs = self.extract_ssm_references(template)
        
        result["ssm_parameters"] = ssm_params
        result["ssm_references"] = ssm_refs
        
        # Check for expected exports (SSM parameters created)
        if expected_exports:
            exported_names = [param["parameter_name"] for param in ssm_params]
            for expected_export in expected_exports:
                if not any(expected_export in name for name in exported_names):
                    result["missing_exports"].append(expected_export)
                    result["valid"] = False
        
        # Check for expected imports (SSM parameter references)
        if expected_imports:
            # This is more complex as imports become CloudFormation references
            # We'll check that we have the expected number of references
            if len(ssm_refs) < len(expected_imports):
                result["missing_imports"] = expected_imports[len(ssm_refs):]
                result["valid"] = False
        
        # Analyze tokens
        tokens = self.extract_cdk_tokens(template)
        result["token_analysis"] = {
            "total_tokens": len(tokens),
            "token_types": self._analyze_token_types(tokens),
            "tokens": tokens[:10]  # First 10 tokens for inspection
        }
        
        return result
    
    def _analyze_token_types(self, tokens: List[str]) -> Dict[str, int]:
        """Analyze types of CDK tokens found."""
        token_types = {}
        
        for token in tokens:
            if "Token[" in token:
                token_types["CDK_Token"] = token_types.get("CDK_Token", 0) + 1
            elif "resolve(" in token:
                token_types["Resolve_Token"] = token_types.get("Resolve_Token", 0) + 1
            else:
                token_types["Other"] = token_types.get("Other", 0) + 1
        
        return token_types
    
    def create_test_config_with_ssm(self, module_name: str, 
                                   imports: Dict[str, Any] = None, 
                                   exports: Dict[str, Any] = None,
                                   additional_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Create test configuration with SSM imports/exports.
        
        Args:
            module_name: Name of the module being tested
            imports: SSM imports configuration
            exports: SSM exports configuration
            additional_config: Additional configuration for the module
            
        Returns:
            Complete test configuration
        """
        config = {
            "name": "test-{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-stack",
            "module": module_name,
            "enabled": True,
            "dependencies": []
        }
        
        if imports or exports:
            config["ssm"] = {}
            if imports:
                config["ssm"]["imports"] = imports
            if exports:
                config["ssm"]["exports"] = exports
        
        if additional_config:
            config.update(additional_config)
        
        return config
    
    def assert_template_valid(self, template: Dict[str, Any], 
                            expected_resources: int = None,
                            expected_ssm_params: int = None,
                            expected_outputs: int = None):
        """
        Assert that template meets basic validation criteria.
        
        Args:
            template: CloudFormation template to validate
            expected_resources: Expected number of resources
            expected_ssm_params: Expected number of SSM parameters
            expected_outputs: Expected number of outputs
        """
        # Validate basic structure
        errors = self.validate_template_structure(template)
        assert len(errors) == 0, f"Template structure validation failed: {errors}"
        
        # Check resource counts
        resources = template.get("Resources", {})
        if expected_resources is not None:
            assert len(resources) == expected_resources, f"Expected {expected_resources} resources, got {len(resources)}"
        
        # Check SSM parameters
        ssm_params = self.extract_ssm_parameters(template)
        if expected_ssm_params is not None:
            assert len(ssm_params) == expected_ssm_params, f"Expected {expected_ssm_params} SSM parameters, got {len(ssm_params)}"
        
        # Check outputs
        outputs = template.get("Outputs", {})
        if expected_outputs is not None:
            assert len(outputs) == expected_outputs, f"Expected {expected_outputs} outputs, got {len(outputs)}"
    
    def get_template_summary(self, template: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get a summary of the CloudFormation template.
        
        Args:
            template: CloudFormation template
            
        Returns:
            Template summary information
        """
        resources = template.get("Resources", {})
        outputs = template.get("Outputs", {})
        ssm_params = self.extract_ssm_parameters(template)
        ssm_refs = self.extract_ssm_references(template)
        tokens = self.extract_cdk_tokens(template)
        
        return {
            "total_resources": len(resources),
            "total_outputs": len(outputs),
            "ssm_parameters": len(ssm_params),
            "ssm_references": len(ssm_refs),
            "cdk_tokens": len(tokens),
            "resource_types": self.extract_resource_types(template),
            "has_parameters": "Parameters" in template,
            "has_mappings": "Mappings" in template,
            "has_conditions": "Conditions" in template
        }


class MockDeploymentConfig:
    """Mock deployment configuration for testing."""
    
    def __init__(self, config_dict: Dict[str, Any] = None):
        self.dictionary = config_dict or {
            "name": "test-deployment",
            "environment": "test",
            "region": "us-east-1",
            "workload_name": "test-workload"
        }
        self.environment = self.dictionary.get("environment", "test")
        self.workload_name = self.dictionary.get("workload_name", "test-workload")
        self.region = self.dictionary.get("region", "us-east-1")
    
    def build_resource_name(self, base_name: str) -> str:
        """Build resource name with standard pattern."""
        return f"{self.workload_name}-{self.environment}-{base_name}"


class MockWorkloadConfig:
    """Mock workload configuration for testing."""
    
    def __init__(self, config_dict: Dict[str, Any] = None):
        self.dictionary = config_dict or {
            "name": "test-workload",
            "environment": "test",
            "owner": "test-team"
        }
        self.name = self.dictionary.get("name", "test-workload")
        self.environment = self.dictionary.get("environment", "test")
        self.owner = self.dictionary.get("owner", "test-team")
