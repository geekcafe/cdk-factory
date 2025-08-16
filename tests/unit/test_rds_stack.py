"""
Unit tests for the RDS Stack
"""

import unittest
from unittest.mock import patch, MagicMock

import aws_cdk as cdk
from aws_cdk import App
from aws_cdk import aws_rds as rds
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_secretsmanager as secretsmanager

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.rds.rds_stack import RdsStack
from cdk_factory.workload.workload_factory import WorkloadConfig


def test_rds_stack_minimal():
    """Test RDS stack with minimal configuration"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "rds": {
                "name": "test-db",
                "engine": "postgres",
                "engine_version": "14",
                "instance_class": "t3.micro",
                "database_name": "testdb",
                "username": "admin",
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
    )
    
    # Create and build the stack
    stack = RdsStack(app, "TestRdsStack")
    
    # Mock VPC and security group
    mock_vpc = MagicMock()
    mock_vpc.vpc_id = "vpc-12345"
    mock_security_group = MagicMock()
    mock_security_group.security_group_id = "sg-12345"
    
    # Mock the workload object with VPC
    dummy_workload.vpc = mock_vpc
    
    # Mock the _create_db_instance method
    mock_db_instance = MagicMock()
    mock_secret = MagicMock()
    mock_secret.secret_arn = "arn:aws:secretsmanager:region:account:secret:test-secret"
    mock_db_instance.secret = mock_secret
    mock_db_instance.db_instance_endpoint_address = "test-db.example.com"
    mock_db_instance.db_instance_endpoint_port = "5432"
    
    # Mock the _get_vpc method
    with patch.object(RdsStack, "_get_vpc", return_value=mock_vpc) as mock_get_vpc:
        # Mock the _create_db_instance method
        with patch.object(RdsStack, "_create_db_instance", return_value=mock_db_instance) as mock_create_db:
            with patch.object(RdsStack, "_add_outputs") as mock_add_outputs:
                # Build the stack
                stack.build(stack_config, deployment, dummy_workload)
                
                # Verify the RDS config was correctly loaded
                assert stack.rds_config.name == "test-db"
                assert stack.rds_config.engine == "postgres"
                assert stack.rds_config.engine_version == "14"
                assert stack.rds_config.instance_class == "t3.micro"
                assert stack.rds_config.database_name == "testdb"
                assert stack.rds_config.username == "admin"
                
                # Verify the DB instance was created
                assert stack.db_instance is mock_db_instance
                
                # Verify methods were called
                mock_get_vpc.assert_called_once()
                mock_create_db.assert_called_once()
                mock_add_outputs.assert_called_once()


def test_rds_stack_full_config():
    """Test RDS stack with full configuration"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "rds": {
                "name": "full-db",
                "engine": "mysql",
                "engine_version": "8.0",
                "instance_class": "r5.large",
                "database_name": "fulldb",
                "username": "dbadmin",
                "secret_name": "full-db-credentials",
                "allocated_storage": 100,
                "storage_encrypted": True,
                "multi_az": True,
                "subnet_group_name": "isolated",
                "security_group_ids": ["sg-12345"],
                "deletion_protection": True,
                "backup_retention": 14,
                "cloudwatch_logs_exports": ["error", "general", "slowquery"],
                "enable_performance_insights": True,
                "performance_insights_retention": 7,
                "removal_policy": "snapshot",
                "existing_instance_id": "",
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
    stack = RdsStack(app, "FullRdsStack")
    
    # Mock VPC and security group
    mock_vpc = MagicMock()
    mock_vpc.vpc_id = "vpc-12345"
    mock_security_group = MagicMock()
    mock_security_group.security_group_id = "sg-12345"
    
    # Mock the workload object with VPC
    dummy_workload.vpc = mock_vpc
    
    # Mock the _create_db_instance method
    mock_db_instance = MagicMock()
    mock_secret = MagicMock()
    mock_secret.secret_arn = "arn:aws:secretsmanager:region:account:secret:full-db-credentials"
    mock_db_instance.secret = mock_secret
    mock_db_instance.db_instance_endpoint_address = "full-db.example.com"
    mock_db_instance.db_instance_endpoint_port = "3306"
    
    # Mock the _get_vpc method
    with patch.object(RdsStack, "_get_vpc", return_value=mock_vpc) as mock_get_vpc:
        # Mock the _get_security_groups method
        with patch.object(RdsStack, "_get_security_groups", return_value=[mock_security_group]) as mock_get_sg:
            # Mock the _create_db_instance method
            with patch.object(RdsStack, "_create_db_instance", return_value=mock_db_instance) as mock_create_db:
                # Mock the _add_outputs method
                with patch.object(RdsStack, "_add_outputs") as mock_add_outputs:
                    # Build the stack
                    stack.build(stack_config, deployment, dummy_workload)
                    
                    # Verify the RDS config was correctly loaded
                    assert stack.rds_config.name == "full-db"
                    assert stack.rds_config.engine == "mysql"
                    assert stack.rds_config.engine_version == "8.0"
                    assert stack.rds_config.instance_class == "r5.large"
                    assert stack.rds_config.database_name == "fulldb"
                    assert stack.rds_config.username == "dbadmin"
                    assert stack.rds_config.secret_name == "full-db-credentials"
                    assert stack.rds_config.allocated_storage == 100
                    assert stack.rds_config.storage_encrypted is True
                    assert stack.rds_config.multi_az is True
                    assert stack.rds_config.subnet_group_name == "isolated"
                    assert stack.rds_config.security_group_ids == ["sg-12345"]
                    assert stack.rds_config.deletion_protection is True
                    assert stack.rds_config.backup_retention == 14
                    assert stack.rds_config.cloudwatch_logs_exports == ["error", "general", "slowquery"]
                    assert stack.rds_config.enable_performance_insights is True
                    assert stack.rds_config.removal_policy == "snapshot"
                    assert stack.rds_config.tags == {"Environment": "test", "Project": "cdk-factory"}
                    
                    # Verify the DB instance was created
                    assert stack.db_instance is mock_db_instance
                    
                    # Verify methods were called
                    mock_get_vpc.assert_called_once()
                    mock_get_sg.assert_called_once()
                    mock_create_db.assert_called_once()
                    mock_add_outputs.assert_called_once()


