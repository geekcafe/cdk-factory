"""
Unit tests for the Auto Scaling Stack
"""

import unittest
from unittest.mock import patch, MagicMock

import aws_cdk as cdk
from aws_cdk import App
from aws_cdk import aws_autoscaling as autoscaling
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.auto_scaling.auto_scaling_stack import AutoScalingStack
from cdk_factory.workload.workload_factory import WorkloadConfig


def test_auto_scaling_stack_minimal():
    """Test Auto Scaling stack with minimal configuration"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "auto_scaling": {
                "name": "test-asg",
                "instance_type": "t3.micro",
                "min_capacity": 1,
                "max_capacity": 3,
                "desired_capacity": 2,
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
    )

    # Create and build the stack
    stack = AutoScalingStack(app, "TestAutoScalingStack")

    # Mock VPC and security group
    mock_vpc = MagicMock()
    mock_vpc.vpc_id = "vpc-12345"
    mock_security_group = MagicMock()
    mock_security_group.security_group_id = "sg-12345"

    # Mock the workload object with VPC
    dummy_workload.vpc = mock_vpc

    # Mock the necessary methods
    mock_role = MagicMock()
    mock_role.role_arn = "arn:aws:iam::account:role/test-role"

    mock_launch_template = MagicMock()
    mock_launch_template.launch_template_id = "lt-12345"

    mock_asg = MagicMock()
    mock_asg.auto_scaling_group_name = "test-asg"

    # Mock the methods
    with patch.object(AutoScalingStack, "vpc", return_value=mock_vpc) as mock_get_vpc:
        with patch.object(
            AutoScalingStack, "_create_instance_role", return_value=mock_role
        ) as mock_create_role:
            with patch.object(
                AutoScalingStack, "_create_user_data"
            ) as mock_create_user_data:
                with patch.object(
                    AutoScalingStack,
                    "_create_launch_template",
                    return_value=mock_launch_template,
                ) as mock_create_lt:
                    with patch.object(
                        AutoScalingStack,
                        "_create_auto_scaling_group",
                        return_value=mock_asg,
                    ) as mock_create_asg:
                        with patch.object(
                            AutoScalingStack, "_configure_scaling_policies"
                        ) as mock_configure_policies:
                            with patch.object(
                                AutoScalingStack, "_add_outputs"
                            ) as mock_add_outputs:
                                # Build the stack
                                stack.build(stack_config, deployment, dummy_workload)

                                # Verify the Auto Scaling config was correctly loaded
                                assert stack.asg_config.name == "test-asg"
                                assert stack.asg_config.instance_type == "t3.micro"
                                assert stack.asg_config.min_capacity == 1
                                assert stack.asg_config.max_capacity == 3
                                assert stack.asg_config.desired_capacity == 2

                                # Verify the resources were created
                                assert stack.instance_role is mock_role
                                assert stack.launch_template is mock_launch_template
                                assert stack.auto_scaling_group is mock_asg

                                # Verify methods were called

                                mock_create_role.assert_called_once()
                                mock_create_user_data.assert_called_once()
                                mock_create_lt.assert_called_once()
                                mock_create_asg.assert_called_once()
                                mock_configure_policies.assert_called_once()
                                mock_add_outputs.assert_called_once()


def test_auto_scaling_stack_full_config():
    """Test Auto Scaling stack with full configuration"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "auto_scaling": {
                "name": "full-asg",
                "instance_type": "m5.large",
                "min_capacity": 2,
                "max_capacity": 10,
                "desired_capacity": 4,
                "subnet_group_name": "private",
                "security_group_ids": ["sg-12345"],
                "health_check_type": "ELB",
                "health_check_grace_period": 300,
                "cooldown": 300,
                "termination_policies": ["OldestInstance", "Default"],
                "managed_policies": [
                    "AmazonSSMManagedInstanceCore",
                    "AmazonEC2ContainerRegistryReadOnly",
                ],
                "ami_type": "amazon-linux-2023",
                "detailed_monitoring": True,
                "block_devices": [
                    {
                        "device_name": "/dev/xvda",
                        "volume_size": 30,
                        "volume_type": "gp3",
                        "delete_on_termination": True,
                        "encrypted": True,
                    }
                ],
                "container_config": {
                    "ecr": {"repo": "app", "tag": "latest"},
                    "database": {
                        "secret_arn": "arn:aws:secretsmanager:region:account:secret:db-credentials"
                    },
                    "port": 8080,
                },
                "user_data_commands": [
                    "yum update -y",
                    "yum install -y docker",
                    "systemctl enable --now docker",
                ],
                "scaling_policies": [
                    {
                        "name": "cpu-scale-out",
                        "type": "target_tracking",
                        "metric_name": "CPUUtilization",
                        "target_value": 70,
                        "scale_out_cooldown": 300,
                        "scale_in_cooldown": 300,
                    }
                ],
                "tags": {"Environment": "test", "Project": "cdk-factory"},
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
    )

    # Create and build the stack
    stack = AutoScalingStack(app, "FullAutoScalingStack")

    # Mock VPC and security group
    mock_vpc = MagicMock()
    mock_vpc.vpc_id = "vpc-12345"
    mock_security_group = MagicMock()
    mock_security_group.security_group_id = "sg-12345"

    # Mock the workload object with VPC
    dummy_workload.vpc = mock_vpc

    # Mock the necessary methods
    mock_role = MagicMock()
    mock_role.role_arn = "arn:aws:iam::account:role/full-role"

    mock_launch_template = MagicMock()
    mock_launch_template.launch_template_id = "lt-67890"

    mock_asg = MagicMock()
    mock_asg.auto_scaling_group_name = "full-asg"

    # Mock the methods
    with patch.object(AutoScalingStack, "vpc", return_value=mock_vpc) as mock_get_vpc:
        with patch.object(
            AutoScalingStack, "_get_security_groups", return_value=[mock_security_group]
        ) as mock_get_sg:
            with patch.object(
                AutoScalingStack, "_create_instance_role", return_value=mock_role
            ) as mock_create_role:
                with patch.object(
                    AutoScalingStack, "_create_user_data"
                ) as mock_create_user_data:
                    with patch.object(
                        AutoScalingStack,
                        "_create_launch_template",
                        return_value=mock_launch_template,
                    ) as mock_create_lt:
                        with patch.object(
                            AutoScalingStack,
                            "_create_auto_scaling_group",
                            return_value=mock_asg,
                        ) as mock_create_asg:
                            with patch.object(
                                AutoScalingStack, "_configure_scaling_policies"
                            ) as mock_configure_policies:
                                with patch.object(
                                    AutoScalingStack, "_add_outputs"
                                ) as mock_add_outputs:
                                    # Build the stack
                                    stack.build(
                                        stack_config, deployment, dummy_workload
                                    )

                                    # Verify the Auto Scaling config was correctly loaded
                                    assert stack.asg_config.name == "full-asg"
                                    assert stack.asg_config.instance_type == "m5.large"
                                    assert stack.asg_config.min_capacity == 2
                                    assert stack.asg_config.max_capacity == 10
                                    assert stack.asg_config.desired_capacity == 4
                                    assert (
                                        stack.asg_config.subnet_group_name == "private"
                                    )
                                    assert stack.asg_config.security_group_ids == [
                                        "sg-12345"
                                    ]
                                    assert stack.asg_config.health_check_type == "ELB"
                                    assert (
                                        stack.asg_config.health_check_grace_period
                                        == 300
                                    )
                                    assert stack.asg_config.cooldown == 300
                                    assert stack.asg_config.termination_policies == [
                                        "OldestInstance",
                                        "Default",
                                    ]
                                    assert stack.asg_config.managed_policies == [
                                        "AmazonSSMManagedInstanceCore",
                                        "AmazonEC2ContainerRegistryReadOnly",
                                    ]
                                    assert (
                                        stack.asg_config.ami_type == "amazon-linux-2023"
                                    )
                                    assert stack.asg_config.detailed_monitoring is True
                                    assert len(stack.asg_config.block_devices) == 1
                                    assert (
                                        stack.asg_config.block_devices[0]["device_name"]
                                        == "/dev/xvda"
                                    )
                                    assert (
                                        stack.asg_config.block_devices[0]["volume_size"]
                                        == 30
                                    )
                                    assert (
                                        stack.asg_config.container_config["ecr"]["repo"]
                                        == "app"
                                    )
                                    assert (
                                        stack.asg_config.container_config["port"]
                                        == 8080
                                    )
                                    assert len(stack.asg_config.user_data_commands) == 3
                                    assert len(stack.asg_config.scaling_policies) == 1
                                    assert (
                                        stack.asg_config.scaling_policies[0]["name"]
                                        == "cpu-scale-out"
                                    )
                                    assert stack.asg_config.tags == {
                                        "Environment": "test",
                                        "Project": "cdk-factory",
                                    }

                                    # Verify the resources were created
                                    assert stack.instance_role is mock_role
                                    assert stack.launch_template is mock_launch_template
                                    assert stack.auto_scaling_group is mock_asg

                                    # Verify methods were called

                                    mock_get_sg.assert_called_once()
                                    mock_create_role.assert_called_once()
                                    mock_create_user_data.assert_called_once()
                                    mock_create_lt.assert_called_once()
                                    mock_create_asg.assert_called_once()
                                    mock_configure_policies.assert_called_once()
                                    mock_add_outputs.assert_called_once()


