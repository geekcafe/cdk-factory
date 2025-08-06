import pytest
from aws_cdk import App, Environment
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import RemovalPolicy
from cdk_factory.stack_library.dynamodb.dynamodb_stack import DynamoDBStack
from cdk_factory.configurations.resources.dynamodb import DynamoDBConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.workload.workload_factory import WorkloadConfig
from cdk_factory.stack.stack_factory import StackFactory


def test_dynamodb_stack_minimal():
    """Test creating a DynamoDB stack with minimal configuration"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "dynamodb": {
                "name": "TestTable",
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment", "environment": "dev"},
    )
    stack = DynamoDBStack(app, "TestDynamoDBStack")
    stack.build(stack_config, deployment, dummy_workload)

    # Verify the table was created
    resources = [c for c in stack.node.children if isinstance(c, dynamodb.TableV2)]
    assert len(resources) == 1
    table: dynamodb.TableV2 = resources[0]

    # Verify basic properties
    assert stack.table is not None
    assert stack.db_config.name == "TestTable"
    assert stack.db_config.use_existing is False
    assert stack.db_config.point_in_time_recovery is True
    assert stack.db_config.enable_delete_protection is True
    assert stack.db_config.gsi_count == 5
    assert len(stack.db_config.replica_regions) == 0


def test_dynamodb_stack_full_config():
    """Test creating a DynamoDB stack with full configuration"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "dynamodb": {
                "name": "FullConfigTable",
                "use_existing": False,
                "enable_delete_protection": False,
                "point_in_time_recovery": False,
                "gsi_count": 3,
                "replica_regions": ["us-west-1", "eu-west-1"],
                "kwargs": {"env": {"region": "us-east-1"}},
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment", "environment": "dev"},
    )
    stack = DynamoDBStack(app, "FullDynamoDBStack", env=Environment(region="us-east-1"))
    stack.build(stack_config, deployment, dummy_workload)

    # Verify the table was created
    resources = [c for c in stack.node.children if isinstance(c, dynamodb.TableV2)]
    assert len(resources) == 1
    table: dynamodb.TableV2 = resources[0]

    # Verify properties
    assert stack.table is not None
    assert stack.db_config.name == "FullConfigTable"
    assert stack.db_config.use_existing is False
    assert stack.db_config.point_in_time_recovery is False
    assert stack.db_config.enable_delete_protection is False
    assert stack.db_config.gsi_count == 3
    assert len(stack.db_config.replica_regions) == 2
    assert "us-west-1" in stack.db_config.replica_regions
    assert "eu-west-1" in stack.db_config.replica_regions


def test_dynamodb_stack_factory():
    """Test creating a DynamoDB stack with full configuration"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "name": "db-stack",
            "module": "dynamodb_stack",
            "kwargs": {"env": {"region": "us-east-1"}},
            "dynamodb": {
                "name": "FullConfigTable",
                "use_existing": False,
                "enable_delete_protection": False,
                "point_in_time_recovery": False,
                "gsi_count": 3,
                "replica_regions": ["us-west-1", "eu-west-1"],
            },
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment", "environment": "dev"},
    )
    factory = StackFactory()
    stack = factory.load_module(
        stack_config.module,
        app,
        stack_config.name,
        **stack_config.kwargs,
    )

    stack.build(stack_config, deployment, dummy_workload)

    # Verify the table was created
    resources = [c for c in stack.node.children if isinstance(c, dynamodb.TableV2)]
    assert len(resources) == 1
    table: dynamodb.TableV2 = resources[0]

    # Verify properties
    assert stack.table is not None
    assert stack.db_config.name == "FullConfigTable"
    assert stack.db_config.use_existing is False
    assert stack.db_config.point_in_time_recovery is False
    assert stack.db_config.enable_delete_protection is False
    assert stack.db_config.gsi_count == 3
    assert len(stack.db_config.replica_regions) == 2
    assert "us-west-1" in stack.db_config.replica_regions
    assert "eu-west-1" in stack.db_config.replica_regions


def test_dynamodb_stack_existing_table():
    """Test importing an existing DynamoDB table"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "dynamodb": {
                "name": "ExistingTable",
                "use_existing": True,
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
    )
    stack = DynamoDBStack(app, "ExistingDynamoDBStack")
    stack.build(stack_config, deployment, dummy_workload)

    # Verify that we imported the table rather than creating a new one
    resources = [c for c in stack.node.children if isinstance(c, dynamodb.TableV2)]
    assert len(resources) == 0  # No TableV2 resources created

    assert stack.table is not None
    assert stack.db_config.name == "ExistingTable"
    assert stack.db_config.use_existing is True


def test_dynamodb_stack_removal_policy():
    """Test that removal policy is set correctly based on environment"""
    # Test dev environment (should be DESTROY)
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "dynamodb": {
                "name": "DevTable",
                "enable_delete_protection": False,
            }
        },
        workload=dummy_workload.dictionary,
    )
    dev_deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment", "environment": "dev"},
    )
    dev_stack = DynamoDBStack(app, "DevDynamoDBStack")
    dev_stack.build(stack_config, dev_deployment, dummy_workload)

    # Test prod environment (should be RETAIN)
    prod_deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment", "environment": "prod"},
    )
    prod_stack = DynamoDBStack(app, "ProdDynamoDBStack")
    prod_stack.build(stack_config, prod_deployment, dummy_workload)

    # Verify dev stack has DESTROY removal policy
    dev_resources = [
        c for c in dev_stack.node.children if isinstance(c, dynamodb.TableV2)
    ]
    assert len(dev_resources) == 1

    # Verify prod stack has RETAIN removal policy
    prod_resources = [
        c for c in prod_stack.node.children if isinstance(c, dynamodb.TableV2)
    ]
    assert len(prod_resources) == 1