def test_rds_import_existing():
    """Test RDS stack with importing an existing instance"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "rds": {
                "name": "imported-db",
                "existing_instance_id": "database-1",
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
    )
    
    # Create and build the stack
    stack = RdsStack(app, "ImportRdsStack")
    
    # Mock VPC
    mock_vpc = MagicMock()
    mock_vpc.vpc_id = "vpc-12345"
    
    # Mock the workload object with VPC
    dummy_workload.vpc = mock_vpc
    
    # Mock the _import_existing_db method
    mock_db_instance = MagicMock()
    mock_db_instance.db_instance_endpoint_address = "imported-db.example.com"
    mock_db_instance.db_instance_endpoint_port = "5432"
    
    # Mock the _get_vpc method
    with patch.object(RdsStack, "_get_vpc", return_value=mock_vpc) as mock_get_vpc:
        # Mock the _import_existing_db method
        with patch.object(RdsStack, "_import_existing_db", return_value=mock_db_instance) as mock_import_db:
            with patch.object(RdsStack, "_add_outputs") as mock_add_outputs:
                # Build the stack
                stack.build(stack_config, deployment, dummy_workload)
                
                # Verify the RDS config was correctly loaded
                assert stack.rds_config.name == "imported-db"
                assert stack.rds_config.existing_instance_id == "database-1"
                
                # Verify the DB instance was imported
                assert stack.db_instance is mock_db_instance
                
                # Verify methods were called
                mock_get_vpc.assert_called_once()
                mock_import_db.assert_called_once()
                mock_add_outputs.assert_called_once()
