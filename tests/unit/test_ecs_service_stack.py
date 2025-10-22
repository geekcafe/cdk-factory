"""
Unit tests for the ECS Service Stack - No Mocking, Real CDK Synthesis
Follows established testing patterns with pytest fixtures and real CDK synthesis.
"""

import pytest
import aws_cdk as cdk
from aws_cdk import App
from aws_cdk.assertions import Template, Match

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.ecs.ecs_service_stack import EcsServiceStack
from cdk_factory.workload.workload_factory import WorkloadConfig


class TestEcsServiceStack:
    """Test ECS Service stack with real CDK synthesis"""

    @pytest.fixture
    def app(self):
        """Create CDK App for testing"""
        return App()

    @pytest.fixture
    def workload_config(self):
        """Create a basic workload config with VPC"""
        return WorkloadConfig(
            {
                "workload": {
                    "name": "test-workload",
                    "devops": {"name": "test-devops"},
                },
                "vpc": {
                    "id": "vpc-12345678",
                    "cidr": "10.0.0.0/16",
                    "subnets": {
                        "private": ["subnet-abc123", "subnet-def456"],
                        "public": ["subnet-ghi789", "subnet-jkl012"],
                    },
                },
            }
        )

    @pytest.fixture
    def deployment_config(self, workload_config):
        """Create a deployment config"""
        return DeploymentConfig(
            workload=workload_config.dictionary,
            deployment={"name": "test", "environment": "test"},
        )

    def test_minimal_fargate_service(self, app, deployment_config, workload_config):
        """Test ECS Service stack with minimal Fargate configuration"""
        stack_config = StackConfig(
            {
                "ecs_service": {
                    "name": "test-service",
                    "vpc_id": "vpc-12345678",
                    "launch_type": "FARGATE",
                    "desired_count": 2,
                    "task_definition": {
                        "cpu": "256",
                        "memory": "512",
                        "containers": [
                            {
                                "name": "nginx",
                                "image": "nginx:latest",
                                "port_mappings": [{"container_port": 80}],
                                "essential": True,
                            }
                        ],
                    },
                    "security_group_ids": ["sg-12345678"],
                }
            },
            workload=workload_config.dictionary,
        )

        stack = EcsServiceStack(
            app,
            "TestMinimalFargateService",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        # Verify ECS Cluster is created (no cluster_name means auto-create)
        template.has_resource_properties(
            "AWS::ECS::Cluster",
            {"ClusterName": "test-workload-test-cluster"},
        )

        # Verify Fargate Task Definition
        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "Cpu": "256",
                "Memory": "512",
                "NetworkMode": "awsvpc",
                "RequiresCompatibilities": ["FARGATE"],
            },
        )

        # Verify Fargate Service
        template.has_resource_properties(
            "AWS::ECS::Service",
            {"DesiredCount": 2, "LaunchType": "FARGATE"},
        )

        # Verify IAM Roles and Log Group
        template.resource_count_is("AWS::IAM::Role", 2)
        template.has_resource("AWS::Logs::LogGroup", {})

        assert stack.ecs_config.name == "test-service"
        assert stack.ecs_config.desired_count == 2

    def test_full_fargate_service_with_all_features(
        self, app, deployment_config, workload_config
    ):
        """Test comprehensive Fargate configuration with auto-scaling"""
        stack_config = StackConfig(
            {
                "ecs_service": {
                    "name": "full-service",
                    "vpc_id": "vpc-12345678",
                    "launch_type": "FARGATE",
                    "desired_count": 3,
                    "min_capacity": 2,
                    "max_capacity": 10,
                    "enable_auto_scaling": True,
                    "auto_scaling_target_cpu": 75,
                    "auto_scaling_target_memory": 85,
                    "enable_execute_command": True,
                    "task_definition": {
                        "cpu": "1024",
                        "memory": "2048",
                        "containers": [
                            {
                                "name": "app",
                                "image": "123456789012.dkr.ecr.us-east-1.amazonaws.com/my-app:v1.0",
                                "cpu": 512,
                                "memory": 1024,
                                "essential": True,
                                "port_mappings": [{"container_port": 8080}],
                                "environment": {"ENV": "production"},
                                "health_check": {
                                    "command": ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"],
                                    "interval": 30,
                                    "timeout": 5,
                                    "retries": 3,
                                    "start_period": 60,
                                },
                            }
                        ],
                    },
                    "security_group_ids": ["sg-12345678"],
                    "ssm_exports": {
                        "service_name": "/production/test-workload/ecs/service-name",
                        "service_arn": "/production/test-workload/ecs/service-arn",
                    },
                }
            },
            workload=workload_config.dictionary,
        )

        stack = EcsServiceStack(
            app,
            "TestFullFargateService",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        # Verify Service configuration
        template.has_resource_properties(
            "AWS::ECS::Service",
            {
                "DesiredCount": 3,
                "EnableExecuteCommand": True,
                "DeploymentConfiguration": {
                    "DeploymentCircuitBreaker": {"Enable": True, "Rollback": True}
                },
            },
        )

        # Verify Auto Scaling
        template.has_resource("AWS::ApplicationAutoScaling::ScalableTarget", {})
        template.resource_count_is("AWS::ApplicationAutoScaling::ScalingPolicy", 2)

        # Verify SSM exports
        template.resource_count_is("AWS::SSM::Parameter", 2)

        assert stack.ecs_config.enable_auto_scaling is True
        assert stack.ecs_config.auto_scaling_target_cpu == 75

    def test_service_without_auto_scaling(self, app, deployment_config, workload_config):
        """Test service with auto-scaling disabled"""
        stack_config = StackConfig(
            {
                "ecs_service": {
                    "name": "no-autoscale-service",
                    "vpc_id": "vpc-12345678",
                    "desired_count": 2,
                    "enable_auto_scaling": False,
                    "task_definition": {
                        "cpu": "512",
                        "memory": "1024",
                        "containers": [
                            {"name": "app", "image": "myapp:latest"}
                        ],
                    },
                    "security_group_ids": ["sg-12345678"],
                }
            },
            workload=workload_config.dictionary,
        )

        stack = EcsServiceStack(
            app,
            "TestNoAutoScaleService",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        template.has_resource("AWS::ECS::Service", {})
        template.resource_count_is("AWS::ApplicationAutoScaling::ScalableTarget", 0)
        template.resource_count_is("AWS::ApplicationAutoScaling::ScalingPolicy", 0)

        assert stack.ecs_config.enable_auto_scaling is False

    def test_service_with_load_balancer_integration(
        self, app, deployment_config, workload_config
    ):
        """Test service with load balancer target groups"""
        stack_config = StackConfig(
            {
                "ecs_service": {
                    "name": "lb-service",
                    "vpc_id": "vpc-12345678",
                    "desired_count": 3,
                    "target_group_arns": [
                        "arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/my-tg/50dc6c495c0c9188",
                    ],
                    "health_check_grace_period": 300,
                    "task_definition": {
                        "cpu": "512",
                        "memory": "1024",
                        "containers": [
                            {
                                "name": "web",
                                "image": "mywebapp:latest",
                                "port_mappings": [{"container_port": 8080}],
                            }
                        ],
                    },
                    "security_group_ids": ["sg-12345678"],
                }
            },
            workload=workload_config.dictionary,
        )

        stack = EcsServiceStack(
            app,
            "TestLBService",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::ECS::Service",
            {
                "DesiredCount": 3,
                "HealthCheckGracePeriodSeconds": 300,
                "LoadBalancers": Match.array_with(
                    [Match.object_like({"TargetGroupArn": Match.string_like_regexp(".*targetgroup.*")})]
                ),
            },
        )

        assert stack.ecs_config.health_check_grace_period == 300

    def test_service_with_multiple_containers(self, app, deployment_config, workload_config):
        """Test service with multiple containers"""
        stack_config = StackConfig(
            {
                "ecs_service": {
                    "name": "multi-container-service",
                    "vpc_id": "vpc-12345678",
                    "desired_count": 2,
                    "task_definition": {
                        "cpu": "1024",
                        "memory": "2048",
                        "containers": [
                            {
                                "name": "frontend",
                                "image": "frontend:v1",
                                "cpu": 512,
                                "memory": 1024,
                                "essential": True,
                            },
                            {
                                "name": "backend",
                                "image": "backend:v1",
                                "cpu": 256,
                                "memory": 512,
                                "essential": True,
                            },
                        ],
                    },
                    "security_group_ids": ["sg-12345678"],
                }
            },
            workload=workload_config.dictionary,
        )

        stack = EcsServiceStack(
            app,
            "TestMultiContainerService",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        template.resource_count_is("AWS::Logs::LogGroup", 2)
        assert len(stack.ecs_config.container_definitions) == 2

    def test_service_creates_new_cluster_when_not_specified(
        self, app, deployment_config, workload_config
    ):
        """Test that stack creates new cluster when not specified"""
        stack_config = StackConfig(
            {
                "ecs_service": {
                    "name": "new-cluster-service",
                    "vpc_id": "vpc-12345678",
                    "desired_count": 1,
                    "task_definition": {
                        "cpu": "256",
                        "memory": "512",
                        "containers": [{"name": "app", "image": "myapp:latest"}],
                    },
                    "security_group_ids": ["sg-12345678"],
                }
            },
            workload=workload_config.dictionary,
        )

        stack = EcsServiceStack(
            app,
            "TestNewClusterService",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::ECS::Cluster",
            {
                "ClusterName": "test-workload-test-cluster",
                "ClusterSettings": [{"Name": "containerInsights", "Value": "enabled"}],
            },
        )

        assert stack.cluster is not None

    def test_service_requires_vpc_id(self, app, deployment_config, workload_config):
        """Test that stack raises error when VPC ID is missing"""
        stack_config = StackConfig(
            {
                "ecs_service": {
                    "name": "no-vpc-service",
                    "desired_count": 1,
                    "task_definition": {
                        "cpu": "256",
                        "memory": "512",
                        "containers": [{"name": "app", "image": "myapp:latest"}],
                    },
                }
            },
            workload=workload_config.dictionary,
        )

        stack = EcsServiceStack(
            app,
            "TestNoVPCService",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

        with pytest.raises(ValueError, match="VPC ID is required for ECS service"):
            stack.build(stack_config, deployment_config, workload_config)

    def test_service_requires_container_definitions(
        self, app, deployment_config, workload_config
    ):
        """Test that stack raises error when no container definitions provided"""
        stack_config = StackConfig(
            {
                "ecs_service": {
                    "name": "no-containers-service",
                    "vpc_id": "vpc-12345678",
                    "desired_count": 1,
                    "task_definition": {
                        "cpu": "256",
                        "memory": "512",
                        "containers": [],
                    },
                    "security_group_ids": ["sg-12345678"],
                }
            },
            workload=workload_config.dictionary,
        )

        stack = EcsServiceStack(
            app,
            "TestNoContainersService",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

        with pytest.raises(
            ValueError, match="At least one container definition is required"
        ):
            stack.build(stack_config, deployment_config, workload_config)
