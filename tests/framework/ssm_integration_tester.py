"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

"""
SSM Integration Tester - Specialized testing for SSM parameter integration

Provides comprehensive testing for SSM parameter handling including:
- Configuration validation
- Stack synthesis testing
- SSM parameter creation and reference validation
- Token resolution testing
- Mock SSM value testing
"""

import boto3
from typing import Dict, Any, List, Optional
from unittest.mock import patch, Mock

from .factory_test_base import FactoryTestBase
from cdk_factory.validation.config_validator import ConfigValidator


class SSMIntegrationTester(FactoryTestBase):
    """
    Specialized tester for SSM integration scenarios.
    
    Tests complete SSM integration workflow:
    1. Configuration validation
    2. SSM configuration validation
    3. Stack synthesis
    4. SSM parameter creation
    5. SSM parameter references
    6. Token resolution
    """
    
    def test_complete_ssm_integration(self, module_class, test_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Test complete SSM integration for a module.
        
        This test validates:
        1. Configuration validation
        2. SSM configuration validation
        3. Stack synthesis
        4. SSM parameter creation
        5. SSM parameter references
        6. Token resolution
        
        Args:
            module_class: CDK Factory module class to test
            test_config: Test configuration for the module
            
        Returns:
            Comprehensive test result with all validation details
        """
        test_result = {
            "passed": True,
            "errors": [],
            "template": None,
            "ssm_parameters": [],
            "ssm_references": [],
            "tokens": [],
            "validation_results": {},
            "template_summary": {}
        }
        
        try:
            # 1. Test configuration validation
            validator = ConfigValidator()
            validation_result = validator.validate_module_config(
                module_class.__name__, test_config
            )
            test_result["validation_results"]["config"] = {
                "valid": validation_result.valid,
                "errors": validation_result.errors
            }
            
            if not validation_result.valid:
                test_result["passed"] = False
                test_result["errors"].extend([f"Config validation: {error}" for error in validation_result.errors])
                return test_result
            
            # 2. Test SSM configuration validation
            ssm_validation = validator.validate_ssm_configuration(test_config)
            test_result["validation_results"]["ssm"] = {
                "valid": ssm_validation.valid,
                "errors": ssm_validation.errors
            }
            
            if not ssm_validation.valid:
                test_result["passed"] = False
                test_result["errors"].extend([f"SSM validation: {error}" for error in ssm_validation.errors])
                return test_result
            
            # 3. Test stack synthesis
            template = self.synthesize_stack(module_class, test_config)
            test_result["template"] = template
            
            # Validate template structure
            structure_errors = self.validate_template_structure(template)
            if structure_errors:
                test_result["passed"] = False
                test_result["errors"].extend([f"Template structure: {error}" for error in structure_errors])
                return test_result
            
            # 4. Test SSM parameter creation
            ssm_params = self.extract_ssm_parameters(template)
            test_result["ssm_parameters"] = ssm_params
            
            if len(ssm_params) == 0:
                # Check if SSM exports were expected
                ssm_config = test_config.get("ssm", {})
                if ssm_config.get("exports"):
                    test_result["passed"] = False
                    test_result["errors"].append("No SSM parameters found in template but exports were configured")
                    return test_result
            
            # 5. Test SSM references
            ssm_refs = self.extract_ssm_references(template)
            test_result["ssm_references"] = ssm_refs
            
            # 6. Test token resolution
            tokens = self.extract_cdk_tokens(template)
            test_result["tokens"] = tokens
            
            # Validate token formats
            invalid_tokens = []
            for token in tokens:
                if not token.startswith("${Token["):
                    invalid_tokens.append(token)
            
            if invalid_tokens:
                test_result["passed"] = False
                test_result["errors"].extend([f"Invalid token format: {token}" for token in invalid_tokens])
            
            # Generate template summary
            test_result["template_summary"] = self.get_template_summary(template)
            
            return test_result
            
        except Exception as e:
            test_result["passed"] = False
            test_result["errors"].append(f"Test execution failed: {str(e)}")
            return test_result
    
    def test_ssm_import_resolution(self, module_class, test_config: Dict[str, Any], 
                                 mock_ssm_values: Dict[str, str]) -> Dict[str, Any]:
        """
        Test SSM import resolution with mocked SSM values.
        
        This test verifies that SSM imports are correctly resolved
        when the parameters exist in SSM.
        
        Args:
            module_class: CDK Factory module class to test
            test_config: Test configuration for the module
            mock_ssm_values: Dictionary of mock SSM parameter values
            
        Returns:
            Test result with import resolution validation
        """
        # Mock SSM client
        mock_ssm = Mock()
        mock_ssm.get_parameter.side_effect = lambda Name, WithDecryption=False: {
            "Parameter": {"Value": mock_ssm_values.get(Name, "mock-value")}
        }
        
        with patch('boto3.client', return_value=mock_ssm):
            test_result = self.test_complete_ssm_integration(module_class, test_config)
            
            # Additional validation for import resolution
            if test_result["passed"]:
                # Verify that all expected imports have corresponding references
                expected_imports = list(mock_ssm_values.keys())
                actual_refs = [ref["reference"] for ref in test_result["ssm_references"]]
                
                missing_imports = []
                for expected_import in expected_imports:
                    if not any(expected_import in ref for ref in actual_refs):
                        missing_imports.append(expected_import)
                
                if missing_imports:
                    test_result["passed"] = False
                    test_result["errors"].extend([f"Expected import not found in references: {imp}" for imp in missing_imports])
            
            # Add import resolution details
            test_result["import_resolution"] = {
                "mock_values": mock_ssm_values,
                "expected_imports": list(mock_ssm_values.keys()),
                "actual_references": len(test_result["ssm_references"])
            }
            
            return test_result
    
    def test_token_resolution_with_context(self, module_class, test_config: Dict[str, Any], 
                                         context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Test token resolution with specific CDK context.
        
        This test verifies that CDK tokens resolve correctly
        when specific context is provided.
        
        Args:
            module_class: CDK Factory module class to test
            test_config: Test configuration for the module
            context: CDK context variables
            
        Returns:
            Test result with token resolution validation
        """
        try:
            template = self.synthesize_stack_with_context(module_class, context)
            
            # Extract and validate tokens
            tokens = self.extract_cdk_tokens(template)
            
            # Verify tokens are present and properly formatted
            token_validation = {
                "tokens_found": len(tokens),
                "valid_tokens": 0,
                "invalid_tokens": [],
                "token_types": {}
            }
            
            for token in tokens:
                if token.startswith("${Token[") and token.endswith("]}"):
                    token_validation["valid_tokens"] += 1
                else:
                    token_validation["invalid_tokens"].append(token)
                
                # Analyze token types
                if "resolve(" in token:
                    token_validation["token_types"]["resolve"] = token_validation["token_types"].get("resolve", 0) + 1
                elif "GetAtt" in token:
                    token_validation["token_types"]["get_att"] = token_validation["token_types"].get("get_att", 0) + 1
                else:
                    token_validation["token_types"]["other"] = token_validation["token_types"].get("other", 0) + 1
            
            # Validate template structure
            structure_errors = self.validate_template_structure(template)
            
            return {
                "passed": len(token_validation["invalid_tokens"]) == 0 and len(structure_errors) == 0,
                "template": template,
                "token_validation": token_validation,
                "structure_errors": structure_errors,
                "template_summary": self.get_template_summary(template)
            }
            
        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
                "context": context
            }
    
    def test_ssm_path_validation(self, test_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Test SSM path validation in configuration.
        
        Args:
            test_config: Configuration to validate
            
        Returns:
            Validation result for SSM paths
        """
        validator = ConfigValidator()
        ssm_validation = validator.validate_ssm_configuration(test_config)
        
        # Extract SSM paths for detailed analysis
        ssm_config = test_config.get("ssm", {})
        imports = ssm_config.get("imports", {})
        exports = ssm_config.get("exports", {})
        
        path_analysis = {
            "import_paths": [],
            "export_paths": [],
            "invalid_paths": [],
            "valid_paths": []
        }
        
        # Analyze import paths
        for key, value in imports.items():
            if isinstance(value, list):
                for path in value:
                    path_analysis["import_paths"].append({"key": f"{key}[]", "path": path})
            else:
                path_analysis["import_paths"].append({"key": key, "path": value})
        
        # Analyze export paths
        for key, value in exports.items():
            path_analysis["export_paths"].append({"key": key, "path": value})
        
        # Validate each path
        all_paths = path_analysis["import_paths"] + path_analysis["export_paths"]
        for path_info in all_paths:
            path = path_info["path"]
            if self._is_valid_ssm_path(path):
                path_analysis["valid_paths"].append(path_info)
            else:
                path_analysis["invalid_paths"].append(path_info)
        
        return {
            "validation": {
                "valid": ssm_validation.valid,
                "errors": ssm_validation.errors
            },
            "path_analysis": path_analysis,
            "total_paths": len(all_paths),
            "valid_count": len(path_analysis["valid_paths"]),
            "invalid_count": len(path_analysis["invalid_paths"])
        }
    
    def test_cross_stack_ssm_integration(self, producer_configs: List[Dict[str, Any]], 
                                       consumer_configs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Test SSM integration across multiple stacks.
        
        Args:
            producer_configs: List of configurations that export SSM parameters
            consumer_configs: List of configurations that import SSM parameters
            
        Returns:
            Cross-stack integration test result
        """
        result = {
            "passed": True,
            "errors": [],
            "producer_results": {},
            "consumer_results": {},
            "cross_validation": {
                "exports_found": [],
                "imports_found": [],
                "unmatched_imports": [],
                "unmatched_exports": []
            }
        }
        
        # Test producer stacks
        for i, config in enumerate(producer_configs):
            module_name = config.get("module", f"producer-{i}")
            # This would need the actual module class
            # For now, just validate configuration
            validation = self.test_ssm_path_validation(config)
            result["producer_results"][f"producer-{i}"] = validation
            
            if not validation["validation"]["valid"]:
                result["passed"] = False
                result["errors"].extend([f"Producer {i}: {error}" for error in validation["validation"]["errors"]])
        
        # Test consumer stacks
        for i, config in enumerate(consumer_configs):
            module_name = config.get("module", f"consumer-{i}")
            validation = self.test_ssm_path_validation(config)
            result["consumer_results"][f"consumer-{i}"] = validation
            
            if not validation["validation"]["valid"]:
                result["passed"] = False
                result["errors"].extend([f"Consumer {i}: {error}" for error in validation["validation"]["errors"]])
        
        # Cross-validate imports and exports
        all_exports = []
        all_imports = []
        
        for config in producer_configs:
            ssm_config = config.get("ssm", {})
            exports = ssm_config.get("exports", {})
            for key, path in exports.items():
                all_exports.append({"stack": config.get("name"), "key": key, "path": path})
        
        for config in consumer_configs:
            ssm_config = config.get("ssm", {})
            imports = ssm_config.get("imports", {})
            for key, path in imports.items():
                if isinstance(path, list):
                    for p in path:
                        all_imports.append({"stack": config.get("name"), "key": f"{key}[]", "path": p})
                else:
                    all_imports.append({"stack": config.get("name"), "key": key, "path": path})
        
        result["cross_validation"]["exports_found"] = all_exports
        result["cross_validation"]["imports_found"] = all_imports
        
        # Find unmatched imports
        for import_info in all_imports:
            import_path = import_info["path"]
            matching_exports = [exp for exp in all_exports if exp["path"] == import_path]
            if not matching_exports:
                result["cross_validation"]["unmatched_imports"].append(import_info)
        
        # Find unmatched exports
        for export_info in all_exports:
            export_path = export_info["path"]
            matching_imports = [imp for imp in all_imports if imp["path"] == export_path]
            if not matching_imports:
                result["cross_validation"]["unmatched_exports"].append(export_info)
        
        # Determine if cross-stack integration is valid
        if result["cross_validation"]["unmatched_imports"]:
            result["passed"] = False
            result["errors"].append(f"Unmatched imports: {len(result['cross_validation']['unmatched_imports'])}")
        
        return result
    
    def _is_valid_ssm_path(self, path: str) -> bool:
        """
        Check if SSM path follows standard format.
        
        Args:
            path: SSM parameter path to validate
            
        Returns:
            True if path is valid, False otherwise
        """
        if not path or not isinstance(path, str):
            return False
        
        if not path.startswith("/"):
            return False
        
        segments = path.split("/")
        if len(segments) < 4:
            return False
        
        # Check for template variables
        if "{{ENVIRONMENT}}" not in path and "{{WORKLOAD_NAME}}" not in path:
            # If no template variables, check for actual values
            if segments[1] not in ["dev", "staging", "prod", "test"]:
                return False
        
        return True
    
    def create_comprehensive_test_report(self, test_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Create comprehensive test report from multiple test results.
        
        Args:
            test_results: List of test results from various tests
            
        Returns:
            Comprehensive test report
        """
        report = {
            "summary": {
                "total_tests": len(test_results),
                "passed_tests": 0,
                "failed_tests": 0,
                "total_errors": 0
            },
            "test_details": [],
            "common_errors": {},
            "performance_metrics": {},
            "recommendations": []
        }
        
        all_errors = []
        
        for result in test_results:
            if result.get("passed", False):
                report["summary"]["passed_tests"] += 1
            else:
                report["summary"]["failed_tests"] += 1
            
            errors = result.get("errors", [])
            report["summary"]["total_errors"] += len(errors)
            all_errors.extend(errors)
            
            # Extract performance metrics if available
            if "template_summary" in result:
                summary = result["template_summary"]
                for key, value in summary.items():
                    if key not in report["performance_metrics"]:
                        report["performance_metrics"][key] = []
                    report["performance_metrics"][key].append(value)
        
        # Analyze common errors
        error_counts = {}
        for error in all_errors:
            # Extract error type (first word before colon)
            error_type = error.split(":")[0] if ":" in error else error
            error_counts[error_type] = error_counts.get(error_type, 0) + 1
        
        report["common_errors"] = error_counts
        
        # Generate recommendations
        if report["summary"]["failed_tests"] > 0:
            report["recommendations"].append("Review failed tests and fix configuration issues")
        
        if report["summary"]["total_errors"] > 0:
            report["recommendations"].append("Address common error patterns identified")
        
        # Performance recommendations
        if "total_resources" in report["performance_metrics"]:
            avg_resources = sum(report["performance_metrics"]["total_resources"]) / len(report["performance_metrics"]["total_resources"])
            if avg_resources > 50:
                report["recommendations"].append("Consider optimizing resource usage - high resource count detected")
        
        return report
