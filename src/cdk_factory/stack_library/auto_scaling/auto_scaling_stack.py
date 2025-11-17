"""
Auto Scaling Group Stack Pattern for CDK-Factory (Standardized SSM Version)
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Dict, Any, List, Optional

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_autoscaling as autoscaling
from aws_cdk import aws_iam as iam
from aws_cdk import aws_ecs as ecs
from aws_cdk import Duration

from aws_cdk.aws_autoscaling import HealthChecks, AdditionalHealthCheckType
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.auto_scaling import AutoScalingConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.vpc_provider_mixin import VPCProviderMixin
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="AutoScalingStackStandardized")


@register_stack("auto_scaling_library_module")
@register_stack("auto_scaling_stack")
class AutoScalingStack(IStack, VPCProviderMixin, StandardizedSsmMixin):
    """
    Reusable stack for AWS Auto Scaling Groups with standardized SSM integration.

    This version uses the StandardizedSsmMixin to provide consistent SSM parameter
    handling across all CDK Factory modules.

    Key Features:
    - Standardized SSM import/export patterns
    - Template variable resolution
    - Comprehensive validation
    - Clear error handling
    - Backward compatibility
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        # Initialize parent classes properly
        super().__init__(scope, id, **kwargs)

        # Initialize VPC cache from mixin
        self._initialize_vpc_cache()

        # Initialize module attributes
        self.asg_config = None
        self.stack_config = None
        self.deployment = None
        self.workload = None
        self.security_groups = []
        self.auto_scaling_group = None
        self.launch_template = None
        self.instance_role = None
        self.user_data = None
        self.user_data_commands = []  # Store raw commands for ECS cluster detection
        self.ecs_cluster = None

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Build the Auto Scaling Group stack"""
        self._build(stack_config, deployment, workload)

    def _build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Internal build method for the Auto Scaling Group stack"""
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload

        self.asg_config = AutoScalingConfig(
            stack_config.dictionary.get("auto_scaling", {}), deployment
        )
        # Use stable construct ID to prevent CloudFormation logical ID changes on pipeline rename
        stable_asg_id = f"{deployment.workload_name}-{deployment.environment}-asg"
        asg_name = deployment.build_resource_name(self.asg_config.name)

        # Setup standardized SSM integration
        self.setup_ssm_integration(
            scope=self,
            config=self.asg_config,
            resource_type="auto_scaling",
            resource_name=asg_name,
            deployment=deployment,
            workload=workload,
        )

        # Process SSM imports using standardized method
        self.process_ssm_imports()

        # Get security groups using standardized approach
        self.security_groups = self._get_security_groups()

        # Create IAM role for instances
        self.instance_role = self._create_instance_role(asg_name)

        # Create VPC once to be reused by both ECS cluster and ASG
        self._vpc = None  # Store VPC for reuse

        # Create ECS cluster if ECS configuration is detected
        self.ecs_cluster = self._create_ecs_cluster_if_needed()

        # Create user data (after ECS cluster so it can reference it)
        self.user_data = self._create_user_data()

        # Create launch template
        self.launch_template = self._create_launch_template(asg_name)

        # Create Auto Scaling Group
        self.auto_scaling_group = self._create_auto_scaling_group(asg_name, stable_asg_id)

        # Add scaling policies
        self._add_scaling_policies(stable_asg_id)

        # Add update policy
        self._add_update_policy()

        # Export SSM parameters
        self._export_ssm_parameters()

        logger.info(f"Auto Scaling Group {asg_name} built successfully")

    def _get_ssm_imports(self) -> Dict[str, Any]:
        """Get SSM imports from standardized mixin processing"""
        return self.get_all_ssm_imports()

    def _get_security_groups(self) -> List[ec2.ISecurityGroup]:
        """
        Get security groups for the Auto Scaling Group using standardized SSM imports.

        Returns:
            List of security group references
        """
        security_groups = []

        # Primary method: Use standardized SSM imports
        ssm_imports = self._get_ssm_imports()
        if "security_group_ids" in ssm_imports:
            imported_sg_ids = ssm_imports["security_group_ids"]
            if isinstance(imported_sg_ids, list):
                for idx, sg_id in enumerate(imported_sg_ids):
                    security_groups.append(
                        ec2.SecurityGroup.from_security_group_id(
                            self, f"SecurityGroup-SSM-{idx}", sg_id
                        )
                    )
                logger.info(
                    f"Added {len(imported_sg_ids)} security groups from SSM imports"
                )
            else:
                security_groups.append(
                    ec2.SecurityGroup.from_security_group_id(
                        self, f"SecurityGroup-SSM-0", imported_sg_ids
                    )
                )
                logger.info(f"Added security group from SSM imports")

        # Fallback: Check for direct configuration (backward compatibility)
        elif self.asg_config.security_group_ids:
            logger.warning(
                "Using direct security group configuration - consider migrating to SSM imports"
            )
            for idx, sg_id in enumerate(self.asg_config.security_group_ids):
                logger.info(f"Adding security group from direct config: {sg_id}")
                # Handle comma-separated security group IDs
                if "," in sg_id:
                    blocks = sg_id.split(",")
                    for block_idx, block in enumerate(blocks):
                        security_groups.append(
                            ec2.SecurityGroup.from_security_group_id(
                                self,
                                f"SecurityGroup-Direct-{idx}-{block_idx}",
                                block.strip(),
                            )
                        )
                else:
                    security_groups.append(
                        ec2.SecurityGroup.from_security_group_id(
                            self, f"SecurityGroup-Direct-{idx}", sg_id
                        )
                    )
        else:
            logger.warning(
                "No security groups found from SSM imports or direct configuration"
            )

        return security_groups

    def _get_vpc_id(self) -> str:
        """
        Get VPC ID using the centralized VPC provider mixin.
        """
        # Use the centralized VPC resolution from VPCProviderMixin
        vpc = self.resolve_vpc(
            config=self.asg_config, deployment=self.deployment, workload=self.workload
        )
        return vpc.vpc_id

    def _get_subnet_ids(self) -> List[str]:
        """
        Get subnet IDs using standardized SSM approach.
        """
        # Primary method: Use standardized SSM imports
        # ssm_imports = self._get_ssm_imports()

        subnet_ids = self.get_subnet_ids(self.asg_config)

        return subnet_ids

    def _create_instance_role(self, asg_name: str) -> iam.Role:
        """Create IAM role for EC2 instances"""
        role = iam.Role(
            self,
            f"{asg_name}-InstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            role_name=f"{asg_name}-role",
        )

        # Add managed policies
        for policy_name in self.asg_config.managed_policies:
            role.add_managed_policy(
                iam.ManagedPolicy.from_aws_managed_policy_name(policy_name)
            )

        logger.info(f"Created instance role: {role.role_name}")
        return role

    def _create_user_data(self) -> ec2.UserData:
        """Create user data for EC2 instances"""
        user_data = ec2.UserData.for_linux()

        # Add basic setup commands
        # this will break amazon linux 2023 which uses dnf instead of yum
        # user_data.add_commands(
        #     "#!/bin/bash",
        #     "yum update -y",
        #     "yum install -y aws-cfn-bootstrap",
        # )

        # Add user data commands from configuration
        if self.asg_config.user_data_commands:
            # Process template variables in user data commands
            processed_commands = []
            ssm_imports = self._get_ssm_imports()
            for command in self.asg_config.user_data_commands:
                processed_command = command
                # Substitute SSM-imported values
                if "cluster_name" in ssm_imports and "{{cluster_name}}" in command:
                    cluster_name = ssm_imports["cluster_name"]
                    processed_command = command.replace(
                        "{{cluster_name}}", cluster_name
                    )
                processed_commands.append(processed_command)

            user_data.add_commands(*processed_commands)
            self.user_data_commands = processed_commands

        # Add ECS cluster configuration if needed
        if self.ecs_cluster:
            # Use the SSM-imported cluster name if available, otherwise fallback to default format
            ssm_imports = self._get_ssm_imports()
            if "cluster_name" in ssm_imports:
                cluster_name = ssm_imports["cluster_name"]
                ecs_commands = [
                    f"echo 'ECS_CLUSTER={cluster_name}' >> /etc/ecs/ecs.config",
                    "systemctl restart ecs",
                ]
            else:
                # Fallback to default naming pattern
                ecs_commands = [
                    "echo 'ECS_CLUSTER={}{}' >> /etc/ecs/ecs.config".format(
                        self.deployment.workload_name, self.deployment.environment
                    ),
                    "systemctl restart ecs",
                ]
            user_data.add_commands(*ecs_commands)

        logger.info(
            f"Created user data with {len(self.user_data_commands)} custom commands"
        )
        return user_data

    def _get_or_create_vpc(self) -> ec2.Vpc:
        """Get or create VPC for reuse across the stack"""
        if self._vpc is None:
            vpc_id = self._get_vpc_id()
            subnet_ids = self._get_subnet_ids()

            # Create VPC and subnets from imported values
            self._vpc = ec2.Vpc.from_vpc_attributes(
                self,
                "ImportedVPC",
                vpc_id=vpc_id,
                availability_zones=[
                    "us-east-1a",
                    "us-east-1b",
                ],  # Add required availability zones
            )

            # Create and store subnets if we have subnet IDs
            self._subnets = []
            if subnet_ids:
                for i, subnet_id in enumerate(subnet_ids):
                    subnet = ec2.Subnet.from_subnet_id(
                        self, f"ImportedSubnet-{i}", subnet_id
                    )
                    self._subnets.append(subnet)
            else:
                # Use default subnets from VPC
                self._subnets = self._vpc.public_subnets

        return self._vpc

    def _get_subnets(self) -> List[ec2.Subnet]:
        """Get the subnets from the shared VPC"""
        return getattr(self, "_subnets", [])

    def _create_ecs_cluster_if_needed(self) -> Optional[ecs.Cluster]:
        """Create ECS cluster if ECS configuration is detected"""
        # Check if user data contains ECS configuration (use raw config since user_data_commands might not be set yet)
        ecs_detected = False
        if self.asg_config.user_data_commands:
            ecs_detected = any(
                "ECS_CLUSTER" in cmd for cmd in self.asg_config.user_data_commands
            )

        if ecs_detected:
            ssm_imports = self._get_ssm_imports()
            if "cluster_name" in ssm_imports:
                cluster_name = ssm_imports["cluster_name"]

                # Use the shared VPC
                vpc = self._get_or_create_vpc()

                self.ecs_cluster = ecs.Cluster.from_cluster_attributes(
                    self, "ImportedECSCluster", cluster_name=cluster_name, vpc=vpc
                )
                logger.info(f"Connected to existing ECS cluster: {cluster_name}")

        return self.ecs_cluster

    def _create_launch_template(self, asg_name: str) -> ec2.LaunchTemplate:
        """Create launch template for Auto Scaling Group"""

        # Use the configured AMI ID or fall back to appropriate lookup
        if self.asg_config.ami_id:
            # Use explicit AMI ID provided by user
            machine_image = ec2.MachineImage.generic_linux(
                ami_map={self.deployment.region: self.asg_config.ami_id}
            )
        elif self.asg_config.ami_type:
            # Use AMI type for dynamic lookup
            if self.asg_config.ami_type.upper() == "AMAZON-LINUX-2023":
                machine_image = ec2.MachineImage.latest_amazon_linux2023()
            elif self.asg_config.ami_type.upper() == "AMAZON-LINUX-2022":
                machine_image = ec2.MachineImage.latest_amazon_linux2022()
            elif self.asg_config.ami_type.upper() == "AMAZON-LINUX-2":
                machine_image = ec2.MachineImage.latest_amazon_linux2()
            elif self.asg_config.ami_type.upper() == "ECS_OPTIMIZED":
                # Use ECS-optimized AMI from SSM parameter
                from aws_cdk import aws_ssm as ssm

                machine_image = ec2.MachineImage.from_ssm_parameter(
                    parameter_name="/aws/service/ecs/optimized-ami/amazon-linux-2023/recommended/image_id"
                )
            else:
                # Default to latest Amazon Linux
                machine_image = ec2.MachineImage.latest_amazon_linux2023()
        else:
            # Default fallback
            machine_image = ec2.MachineImage.latest_amazon_linux2023()

        # Configure network interface if public IP is needed
        # Note: When using a launch template with ASG, associate_public_ip_address
        # must be set in the ASG's network configuration, not the launch template
        # The launch template just defines the instance configuration
        
        launch_template = ec2.LaunchTemplate(
            self,
            f"{asg_name}-LaunchTemplate",
            instance_type=ec2.InstanceType(self.asg_config.instance_type),
            machine_image=machine_image,
            role=self.instance_role,
            user_data=self.user_data,
            security_group=self.security_groups[0] if self.security_groups else None,
            key_name=self.asg_config.key_name,
            detailed_monitoring=self.asg_config.detailed_monitoring,
            associate_public_ip_address=self.asg_config.associate_public_ip_address,
            block_devices=(
                [
                    ec2.BlockDevice(
                        device_name=block_device.get("device_name", "/dev/xvda"),
                        volume=ec2.BlockDeviceVolume.ebs(
                            volume_size=block_device.get("volume_size", 8),
                            volume_type=getattr(
                                ec2.EbsDeviceVolumeType,
                                block_device.get("volume_type", "GP3").upper(),
                            ),
                            delete_on_termination=block_device.get(
                                "delete_on_termination", True
                            ),
                            encrypted=block_device.get("encrypted", False),
                        ),
                    )
                    for block_device in self.asg_config.block_devices
                ]
                if self.asg_config.block_devices
                else None
            ),
        )

        logger.info(f"Created launch template: {launch_template.launch_template_name}")
        return launch_template

    def _create_auto_scaling_group(self, asg_name: str, stable_asg_id: str) -> autoscaling.AutoScalingGroup:
        """Create Auto Scaling Group"""
        # Use the shared VPC and subnets
        vpc = self._get_or_create_vpc()
        subnets = self._get_subnets()

        health_checks = (
            # ELB + EC2 (EC2 is always included; ELB is “additional”)
            HealthChecks.with_additional_checks(
                additional_types=[AdditionalHealthCheckType.ELB],
                grace_period=Duration.seconds(
                    self.asg_config.health_check_grace_period
                ),
            )
            if self.asg_config.health_check_type.upper() == "ELB"
            # EC2-only
            else HealthChecks.ec2(
                grace_period=Duration.seconds(
                    self.asg_config.health_check_grace_period
                ),
            )
        )
        auto_scaling_group = autoscaling.AutoScalingGroup(
            self,
            stable_asg_id,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=subnets),
            launch_template=self.launch_template,
            min_capacity=self.asg_config.min_capacity,
            max_capacity=self.asg_config.max_capacity,
            desired_capacity=self.asg_config.desired_capacity,
            health_checks=health_checks,
            cooldown=cdk.Duration.seconds(self.asg_config.cooldown),
            termination_policies=[
                getattr(autoscaling.TerminationPolicy, policy.upper())
                for policy in self.asg_config.termination_policies
            ],
        )

        # Add instance refresh if configured
        if self.asg_config.instance_refresh:
            self._configure_instance_refresh(auto_scaling_group)

        # Attach target groups if configured
        self._attach_target_groups(auto_scaling_group)

        logger.info(f"Created Auto Scaling Group: {asg_name}")
        return auto_scaling_group

    def _attach_target_groups(self, asg: autoscaling.AutoScalingGroup) -> None:
        """Attach the Auto Scaling Group to target groups"""
        target_group_arns = self._get_target_group_arns()

        if not target_group_arns:
            logger.warning("No target group ARNs found for Auto Scaling Group")
            return

        # Get the underlying CloudFormation resource to add target group ARNs
        cfn_asg = asg.node.default_child
        cfn_asg.add_property_override("TargetGroupARNs", target_group_arns)

    def _get_target_group_arns(self) -> List[str]:
        """Get target group ARNs using standardized SSM approach"""
        target_group_arns = []

        # Use standardized SSM imports
        ssm_imports = self._get_ssm_imports()
        if "target_group_arns" in ssm_imports:
            imported_arns = ssm_imports["target_group_arns"]
            if isinstance(imported_arns, list):
                target_group_arns.extend(imported_arns)
            else:
                target_group_arns.append(imported_arns)

        # Fallback: Direct configuration
        elif self.asg_config.target_group_arns:
            target_group_arns.extend(self.asg_config.target_group_arns)

        return target_group_arns

    def _add_scaling_policies(self, stable_asg_id: str) -> None:
        """Add scaling policies to the Auto Scaling Group"""
        if not self.asg_config.scaling_policies:
            return

        for policy_config in self.asg_config.scaling_policies:
            if policy_config.get("type") == "target_tracking":
                # Create a target tracking scaling policy for CPU utilization
                scaling_policy = autoscaling.CfnScalingPolicy(
                    self,
                    f"{stable_asg_id}-CPUScalingPolicy",
                    auto_scaling_group_name=self.auto_scaling_group.auto_scaling_group_name,
                    policy_type="TargetTrackingScaling",
                    target_tracking_configuration=autoscaling.CfnScalingPolicy.TargetTrackingConfigurationProperty(
                        target_value=policy_config.get("target_cpu", 70),
                        predefined_metric_specification=autoscaling.CfnScalingPolicy.PredefinedMetricSpecificationProperty(
                            predefined_metric_type="ASGAverageCPUUtilization"
                        ),
                    ),
                )
                logger.info("Added CPU utilization scaling policy")

    def _add_update_policy(self) -> None:
        """Add update policy to the Auto Scaling Group"""
        update_policy = self.asg_config.update_policy

        if not update_policy:
            # No update policy configured, don't add one
            return

        # Get the underlying CloudFormation resource to add update policy
        cfn_asg = self.auto_scaling_group.node.default_child

        # Get CDK's default policy first (if any)
        default_policy = getattr(cfn_asg, "update_policy", {})

        # Merge with defaults, then use the robust add_override method
        merged_policy = {
            **default_policy,  # Preserve CDK defaults
            "AutoScalingRollingUpdate": {
                "MinInstancesInService": update_policy.get(
                    "min_instances_in_service", 1
                ),
                "MaxBatchSize": update_policy.get("max_batch_size", 1),
                "PauseTime": f"PT{update_policy.get('pause_time', 300)}S",
            },
        }

        # Use the robust CDK-documented approach
        cfn_asg.add_override("UpdatePolicy", merged_policy)

        logger.info("Added rolling update policy to Auto Scaling Group")

    def _export_ssm_parameters(self) -> None:
        """Export SSM parameters using standardized approach"""
        if not self.auto_scaling_group:
            logger.warning("No Auto Scaling Group to export")
            return

        # Prepare resource values for export
        resource_values = {
            "auto_scaling_group_name": self.auto_scaling_group.auto_scaling_group_name,
            "auto_scaling_group_arn": self.auto_scaling_group.auto_scaling_group_arn,
        }

        # Export using standardized SSM mixin
        exported_params = self.export_ssm_parameters(resource_values)

        logger.info(f"Exported SSM parameters: {exported_params}")

    def _configure_instance_refresh(self, asg: autoscaling.AutoScalingGroup) -> None:
        """Configure instance refresh for rolling updates"""
        instance_refresh_config = self.asg_config.instance_refresh

        if not instance_refresh_config.get("enabled", False):
            return

        logger.warning("Instance refresh is not supported in this version of the CDK")
        return

        # Get the CloudFormation ASG resource
        cfn_asg = asg.node.default_child

        # Configure instance refresh using CloudFormation UpdatePolicy
        # UpdatePolicy is added at the resource level, not as a property
        update_policy = {
            "AutoScalingRollingUpdate": {
                "PauseTime": "PT300S",  # 5 minutes pause
                "MinInstancesInService": "1",
                "MaxBatchSize": "1",
                "WaitOnResourceSignals": True,
                "SuspendProcesses": [
                    "HealthCheck",
                    "ReplaceUnhealthy",
                    "AZRebalance",
                    "AlarmNotification",
                    "ScheduledActions",
                ],
            }
        }

        # # Apply instance refresh using CloudFormation's cfn_options.update_policy
        # cfn_asg.cfn_options.update_policy = cdk.CfnUpdatePolicy.from_rolling_update(
        #     pause_time=cdk.Duration.seconds(300),
        #     min_instances_in_service=1,
        #     max_batch_size=1,
        #     wait_on_resource_signals=True
        # )

        # Grab the L1 to attach UpdatePolicy.InstanceRefresh
        cfn_asg: autoscaling.CfnAutoScalingGroup = asg.node.default_child

        # cfn_asg.cfn_options.update_policy = CfnUpdatePolicy.from_auto_scaling_instance_refresh(
        #     # Triggers tell CFN *what* changes should start a refresh
        #     triggers=[CfnUpdatePolicy.InstanceRefreshTrigger.LAUNCH_TEMPLATE],
        #     preferences=CfnUpdatePolicy.InstanceRefreshPreferences(
        #         # warmup is like “grace” before counting a new instance healthy
        #         instance_warmup=Duration.minutes(5),
        #         # how aggressive the refresh is; 90 keeps capacity high
        #         min_healthy_percentage=90,
        #         # skip instances that already match the new LT (fast when only userdata/env tweaked)
        #         skip_matching=True,
        #         # optional: put instances in Standby first; default is rolling terminate/launch
        #         # standby_instances=CfnUpdatePolicy.StandbyInstances.TERMINATE,
        #         # checkpoint_percentages=[25, 50, 75],   # optional: progressive checkpoints
        #         # checkpoint_delay=Duration.minutes(2),  # optional delay at checkpoints
        #     ),
        # )
        logger.info(f"Configured instance refresh via CDK CfnUpdatePolicy")

        # Note: This provides rolling update functionality similar to instance refresh
        # For true instance refresh with preferences, we would need CDK v2.80+ or custom CloudFormation


# Backward compatibility alias
AutoScalingStackStandardized = AutoScalingStack
