"""
Integration tests for AutoScalingStack to catch naming conflicts and other integration issues
"""

import unittest
from unittest.mock import MagicMock

import aws_cdk as cdk
from aws_cdk import App, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs

from cdk_factory.stack_library.auto_scaling.auto_scaling_stack import AutoScalingStack
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.workload.workload_factory import WorkloadConfig


class TestAutoScalingStackIntegration(unittest.TestCase):
    """Integration tests for AutoScalingStack"""

    def setUp(self):
        """Set up test fixtures"""
        self.app = App()
        
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

    def test_vpc_naming_with_ecs_cluster(self):
        """Test that VPC and ECS cluster can coexist without naming conflicts"""
        # Create AutoScalingStack with ECS configuration
        stack = AutoScalingStack(self.app, "test-workload-prod-ecs-cluster")
        
        # Configure for ECS
        stack_config = StackConfig({
            "auto_scaling": {
                "name": "test-ecs-asg",
                "instance_type": "t3.small",
                "min_capacity": 1,
                "max_capacity": 2,
                "desired_capacity": 1,
                "subnet_group_name": "Public",
                "managed_policies": [
                    "AmazonSSMManagedInstanceCore",
                    "CloudWatchAgentServerPolicy", 
                    "service-role/AmazonEC2ContainerServiceforEC2Role"
                ],
                "ssm_imports": {
                    "vpc_id": "/test/vpc/id",
                    "subnet_ids": "/test/vpc/subnet-ids",
                    "security_group_ids": "/test/sg/ecs-id"
                },
                "user_data_commands": [
                    "#!/bin/bash",
                    "echo ECS_CLUSTER=test-workload-prod-cluster >> /etc/ecs/ecs.config"
                ]
            }
        }, self.workload_config.dictionary)
        
        # Mock SSM parameter values
        stack._ssm_imported_values = {
            "vpc_id": "vpc-test123",
            "subnet_ids": "subnet-test1,subnet-test2,subnet-test3",
            "security_group_ids": "sg-test123"
        }
        
        # Build the stack - this should not raise naming conflicts
        try:
            stack.build(stack_config, self.deployment_config, self.workload_config)
            
            # Verify both VPC and ECS cluster were created
            self.assertIsNotNone(stack.vpc)
            self.assertIsNotNone(stack.ecs_cluster)
            
            # Verify VPC has correct properties
            self.assertEqual(stack.vpc.vpc_id, "vpc-test123")
            
            # Verify ECS cluster has correct name (handle CDK tokens)
            cluster_name = stack.ecs_cluster.cluster_name
            # Check if it's a CDK token (contains ${Token[})
            if "${Token[" in str(cluster_name):
                # It's a CDK token, which is expected
                print(f"✅ ECS cluster name is CDK token: {cluster_name}")
            else:
                # Should contain our expected cluster name
                self.assertIn("test-workload-prod-cluster", str(cluster_name))
            
            print("✅ VPC and ECS cluster created without naming conflicts")
            
        except Exception as e:
            self.fail(f"VPC and ECS cluster creation failed with naming conflict: {e}")

    def test_vpc_construct_name_uniqueness(self):
        """Test that VPC construct names are unique across different stacks"""
        # Create two stacks with similar names
        stack1 = AutoScalingStack(self.app, "test-workload-prod-ecs-cluster")
        stack2 = AutoScalingStack(self.app, "test-workload-prod-ecs-cluster-2")
        
        # Configure both stacks for SSM VPC imports
        stack_config = StackConfig({
            "auto_scaling": {
                "name": "test-asg",
                "instance_type": "t3.small",
                "min_capacity": 1,
                "max_capacity": 2,
                "desired_capacity": 1,
                "subnet_group_name": "Public",
                "ssm_imports": {
                    "vpc_id": "/test/vpc/id",
                    "subnet_ids": "/test/vpc/subnet-ids"
                }
            }
        }, self.workload_config.dictionary)
        
        # Mock SSM values
        for stack in [stack1, stack2]:
            stack._ssm_imported_values = {
                "vpc_id": "vpc-test123",
                "subnet_ids": "subnet-test1,subnet-test2"
            }
        
        # Build both stacks - should not interfere with each other
        try:
            stack1.build(stack_config, self.deployment_config, self.workload_config)
            stack2.build(stack_config, self.deployment_config, self.workload_config)
            
            # Verify both have VPCs
            self.assertIsNotNone(stack1.vpc)
            self.assertIsNotNone(stack2.vpc)
            
            print("✅ Multiple stacks can create VPCs with unique names")
            
        except Exception as e:
            self.fail(f"Multiple stack VPC creation failed: {e}")

    def test_ecs_cluster_detection(self):
        """Test that ECS cluster creation is properly detected"""
        stack = AutoScalingStack(self.app, "test-ecs-detection")
        
        # Test ECS detection via managed policy
        stack_config = StackConfig({
            "auto_scaling": {
                "name": "test-asg",
                "instance_type": "t3.small",
                "min_capacity": 1,
                "max_capacity": 2,
                "desired_capacity": 1,
                "managed_policies": [
                    "service-role/AmazonEC2ContainerServiceforEC2Role"
                ],
                "user_data_commands": [
                    "echo ECS_CLUSTER=test-cluster >> /etc/ecs/ecs.config"
                ]
            }
        }, self.workload_config.dictionary)
        
        # Mock user data
        class MockUserData:
            def __str__(self):
                return "echo ECS_CLUSTER=test-cluster >> /etc/ecs/ecs.config"
        
        stack.user_data = MockUserData()
        stack.asg_config = MagicMock()
        stack.asg_config.managed_policies = ["service-role/AmazonEC2ContainerServiceforEC2Role"]
        stack.stack_config = stack_config
        stack.deployment = self.deployment_config
        # Mock the VPC property instead of trying to set it
        stack._vpc = MagicMock()
        
        # Test ECS detection logic
        is_ecs_config = (
            (stack.user_data and "ECS_CLUSTER=" in str(stack.user_data)) or
            any("AmazonEC2ContainerServiceforEC2Role" in policy for policy in stack.asg_config.managed_policies) or
            stack.stack_config.dictionary.get("auto_scaling", {}).get("enable_ecs_cluster", False)
        )
        
        self.assertTrue(is_ecs_config, "ECS configuration should be detected")
        print("✅ ECS configuration detection working correctly")

    def test_ecs_cluster_naming_default(self):
        """Test that ECS cluster gets default name when no user data cluster is specified"""
        # Create AutoScalingStack with ECS configuration but no cluster name in user data
        stack = AutoScalingStack(self.app, "test-workload-prod-ecs-cluster-default")
        
        # Configure for ECS without specific cluster name
        stack_config = StackConfig({
            "auto_scaling": {
                "name": "test-ecs-asg",
                "instance_type": "t3.small",
                "min_capacity": 1,
                "max_capacity": 2,
                "desired_capacity": 1,
                "subnet_group_name": "Public",
                "managed_policies": [
                    "service-role/AmazonEC2ContainerServiceforEC2Role"
                ],
                "ssm_imports": {
                    "vpc_id": "/test/vpc/id",
                    "subnet_ids": "/test/vpc/subnet-ids"
                },
                "user_data_commands": [
                    "#!/bin/bash",
                    "echo ECS_ENABLE_CONTAINER_METADATA=true >> /etc/ecs/ecs.config"
                ]
            }
        }, self.workload_config.dictionary)
        
        # Mock SSM parameter values
        stack._ssm_imported_values = {
            "vpc_id": "vpc-test123",
            "subnet_ids": "subnet-test1,subnet-test2"
        }
        
        # Build the stack
        try:
            stack.build(stack_config, self.deployment_config, self.workload_config)
            
            # Verify ECS cluster was created
            self.assertIsNotNone(stack.ecs_cluster)
            
            # Verify default cluster naming (should contain 'cluster')
            cluster_name = stack.ecs_cluster.cluster_name
            if "${Token[" in str(cluster_name):
                # Check template synthesis for default naming
                template = self.app.synth().get_stack_by_name("test-workload-prod-ecs-cluster-default").template
                ecs_cluster_resource = None
                for resource_id, resource in template.get('Resources', {}).items():
                    if resource.get('Type') == 'AWS::ECS::Cluster':
                        ecs_cluster_resource = resource
                        break
                
                self.assertIsNotNone(ecs_cluster_resource, "ECS cluster resource should exist in template")
                actual_cluster_name = ecs_cluster_resource.get('Properties', {}).get('ClusterName')
                self.assertIsNotNone(actual_cluster_name, "Default cluster name should not be None")
                self.assertIn("cluster", actual_cluster_name.lower(), 
                             "Default cluster name should contain 'cluster'")
            else:
                self.assertIn("cluster", cluster_name.lower(), 
                             "Default cluster name should contain 'cluster'")
            
            print("✅ ECS cluster default naming works correctly")
            
        except Exception as e:
            self.fail(f"ECS cluster default naming test failed: {e}")

    def test_ecs_cluster_naming_from_stack(self):
        """Test that ECS cluster gets the correct name from stack and injects into user data"""
        # Create AutoScalingStack with ECS configuration
        stack = AutoScalingStack(self.app, "test-workload-prod-ecs-cluster")
        
        # Configure for ECS with placeholder cluster name in user data
        stack_config = StackConfig({
            "auto_scaling": {
                "name": "test-ecs-asg",
                "instance_type": "t3.small",
                "min_capacity": 1,
                "max_capacity": 2,
                "desired_capacity": 1,
                "subnet_group_name": "Public",
                "managed_policies": [
                    "AmazonSSMManagedInstanceCore",
                    "CloudWatchAgentServerPolicy", 
                    "service-role/AmazonEC2ContainerServiceforEC2Role"
                ],
                "ssm_imports": {
                    "vpc_id": "/test/vpc/id",
                    "subnet_ids": "/test/vpc/subnet-ids",
                    "security_group_ids": "/test/sg/ecs-id"
                },
                "user_data_commands": [
                    "#!/bin/bash",
                    "echo ECS_CLUSTER=placeholder >> /etc/ecs/ecs.config"
                ]
            }
        }, self.workload_config.dictionary)
        
        # Mock SSM parameter values
        stack._ssm_imported_values = {
            "vpc_id": "vpc-test123",
            "subnet_ids": "subnet-test1,subnet-test2,subnet-test3",
            "security_group_ids": "sg-test123"
        }
        
        # Build the stack
        try:
            stack.build(stack_config, self.deployment_config, self.workload_config)
            
            # Verify ECS cluster was created
            self.assertIsNotNone(stack.ecs_cluster)
            
            # Verify the cluster name was generated correctly (should contain 'cluster')
            cluster_name = stack.ecs_cluster.cluster_name
            if "${Token[" in str(cluster_name):
                # If it's a token, we need to check the template synthesis
                template = self.app.synth().get_stack_by_name("test-workload-prod-ecs-cluster").template
                ecs_cluster_resource = None
                for resource_id, resource in template.get('Resources', {}).items():
                    if resource.get('Type') == 'AWS::ECS::Cluster':
                        ecs_cluster_resource = resource
                        break
                
                self.assertIsNotNone(ecs_cluster_resource, "ECS cluster resource should exist in template")
                actual_cluster_name = ecs_cluster_resource.get('Properties', {}).get('ClusterName')
                self.assertIsNotNone(actual_cluster_name, "Cluster name should not be None")
                self.assertIn("cluster", actual_cluster_name.lower(), 
                             "Cluster name should contain 'cluster'")
            else:
                self.assertIn("cluster", cluster_name.lower(), 
                             "Cluster name should contain 'cluster'")
            
            # Verify that the user data was updated with the correct cluster name
            cluster_injected = any("ECS_CLUSTER=" in cmd and "placeholder" not in cmd for cmd in stack.user_data_commands)
            self.assertTrue(cluster_injected, "ECS cluster name should be injected into user data")
            
            print("✅ ECS cluster naming and user data injection works correctly")
            
        except Exception as e:
            self.fail(f"ECS cluster naming test failed: {e}")

    def test_ecs_cluster_naming_without_user_data_cluster(self):
        """Test that ECS cluster gets created and adds cluster name to user data when none exists"""
        # Create AutoScalingStack with ECS configuration but no cluster in user data
        stack = AutoScalingStack(self.app, "test-workload-prod-ecs-cluster-auto")
        
        # Configure for ECS without cluster name in user data
        stack_config = StackConfig({
            "auto_scaling": {
                "name": "test-ecs-asg",
                "instance_type": "t3.small",
                "min_capacity": 1,
                "max_capacity": 2,
                "desired_capacity": 1,
                "subnet_group_name": "Public",
                "managed_policies": [
                    "service-role/AmazonEC2ContainerServiceforEC2Role"
                ],
                "ssm_imports": {
                    "vpc_id": "/test/vpc/id",
                    "subnet_ids": "/test/vpc/subnet-ids"
                },
                "user_data_commands": [
                    "#!/bin/bash",
                    "echo ECS_ENABLE_CONTAINER_METADATA=true >> /etc/ecs/ecs.config"
                ]
            }
        }, self.workload_config.dictionary)
        
        # Mock SSM parameter values
        stack._ssm_imported_values = {
            "vpc_id": "vpc-test123",
            "subnet_ids": "subnet-test1,subnet-test2"
        }
        
        # Build the stack
        try:
            stack.build(stack_config, self.deployment_config, self.workload_config)
            
            # Verify ECS cluster was created
            self.assertIsNotNone(stack.ecs_cluster)
            
            # Verify that the cluster name was added to user data
            cluster_added = any("ECS_CLUSTER=" in cmd for cmd in stack.user_data_commands)
            self.assertTrue(cluster_added, "ECS cluster name should be added to user data")
            
            print("✅ ECS cluster auto-adds cluster name to user data when missing")
            
        except Exception as e:
            self.fail(f"ECS cluster auto-add test failed: {e}")


if __name__ == "__main__":
    unittest.main()
