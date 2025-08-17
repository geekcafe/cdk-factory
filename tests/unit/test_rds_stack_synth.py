"""Tests for RDS stack synthesis"""
import pytest
from unittest.mock import patch
from aws_cdk import App
from aws_cdk import aws_ec2 as ec2

from cdk_factory.stack_library.rds.rds_stack import RdsStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig
from utils.synth_test_utils import (
    get_resources_by_type,
    assert_resource_count,
    assert_has_resource_with_properties,
    assert_has_tag,
    find_tag_value
)


@pytest.fixture
def dummy_workload():
    """Create a dummy workload config for testing"""
    return WorkloadConfig(
        {
            "name": "dummy-workload",
            "description": "Dummy workload for testing",
            "devops": {
                "account": "123456789012",
                "region": "us-east-1",
                "commands": []
            },
            "stacks": [
                {
                    "name": "vpc-test",
                    "module": "vpc_library_module",
                    "enabled": True,
                    "vpc": {
                        "name": "test-vpc",
                        "cidr": "10.0.0.0/16",
                        "max_azs": 2,
                    },
                },
                {
                    "name": "rds-test",
                    "module": "rds_library_module",
                    "enabled": True,
                    "rds": {
                        "name": "test-db",
                        "engine": "postgres",
                        "engine_version": "14",
                        "instance_class": "t3.micro",
                        "database_name": "testdb",
                        "username": "admin",
                    },
                }
            ],
        }
    )


def test_rds_stack_synth(dummy_workload):
    """Test that the RDS stack can be synthesized without errors"""
    # Create the app and stack
    app = App()
    
    # Create the stack config
    stack_config = StackConfig(
        {
            "name": "rds-test",
            "module": "rds_library_module",
            "enabled": True,
            "rds": {
                "name": "test-db",
                "engine": "postgres",
                "engine_version": "14",
                "instance_class": "t3.micro",
                "database_name": "testdb",
                "username": "admin",
            },
        },
        workload=dummy_workload.dictionary,
    )
    
    # Create the deployment config
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "test-deployment"},
    )
    
    # Create and build the stack
    stack = RdsStack(app, "TestRdsStack")
    
    # Set the VPC ID on the workload
    dummy_workload.vpc_id = "vpc-12345"
    
    # Patch the _get_vpc method to use a direct import instead of lookup
    with patch.object(RdsStack, '_get_vpc') as mock_get_vpc:
        mock_get_vpc.return_value = ec2.Vpc.from_vpc_attributes(
            stack, "ImportedVpc",
            vpc_id="vpc-12345",
            availability_zones=["us-east-1a", "us-east-1b"],
            private_subnet_ids=["subnet-1", "subnet-2"],
            public_subnet_ids=["subnet-3", "subnet-4"]
        )
        # Build the stack
        stack.build(stack_config, deployment, dummy_workload)
    
    # Synthesize the stack to CloudFormation
    template = app.synth().get_stack_by_name("TestRdsStack").template
    
    # Verify the template has the expected resources
    resources = template.get("Resources", {})
    
    # Check that we have a DB instance
    db_resources = get_resources_by_type(template, "AWS::RDS::DBInstance")
    assert len(db_resources) == 1
    
    # Get the DB instance resource
    db_resource = db_resources[0]["resource"]
    
    # Check DB instance properties
    assert db_resource["Properties"]["Engine"] == "postgres"
    assert db_resource["Properties"]["EngineVersion"] == "14"
    assert db_resource["Properties"]["DBInstanceClass"] == "db.t3.micro"
    assert db_resource["Properties"]["DBName"] == "testdb"
    
    # Check that we have a secret
    secret_resources = get_resources_by_type(template, "AWS::SecretsManager::Secret")
    assert len(secret_resources) > 0
    
    # Check that we have a DB subnet group
    subnet_group_resources = get_resources_by_type(template, "AWS::RDS::DBSubnetGroup")
    assert len(subnet_group_resources) > 0


def test_rds_stack_full_config(dummy_workload):
    """Test that the RDS stack can be synthesized with full configuration"""
    # Create the app and stack
    app = App()
    
    # Create the stack config
    stack_config = StackConfig(
        {
            "name": "rds-test",
            "module": "rds_library_module",
            "enabled": True,
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
                "deletion_protection": True,
                "backup_retention": 14,
                "cloudwatch_logs_exports": ["error", "general", "slowquery"],
                "enable_performance_insights": True,
                "performance_insights_retention": 7,
                "removal_policy": "snapshot",
                "tags": {
                    "Environment": "test",
                    "Project": "cdk-factory"
                }
            },
        },
        workload=dummy_workload.dictionary,
    )
    
    # Create the deployment config
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "test-deployment"},
    )
    
    # Create and build the stack
    stack = RdsStack(app, "TestRdsFullStack")
    
    # Set the VPC ID on the workload
    dummy_workload.vpc_id = "vpc-12345"
    
    # Patch the _get_vpc method to use a direct import instead of lookup
    with patch.object(RdsStack, '_get_vpc') as mock_get_vpc:
        mock_get_vpc.return_value = ec2.Vpc.from_vpc_attributes(
            stack, "ImportedVpc",
            vpc_id="vpc-12345",
            availability_zones=["us-east-1a", "us-east-1b"],
            private_subnet_ids=["subnet-1", "subnet-2"],
            public_subnet_ids=["subnet-3", "subnet-4"]
        )
        # Build the stack
        stack.build(stack_config, deployment, dummy_workload)
    
    # Synthesize the stack to CloudFormation
    template = app.synth().get_stack_by_name("TestRdsFullStack").template
    
    # Verify the template has the expected resources
    resources = template.get("Resources", {})
    
    # Check that we have a DB instance
    db_resources = get_resources_by_type(template, "AWS::RDS::DBInstance")
    assert len(db_resources) == 1
    
    # Get the DB instance resource
    db_resource = db_resources[0]["resource"]
    
    # Check DB instance properties
    assert db_resource["Properties"]["Engine"] == "mysql"
    assert db_resource["Properties"]["EngineVersion"] == "8.0"
    assert db_resource["Properties"]["DBInstanceClass"] == "db.r5.large"
    assert db_resource["Properties"]["DBName"] == "fulldb"
    assert db_resource["Properties"]["AllocatedStorage"] == 100
    assert db_resource["Properties"]["StorageEncrypted"] is True
    assert db_resource["Properties"]["MultiAZ"] is True
    assert db_resource["Properties"]["DeletionProtection"] is True
    assert db_resource["Properties"]["BackupRetentionPeriod"] == 14
    assert set(db_resource["Properties"]["EnableCloudwatchLogsExports"]) == set(["error", "general", "slowquery"])
    assert db_resource["Properties"]["EnablePerformanceInsights"] is True
    
    # Check that we have a secret with the correct name
    secret_resources = get_resources_by_type(template, "AWS::SecretsManager::Secret")
    assert len(secret_resources) > 0
    
    # Find the secret with the correct name
    secret_found = False
    for secret_info in secret_resources:
        secret = secret_info["resource"]
        if "full-db-credentials" in secret["Properties"].get("Name", ""):
            secret_found = True
            break
    
    assert secret_found, "Secret with name 'full-db-credentials' not found"
    
    # Check that the DB instance has the correct tags
    tags = db_resource["Properties"]["Tags"]
    assert find_tag_value(tags, "Environment") == "test"
    assert find_tag_value(tags, "Project") == "cdk-factory"
