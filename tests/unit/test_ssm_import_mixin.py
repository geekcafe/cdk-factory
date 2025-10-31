"""Unit tests for Enhanced SSM Parameter Mixin"""

import unittest
from unittest.mock import MagicMock, patch

import aws_cdk as cdk
from aws_cdk import App
from aws_cdk.assertions import Template

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.interfaces.ssm_parameter_mixin import SsmParameterMixin
from cdk_factory.workload.workload_factory import WorkloadConfig


class TestStack(cdk.Stack, SsmParameterMixin):
    """Test stack that uses Enhanced SSM Parameter Mixin"""
    
    def __init__(self, scope, id, **kwargs):
        # Initialize both parent classes properly
        cdk.Stack.__init__(self, scope, id, **kwargs)
        SsmParameterMixin.__init__(self, **kwargs)


class TestEnhancedSsmParameterMixin(unittest.TestCase):
    """Test cases for Enhanced SSM Parameter Mixin functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.app = App()
        self.stack = TestStack(self.app, "TestStack")
        
        self.workload_config = WorkloadConfig(
            {
                "workload": {
                    "name": "test-workload",
                    "devops": {"name": "test-devops"},
                },
            }
        )
        
        self.deployment_config = DeploymentConfig(
            workload=self.workload_config.dictionary,
            deployment={"name": "test-deployment", "environment": "prod"},
        )

    def test_initialize_ssm_imports(self):
        """Test SSM imports initialization"""
        # Verify the mixin was properly initialized
        self.assertIsInstance(self.stack._ssm_imported_values, dict)
        self.assertEqual(len(self.stack._ssm_imported_values), 0)

    def test_resolve_ssm_path_absolute(self):
        """Test SSM path resolution with absolute paths"""
        absolute_path = "/prod/custom/vpc/id"
        resolved = self.stack._resolve_ssm_path(absolute_path, self.deployment_config)
        self.assertEqual(resolved, absolute_path)

    def test_resolve_ssm_path_relative(self):
        """Test SSM path resolution with relative paths"""
        relative_path = "vpc/id"
        resolved = self.stack._resolve_ssm_path(relative_path, self.deployment_config)
        expected = "/prod/test-workload/vpc/id"
        self.assertEqual(resolved, expected)

    def test_has_ssm_import(self):
        """Test checking if SSM import exists"""
        # Initially empty
        self.assertFalse(self.stack.has_ssm_import("vpc_id"))
        
        # Add a value
        self.stack._ssm_imported_values["vpc_id"] = "vpc-12345"
        
        # Now it should exist
        self.assertTrue(self.stack.has_ssm_import("vpc_id"))

    def test_get_ssm_imported_value(self):
        """Test getting SSM imported values"""
        # Test with default
        result = self.stack.get_ssm_imported_value("missing", "default")
        self.assertEqual(result, "default")
        
        # Test with actual value
        self.stack._ssm_imported_values["test_key"] = "test_value"
        result = self.stack.get_ssm_imported_value("test_key", "default")
        self.assertEqual(result, "test_value")

    def test_process_ssm_imports_no_config_property(self):
        """Test processing SSM imports when config has no ssm_imports property"""
        config = MagicMock()
        del config.ssm_imports  # Remove the property
        
        # Should not raise an error
        self.stack.process_ssm_imports(config, self.deployment_config, "test")
        
        # Should still be empty
        self.assertEqual(len(self.stack._ssm_imported_values), 0)

    def test_process_ssm_imports_empty(self):
        """Test processing empty SSM imports"""
        config = MagicMock()
        config.ssm_imports = {}
        
        # Should not raise an error
        self.stack.process_ssm_imports(config, self.deployment_config, "test")
        
        # Should still be empty
        self.assertEqual(len(self.stack._ssm_imported_values), 0)

    @patch('cdk_factory.interfaces.ssm_parameter_mixin.ssm')
    def test_process_ssm_imports_string_values(self, mock_ssm):
        """Test processing SSM imports with string values"""
        # Mock SSM parameter
        mock_param = MagicMock()
        mock_param.string_value = "vpc-12345"
        mock_ssm.StringParameter.from_string_parameter_name.return_value = mock_param
        
        config = MagicMock()
        config.ssm_imports = {
            "vpc_id": "/prod/app/vpc/id",
            "subnet_ids": "/prod/app/vpc/subnet-ids"
        }
        
        # Process imports
        self.stack.process_ssm_imports(config, self.deployment_config, "test")
        
        # Verify values were imported
        self.assertEqual(len(self.stack._ssm_imported_values), 2)
        self.assertEqual(self.stack._ssm_imported_values["vpc_id"], "vpc-12345")
        self.assertEqual(self.stack._ssm_imported_values["subnet_ids"], "vpc-12345")

    @patch('cdk_factory.interfaces.ssm_parameter_mixin.ssm')
    def test_process_ssm_imports_list_values(self, mock_ssm):
        """Test processing SSM imports with list values"""
        # Mock SSM parameters
        mock_param1 = MagicMock()
        mock_param1.string_value = "sg-12345"
        mock_param2 = MagicMock()
        mock_param2.string_value = "sg-67890"
        mock_ssm.StringParameter.from_string_parameter_name.side_effect = [mock_param1, mock_param2]
        
        config = MagicMock()
        config.ssm_imports = {
            "security_group_ids": ["/prod/app/sg/ecs-id", "/prod/app/sg/alb-id"]
        }
        
        # Process imports
        self.stack.process_ssm_imports(config, self.deployment_config, "test")
        
        # Verify values were imported as list
        self.assertEqual(len(self.stack._ssm_imported_values), 1)
        self.assertIsInstance(self.stack._ssm_imported_values["security_group_ids"], list)
        self.assertEqual(self.stack._ssm_imported_values["security_group_ids"], ["sg-12345", "sg-67890"])

    @patch('cdk_factory.interfaces.ssm_parameter_mixin.ssm')
    def test_process_ssm_imports_relative_paths(self, mock_ssm):
        """Test processing SSM imports with relative paths"""
        # Mock SSM parameter
        mock_param = MagicMock()
        mock_param.string_value = "vpc-12345"
        mock_ssm.StringParameter.from_string_parameter_name.return_value = mock_param
        
        config = MagicMock()
        config.ssm_imports = {
            "vpc_id": "vpc/id",  # Relative path
            "subnet_ids": "vpc/subnet-ids"  # Relative path
        }
        
        # Process imports
        self.stack.process_ssm_imports(config, self.deployment_config, "test")
        
        # Verify SSM was called with resolved absolute paths
        expected_calls = [
            unittest.mock.call(
                self.stack, 
                unittest.mock.ANY,  # construct_id with hash
                "/prod/test-workload/vpc/id"
            ),
            unittest.mock.call(
                self.stack, 
                unittest.mock.ANY,  # construct_id with hash
                "/prod/test-workload/vpc/subnet-ids"
            )
        ]
        
        mock_ssm.StringParameter.from_string_parameter_name.assert_has_calls(expected_calls)

    @patch('cdk_factory.interfaces.ssm_parameter_mixin.ssm')
    def test_process_ssm_imports_error_handling(self, mock_ssm):
        """Test error handling in SSM imports processing"""
        # Mock SSM parameter to raise an exception
        mock_ssm.StringParameter.from_string_parameter_name.side_effect = Exception("SSM Error")
        
        config = MagicMock()
        config.ssm_imports = {
            "vpc_id": "/prod/app/vpc/id"
        }
        
        # Should raise the exception
        with self.assertRaises(Exception) as context:
            self.stack.process_ssm_imports(config, self.deployment_config, "test")
        
        self.assertIn("SSM Error", str(context.exception))


if __name__ == "__main__":
    unittest.main()
