"""Unit tests for VPC Provider Mixin"""

import unittest
from unittest.mock import MagicMock, patch

import aws_cdk as cdk
from aws_cdk import App, aws_ec2 as ec2
from aws_cdk.assertions import Template

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.interfaces.vpc_provider_mixin import VPCProviderMixin
from cdk_factory.workload.workload_factory import WorkloadConfig


class TestStack(cdk.Stack, VPCProviderMixin):
    """Test stack that uses VPC Provider Mixin"""
    
    def __init__(self, scope, id, **kwargs):
        super().__init__(scope, id, **kwargs)
        self._initialize_vpc_cache()


class TestVPCProviderMixin(unittest.TestCase):
    """Test cases for VPC Provider Mixin functionality"""

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

    def test_initialize_vpc_cache(self):
        """Test VPC cache initialization"""
        # Verify the mixin was properly initialized
        self.assertIsNone(self.stack._vpc)

    @patch('cdk_factory.interfaces.vpc_provider_mixin.ec2.Vpc.from_vpc_attributes')
    def test_resolve_vpc_from_ssm_imports(self, mock_from_vpc_attrs):
        """Test VPC resolution from SSM imports"""
        # Mock VPC creation
        mock_vpc = MagicMock()
        mock_from_vpc_attrs.return_value = mock_vpc
        
        # Set up SSM imported values
        self.stack._ssm_imported_values = {"vpc_id": "vpc-12345"}
        
        # Create mock configs
        config = MagicMock()
        workload = MagicMock()
        
        # Resolve VPC
        result = self.stack.resolve_vpc(config, self.deployment_config, workload)
        
        # Verify VPC was created from SSM imports
        self.assertEqual(result, mock_vpc)
        mock_from_vpc_attrs.assert_called_once()
        
        # Check the VPC attributes
        call_args = mock_from_vpc_attrs.call_args
        vpc_attrs = call_args[1]  # kwargs
        self.assertEqual(vpc_attrs["vpc_id"], "vpc-12345")
        self.assertEqual(vpc_attrs["availability_zones"], ["us-east-1a", "us-east-1b"])

    @patch('cdk_factory.interfaces.vpc_provider_mixin.ec2.Vpc.from_vpc_attributes')
    def test_resolve_vpc_from_ssm_with_subnets(self, mock_from_vpc_attrs):
        """Test VPC resolution from SSM imports with subnet support"""
        # Mock VPC creation
        mock_vpc = MagicMock()
        mock_from_vpc_attrs.return_value = mock_vpc
        
        # Set up SSM imported values with subnets
        self.stack._ssm_imported_values = {
            "vpc_id": "vpc-12345",
            "subnet_ids": "subnet-1,subnet-2"
        }
        
        # Create mock configs
        config = MagicMock()
        workload = MagicMock()
        
        # Resolve VPC
        result = self.stack.resolve_vpc(config, self.deployment_config, workload)
        
        # Verify VPC was created with actual subnet IDs
        call_args = mock_from_vpc_attrs.call_args
        vpc_attrs = call_args[1]  # kwargs
        self.assertEqual(vpc_attrs["public_subnet_ids"], ["subnet-1", "subnet-2"])

    @patch('cdk_factory.interfaces.vpc_provider_mixin.ec2.Vpc.from_lookup')
    def test_resolve_vpc_from_config(self, mock_from_lookup):
        """Test VPC resolution from config-level VPC ID"""
        # Mock VPC creation
        mock_vpc = MagicMock()
        mock_from_lookup.return_value = mock_vpc
        
        # Create mock configs
        config = MagicMock()
        config.vpc_id = "vpc-config-123"
        workload = MagicMock()
        
        # Resolve VPC
        result = self.stack.resolve_vpc(config, self.deployment_config, workload)
        
        # Verify VPC was created from config with unique name
        mock_from_lookup.assert_called_once_with(self.stack, "TestStack-VPC", vpc_id="vpc-config-123")

    @patch('cdk_factory.interfaces.vpc_provider_mixin.ec2.Vpc.from_lookup')
    def test_resolve_vpc_from_workload(self, mock_from_lookup):
        """Test VPC resolution from workload-level VPC ID"""
        # Mock VPC creation
        mock_vpc = MagicMock()
        mock_from_lookup.return_value = mock_vpc
        
        # Create mock configs
        config = MagicMock()
        config.vpc_id = None  # No config-level VPC
        workload = MagicMock()
        workload.vpc_id = "vpc-workload-456"
        
        # Resolve VPC
        result = self.stack.resolve_vpc(config, self.deployment_config, workload)
        
        # Verify VPC was created from workload with unique name
        self.assertEqual(result, mock_vpc)
        mock_from_lookup.assert_called_once_with(self.stack, "TestStack-VPC", vpc_id="vpc-workload-456")

    def test_resolve_vpc_not_found_error(self):
        """Test VPC resolution when no VPC configuration is found"""
        # Create mock configs with no VPC
        config = MagicMock()
        config.vpc_id = None
        workload = MagicMock()
        workload.vpc_id = None
        workload.name = "test-workload"
        
        # Should raise ValueError with descriptive message
        with self.assertRaises(ValueError) as context:
            self.stack.resolve_vpc(config, self.deployment_config, workload)
        
        error_message = str(context.exception)
        self.assertIn("VPC is not defined", error_message)
        self.assertIn("SSM import", error_message)
        self.assertIn("config level", error_message)
        self.assertIn("workload level", error_message)
        self.assertIn("test-workload", error_message)

    def test_resolve_vpc_cached_result(self):
        """Test that resolved VPC is cached"""
        # Set up cached VPC
        cached_vpc = MagicMock()
        self.stack._vpc = cached_vpc
        
        # Create mock configs
        config = MagicMock()
        workload = MagicMock()
        
        # Resolve VPC - should return cached result
        result = self.stack.resolve_vpc(config, self.deployment_config, workload)
        
        # Should return cached VPC without calling any creation methods
        self.assertEqual(result, cached_vpc)

    @patch('cdk_factory.interfaces.vpc_provider_mixin.ec2.Vpc.from_vpc_attributes')
    def test_resolve_vpc_custom_availability_zones(self, mock_from_vpc_attrs):
        """Test VPC resolution with custom availability zones"""
        # Mock VPC creation
        mock_vpc = MagicMock()
        mock_from_vpc_attrs.return_value = mock_vpc
        
        # Set up SSM imported values
        self.stack._ssm_imported_values = {"vpc_id": "vpc-12345"}
        
        # Create mock configs
        config = MagicMock()
        workload = MagicMock()
        
        # Custom AZ list
        custom_azs = ["us-west-2a", "us-west-2b", "us-west-2c"]
        
        # Resolve VPC
        result = self.stack.resolve_vpc(config, self.deployment_config, workload, custom_azs)
        
        # Verify VPC was created with custom AZs
        call_args = mock_from_vpc_attrs.call_args
        vpc_attrs = call_args[1]  # kwargs
        self.assertEqual(vpc_attrs["availability_zones"], custom_azs)

    @patch('cdk_factory.interfaces.vpc_provider_mixin.ec2.Vpc.from_vpc_attributes')
    def test_get_vpc_property(self, mock_from_vpc_attrs):
        """Test the standard VPC property implementation"""
        # Mock VPC creation
        mock_vpc = MagicMock()
        mock_from_vpc_attrs.return_value = mock_vpc
        
        # Set up SSM imported values
        self.stack._ssm_imported_values = {"vpc_id": "vpc-12345"}
        
        # Create mock configs
        config = MagicMock()
        workload = MagicMock()
        
        # Use the property-style method
        result = self.stack.get_vpc_property(config, self.deployment_config, workload)
        
        # Verify VPC was resolved
        self.assertEqual(result, mock_vpc)

    def test_get_vpc_property_not_initialized(self):
        """Test VPC property when stack is not properly initialized"""
        # Create a new stack without proper initialization
        class BadStack(cdk.Stack, VPCProviderMixin):
            pass
        
        bad_stack = BadStack(self.app, "BadStack")
        config = MagicMock()
        workload = MagicMock()
        
        # Should raise AttributeError
        with self.assertRaises(AttributeError) as context:
            bad_stack.get_vpc_property(config, self.deployment_config, workload)
        
        error_message = str(context.exception)
        self.assertIn("no attribute '_vpc'", error_message)


if __name__ == "__main__":
    unittest.main()
