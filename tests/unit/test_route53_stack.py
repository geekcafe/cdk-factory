"""
Unit tests for the Route53 Stack
"""

import unittest
from unittest.mock import patch, MagicMock

import aws_cdk as cdk
from aws_cdk import App
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_certificatemanager as acm

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.route53.route53_stack import Route53Stack
from cdk_factory.workload.workload_factory import WorkloadConfig


def test_route53_stack_minimal():
    """Test Route53 stack with minimal configuration"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "route53": {
                "domain_name": "example.com",
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
    )
    
    # Create and build the stack
    stack = Route53Stack(app, "TestRoute53Stack")
    
    # Mock the hosted zone
    mock_hosted_zone = MagicMock()
    mock_hosted_zone.hosted_zone_id = "Z1234567890"
    mock_hosted_zone.zone_name = "example.com"
    
    # Mock the methods
    with patch.object(Route53Stack, "_get_or_create_hosted_zone", return_value=mock_hosted_zone) as mock_create_zone:
        with patch.object(Route53Stack, "_create_dns_records") as mock_create_dns:
            with patch.object(Route53Stack, "_add_outputs") as mock_add_outputs:
                # Build the stack
                stack.build(stack_config, deployment, dummy_workload)
                
                # Verify the Route53 config was correctly loaded
                assert stack.route53_config.domain_name == "example.com"
                assert stack.route53_config.create_hosted_zone is False  # Default value
                assert stack.route53_config.create_certificate is False  # Default value
                
                # Verify the hosted zone was created
                assert stack.hosted_zone is mock_hosted_zone
                
                # Verify methods were called
                mock_create_zone.assert_called_once()
                mock_create_dns.assert_called_once()
                mock_add_outputs.assert_called_once()


def test_route53_stack_full_config():
    """Test Route53 stack with full configuration"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "route53": {
                "domain_name": "full-example.com",
                "create_hosted_zone": True,
                "create_certificate": True,
                "validation_method": "DNS",
                "hosted_zone_id": "",
                "certificate_arn": "",
                "aliases": [
                    {
                        "name": "app.full-example.com",
                        "target_type": "alb",
                        "target_value": "arn:aws:elasticloadbalancing:region:account:loadbalancer/app/my-alb/1234567890"
                    }
                ],
                "cname_records": [
                    {
                        "name": "www.full-example.com",
                        "record_value": "app.full-example.com",
                        "ttl": 300
                    }
                ],
                "tags": {
                    "Environment": "test",
                    "Project": "cdk-factory"
                }
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
    )
    
    # Create and build the stack
    stack = Route53Stack(app, "FullRoute53Stack")
    
    # Mock the resources
    mock_hosted_zone = MagicMock()
    mock_hosted_zone.hosted_zone_id = "Z0987654321"
    mock_hosted_zone.zone_name = "full-example.com"
    
    mock_certificate = MagicMock()
    mock_certificate.certificate_arn = "arn:aws:acm:region:account:certificate/12345678-1234-1234-1234-123456789012"
    
    # Mock the methods
    with patch.object(Route53Stack, "_get_or_create_hosted_zone", return_value=mock_hosted_zone) as mock_create_zone:
        with patch.object(Route53Stack, "_create_certificate", return_value=mock_certificate) as mock_create_cert:
            with patch.object(Route53Stack, "_create_dns_records") as mock_create_dns:
                with patch.object(Route53Stack, "_add_outputs") as mock_add_outputs:
                        # Build the stack
                        stack.build(stack_config, deployment, dummy_workload)
                        
                        # Verify the Route53 config was correctly loaded
                        assert stack.route53_config.domain_name == "full-example.com"
                        assert stack.route53_config.create_hosted_zone is True
                        assert stack.route53_config.create_certificate is True
                        assert stack.route53_config.validation_method == "DNS"
                        assert len(stack.route53_config.aliases) == 1
                        assert stack.route53_config.aliases[0]["name"] == "app.full-example.com"
                        assert len(stack.route53_config.cname_records) == 1
                        assert stack.route53_config.cname_records[0]["name"] == "www.full-example.com"
                        assert stack.route53_config.tags == {"Environment": "test", "Project": "cdk-factory"}
                        
                        # Verify the resources were created
                        assert stack.hosted_zone is mock_hosted_zone
                        assert stack.certificate is mock_certificate
                        
                        # Verify methods were called
                        mock_create_zone.assert_called_once()
                        mock_create_cert.assert_called_once()
                        mock_create_dns.assert_called_once()
                        mock_add_outputs.assert_called_once()


def test_route53_stack_import_existing():
    """Test Route53 stack with importing existing resources"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "route53": {
                "domain_name": "imported-example.com",
                "create_hosted_zone": False,
                "create_certificate": False,
                "hosted_zone_id": "Z1111111111",
                "certificate_arn": "arn:aws:acm:region:account:certificate/abcdef12-3456-7890-abcd-ef1234567890",
                "aliases": [
                    {
                        "name": "api.imported-example.com",
                        "target_type": "apigateway",
                        "target_value": "arn:aws:apigateway:region::/restapis/abcdef1234/stages/prod"
                    }
                ]
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
    )
    
    # Create and build the stack
    stack = Route53Stack(app, "ImportRoute53Stack")
    
    # Mock the resources
    mock_hosted_zone = MagicMock()
    mock_hosted_zone.hosted_zone_id = "Z1111111111"
    mock_hosted_zone.zone_name = "imported-example.com"
    
    mock_certificate = MagicMock()
    mock_certificate.certificate_arn = "arn:aws:acm:region:account:certificate/abcdef12-3456-7890-abcd-ef1234567890"
    
    # Mock the methods
    with patch.object(Route53Stack, "_get_or_create_hosted_zone", return_value=mock_hosted_zone) as mock_import_zone:
        with patch.object(acm.Certificate, "from_certificate_arn", return_value=mock_certificate) as mock_import_cert:
            with patch.object(Route53Stack, "_create_dns_records") as mock_create_dns:
                with patch.object(Route53Stack, "_add_outputs") as mock_add_outputs:
                    # Set up certificate before building the stack
                    def side_effect(*args, **kwargs):
                        stack.certificate = mock_certificate
                    mock_add_outputs.side_effect = side_effect
                    # Build the stack
                    stack.build(stack_config, deployment, dummy_workload)
                    
                    # Verify the Route53 config was correctly loaded
                    assert stack.route53_config.domain_name == "imported-example.com"
                    assert stack.route53_config.create_hosted_zone is False
                    assert stack.route53_config.create_certificate is False
                    assert stack.route53_config.hosted_zone_id == "Z1111111111"
                    assert stack.route53_config.certificate_arn == "arn:aws:acm:region:account:certificate/abcdef12-3456-7890-abcd-ef1234567890"
                    assert len(stack.route53_config.aliases) == 1
                    assert stack.route53_config.aliases[0]["name"] == "api.imported-example.com"
                    
                    # Verify the resources were imported
                    assert stack.hosted_zone is mock_hosted_zone
                    assert stack.certificate is mock_certificate
                    
                    # Verify methods were called
                    mock_import_zone.assert_called_once()
                    mock_create_dns.assert_called_once()
                    mock_add_outputs.assert_called_once()
