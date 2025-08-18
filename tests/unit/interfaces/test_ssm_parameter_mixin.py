"""
Unit tests for the SsmParameterMixin class
"""

import unittest
from unittest.mock import patch, MagicMock, call

import aws_cdk as cdk
from aws_cdk import aws_ssm as ssm
from constructs import Construct

from cdk_factory.interfaces.ssm_parameter_mixin import SsmParameterMixin
from cdk_factory.configurations.deployment import DeploymentConfig


class TestConfig:
    """Test configuration class that mimics BaseConfig behavior"""

    def __init__(self, config_dict):
        self._config = config_dict
        self._ssm_prefix_template = config_dict.get("ssm_prefix_template", None)

    @property
    def ssm_exports(self):
        return self._config.get("ssm_exports", {})

    @property
    def ssm_imports(self):
        return self._config.get("ssm_imports", {})

    @property
    def ssm_parameters(self):
        return self._config.get("ssm_parameters", {})

    def format_ssm_path(
        self, path, resource_type, resource_name, attribute, context=None
    ):
        """Format SSM path using template"""
        # If path starts with '/', it's already a full path
        if path.startswith("/"):
            return path

        # Use the template if available
        if self._ssm_prefix_template:
            context = context or {}
            format_vars = {
                "deployment_name": context.get("deployment_name", "test-deployment"),
                "environment": context.get("environment", "test"),
                "workload_name": context.get("workload_name", "test-workload"),
                "resource_type": resource_type,
                "resource_name": resource_name,
                "attribute": path,
            }

            # Format the template
            formatted_path = self._ssm_prefix_template.format(**format_vars)

            # Ensure the path starts with '/'
            if not formatted_path.startswith("/"):
                formatted_path = f"/{formatted_path}"

            return formatted_path

        # Default format if no template
        return f"/{context.get('environment', 'test')}/{resource_type}/{resource_name}/{attribute}"