def test_auto_scaling_stack_existing_asg():
    """Test Auto Scaling stack with importing an existing ASG"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "auto_scaling": {
                "name": "imported-asg",
                "existing_asg_name": "existing-asg",
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
    )

    # Create and build the stack
    stack = AutoScalingStack(app, "ImportAutoScalingStack")

    # Mock VPC and security group
    mock_vpc = MagicMock()
    mock_vpc.vpc_id = "vpc-12345"

    # Mock the workload object with VPC
    dummy_workload.vpc = mock_vpc

    # Mock the necessary methods
    mock_asg = MagicMock()
    mock_asg.auto_scaling_group_name = "existing-asg"

    # In the actual implementation, there's no _import_auto_scaling_group method
    # The import happens in _create_auto_scaling_group when existing_asg_name is set
    with patch.object(AutoScalingStack, "vpc", return_value=mock_vpc) as mock_get_vpc:
        with patch.object(
            AutoScalingStack, "_create_auto_scaling_group", return_value=mock_asg
        ) as mock_create_asg:
            with patch.object(AutoScalingStack, "_add_outputs") as mock_add_outputs:
                # Build the stack
                stack.build(stack_config, deployment, dummy_workload)

                # Verify the Auto Scaling config was correctly loaded
                assert stack.asg_config.name == "imported-asg"

                # Verify the ASG was imported
                assert stack.auto_scaling_group is mock_asg

                # Verify methods were called

                mock_create_asg.assert_called_once()
                mock_add_outputs.assert_called_once()