class TestSsmParameterMixin(unittest.TestCase):
    """Test cases for SsmParameterMixin"""

    class TestConstruct(Construct, SsmParameterMixin):
        """Test construct that uses SsmParameterMixin"""

        pass

    def setUp(self):
        """Set up test environment"""
        self.app = cdk.App()
        self.construct = self.TestConstruct(self.app, "TestConstruct")

    @patch("aws_cdk.aws_ssm.StringParameter")
    def test_export_ssm_parameter(self, mock_string_parameter):
        """Test export_ssm_parameter method"""
        # Setup
        mock_param = MagicMock()
        mock_string_parameter.return_value = mock_param

        # Execute
        result = self.construct.export_ssm_parameter(
            scope=self.construct,
            id="TestParam",
            value="test-value",
            parameter_name="/test/param",
            description="Test parameter",
        )

        # Assert
        mock_string_parameter.assert_called_once_with(
            scope=self.construct,
            id="TestParam",
            string_value="test-value",
            parameter_name="/test/param",
            description="Test parameter",
            # type=ssm.ParameterType.STRING,
        )
        self.assertEqual(result, mock_param)

    @patch("aws_cdk.aws_ssm.StringParameter.from_string_parameter_name")
    def test_import_ssm_parameter(self, mock_from_string_parameter_name):
        """Test import_ssm_parameter method"""
        # Setup
        mock_param = MagicMock()
        mock_param.string_value = "imported-value"
        mock_from_string_parameter_name.return_value = mock_param

        # Execute
        result = self.construct.import_ssm_parameter(
            scope=self.construct, id="ImportedParam", parameter_name="/test/import"
        )

        # Assert
        mock_from_string_parameter_name.assert_called_once_with(
            self.construct, "ImportedParam", parameter_name="/test/import"
        )
        self.assertEqual(result, "imported-value")

    @patch.object(SsmParameterMixin, "export_ssm_parameters_from_config")
    def test_export_resource_to_ssm_with_full_paths(self, mock_export_ssm_parameters):
        """Test export_resource_to_ssm with full paths"""
        # Setup
        mock_params = {"id": MagicMock(), "name": MagicMock(), "arn": MagicMock()}
        mock_export_ssm_parameters.return_value = mock_params

        resource_values = {
            "id": "res-123",
            "name": "test-resource",
            "arn": "arn:aws:test:region:account:resource/res-123",
        }

        config = TestConfig(
            {
                "ssm_exports": {
                    "id_path": "/test/resource/id",
                    "name_path": "/test/resource/name",
                    "arn_path": "/test/resource/arn",
                }
            }
        )

        # Execute
        result = self.construct.export_resource_to_ssm(
            scope=self.construct,
            resource_values=resource_values,
            config=config,
            resource_name="test-resource",
            resource_type="test",
        )

        # Assert
        self.assertEqual(len(result), 3)
        # Verify the export_ssm_parameters_from_config was called with correct parameters
        mock_export_ssm_parameters.assert_called_once_with(
            scope=self.construct,
            config_dict=resource_values,
            ssm_config={
                "id_path": "/test/resource/id",
                "name_path": "/test/resource/name",
                "arn_path": "/test/resource/arn",
            },
            resource="test-resource-",
        )

    @patch.object(SsmParameterMixin, "export_ssm_parameters_from_config")
    def test_export_resource_to_ssm_with_template(self, mock_export_ssm_parameters):
        """Test export_resource_to_ssm with template-based paths"""
        # Setup
        mock_params = {"id": MagicMock(), "name": MagicMock(), "arn": MagicMock()}
        mock_export_ssm_parameters.return_value = mock_params

        resource_values = {
            "id": "res-123",
            "name": "test-resource",
            "arn": "arn:aws:test:region:account:resource/res-123",
        }

        config = TestConfig(
            {
                "ssm_prefix_template": "/{environment}/{workload_name}/{resource_type}/{attribute}",
                "ssm_exports": {
                    "id_path": "id",
                    "name_path": "name",
                    "arn_path": "arn",
                },
            }
        )

        context = {
            "environment": "dev",
            "workload_name": "my-app",
            "deployment_name": "my-deployment",
        }

        # Execute
        result = self.construct.export_resource_to_ssm(
            scope=self.construct,
            resource_values=resource_values,
            config=config,
            resource_name="test-resource",
            resource_type="test",
            context=context,
        )

        # Assert
        self.assertEqual(len(result), 3)
        # Verify the export_ssm_parameters_from_config was called with correct parameters
        mock_export_ssm_parameters.assert_called_once_with(
            scope=self.construct,
            config_dict=resource_values,
            ssm_config={
                "id_path": "/dev/my-app/test/id",
                "name_path": "/dev/my-app/test/name",
                "arn_path": "/dev/my-app/test/arn",
            },
            resource="test-resource-",
        )

    @patch.object(SsmParameterMixin, "export_ssm_parameters_from_config")
    def test_export_resource_to_ssm_mixed_paths(self, mock_export_ssm_parameters):
        """Test export_resource_to_ssm with mixed full and template paths"""
        # Setup
        mock_params = {"id": MagicMock(), "name": MagicMock(), "arn": MagicMock()}
        mock_export_ssm_parameters.return_value = mock_params

        resource_values = {
            "id": "res-123",
            "name": "test-resource",
            "arn": "arn:aws:test:region:account:resource/res-123",
        }

        config = TestConfig(
            {
                "ssm_prefix_template": "/{environment}/{resource_type}/{attribute}",
                "ssm_exports": {
                    "id_path": "id",
                    "name_path": "/custom/path/name",
                    "arn_path": "arn",
                },
            }
        )

        context = {"environment": "prod"}

        # Execute
        result = self.construct.export_resource_to_ssm(
            scope=self.construct,
            resource_values=resource_values,
            config=config,
            resource_name="test-resource",
            resource_type="test",
            context=context,
        )

        # Assert
        self.assertEqual(len(result), 3)
        # Verify the export_ssm_parameters_from_config was called with correct parameters
        mock_export_ssm_parameters.assert_called_once_with(
            scope=self.construct,
            config_dict=resource_values,
            ssm_config={
                "id_path": "/prod/test/id",
                "name_path": "/custom/path/name",
                "arn_path": "/prod/test/arn",
            },
            resource="test-resource-",
        )

    @patch.object(SsmParameterMixin, "export_ssm_parameters_from_config")
    def test_export_resource_to_ssm_legacy_parameters(self, mock_export_ssm_parameters):
        """Test export_resource_to_ssm with legacy ssm_parameters"""
        # Setup
        mock_params = {"id": MagicMock(), "name": MagicMock()}
        mock_export_ssm_parameters.return_value = mock_params

        resource_values = {"id": "res-123", "name": "test-resource"}

        config = TestConfig(
            {
                "ssm_parameters": {
                    "id_path": "/legacy/resource/id",
                    "name_path": "/legacy/resource/name",
                }
            }
        )

        # Execute
        result = self.construct.export_resource_to_ssm(
            scope=self.construct,
            resource_values=resource_values,
            config=config,
            resource_name="test-resource",
            resource_type="test",
        )

        # Assert
        self.assertEqual(len(result), 2)
        # Verify the export_ssm_parameters_from_config was called with correct parameters
        mock_export_ssm_parameters.assert_called_once_with(
            scope=self.construct,
            config_dict=resource_values,
            ssm_config={
                "id_path": "/legacy/resource/id",
                "name_path": "/legacy/resource/name",
            },
            resource="test-resource-",
        )

    @patch.object(SsmParameterMixin, "export_ssm_parameters_from_config")
    def test_export_resource_to_ssm_with_resource_type_in_template(
        self, mock_export_ssm_parameters
    ):
        """Test export_resource_to_ssm with resource_type in template"""
        # Setup
        mock_params = {"id": MagicMock(), "vpc_id": MagicMock()}
        mock_export_ssm_parameters.return_value = mock_params

        resource_values = {"id": "sg-123", "vpc_id": "vpc-456"}

        config = TestConfig(
            {
                "ssm_prefix_template": "/{environment}/{resource_type}/{resource_name}/{attribute}",
                "ssm_exports": {"id_path": "id", "vpc_id_path": "vpc-id"},
            }
        )

        context = {"environment": "staging"}

        # Execute
        result = self.construct.export_resource_to_ssm(
            scope=self.construct,
            resource_values=resource_values,
            config=config,
            resource_name="web-sg",
            resource_type="security-group",
            context=context,
        )

        # Assert
        self.assertEqual(len(result), 2)
        # Verify the export_ssm_parameters_from_config was called with correct parameters
        mock_export_ssm_parameters.assert_called_once_with(
            scope=self.construct,
            config_dict=resource_values,
            ssm_config={
                "id_path": "/staging/security-group/web-sg/id",
                "vpc_id_path": "/staging/security-group/web-sg/vpc-id",
            },
            resource="web-sg-",
        )


if __name__ == "__main__":
    unittest.main()
