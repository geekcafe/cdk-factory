"""
Auto Scaling Group Stack Pattern for CDK-Factory
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Dict, Any, List, Optional

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_autoscaling as autoscaling
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_iam as iam
from aws_cdk import aws_ssm as ssm
from aws_cdk import Duration
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.auto_scaling import AutoScalingConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.enhanced_ssm_parameter_mixin import EnhancedSsmParameterMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="AutoScalingStack")


@register_stack("auto_scaling_library_module")
@register_stack("auto_scaling_stack")
class AutoScalingStack(IStack, EnhancedSsmParameterMixin):
    """
    Reusable stack for AWS Auto Scaling Groups.
    Supports creating EC2 Auto Scaling Groups with customizable configurations.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.asg_config = None
        self.stack_config = None
        self.deployment = None
        self.workload = None
        self.security_groups = []
        self.auto_scaling_group = None
        self.launch_template = None
        self.instance_role = None
        self.user_data = None
        self._vpc = None

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
        asg_name = deployment.build_resource_name(self.asg_config.name)

        # Get VPC and security groups
        self.security_groups = self._get_security_groups()

        # Create IAM role for instances
        self.instance_role = self._create_instance_role(asg_name)

        # Create user data
        self.user_data = self._create_user_data()

        # Create launch template
        self.launch_template = self._create_launch_template(asg_name)

        # Create auto scaling group
        self.auto_scaling_group = self._create_auto_scaling_group(asg_name)

        # Configure scaling policies
        self._configure_scaling_policies()

        # Add outputs
        self._add_outputs(asg_name)

    @property
    def vpc(self) -> ec2.IVpc:
        """Get the VPC for the Auto Scaling Group"""
        # Assuming VPC is provided by the workload

        if self._vpc:
            return self._vpc

        elif self.asg_config.vpc_id:
            self._vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id=self.asg_config.vpc_id)
        elif self.workload.vpc_id:
            self._vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id=self.workload.vpc_id)
        else:
            # Use default VPC if not provided
            raise ValueError(
                "VPC is not defined in the configuration.  "
                "You can provide it a the auto_scaling.vpc_id in the configuration "
                "or a top level workload.vpc_id in the workload configuration."
            )

        return self._vpc

    def _get_target_group_arns(self) -> List[str]:
        """Get target group ARNs from SSM imports"""
        target_group_arns = []

        # Import target group ARNs using the SSM import pattern
        imported_values = self.import_resources_from_ssm(
            scope=self,
            config=self.asg_config,
            resource_name=self.asg_config.name,
            resource_type="auto-scaling",
        )

        # Look for target group ARN imports
        for key, value in imported_values.items():
            if "target_group" in key and "arn" in key:
                target_group_arns.append(value)

        # see if we have any directly defined in the config
        if self.asg_config.target_group_arns:
            for arn in self.asg_config.target_group_arns:
                logger.info(f"Adding target group ARN: {arn}")
                target_group_arns.append(arn)

        return target_group_arns

    def _attach_target_groups(self, asg: autoscaling.AutoScalingGroup) -> None:
        """Attach the Auto Scaling Group to target groups"""
        target_group_arns = self._get_target_group_arns()

        if not target_group_arns:
            logger.warning("No target group ARNs found for Auto Scaling Group")
            print(
                "⚠️ No target group ARNs found for Auto Scaling Group.  Nothing will be attached."
            )
            return

        # Get the underlying CloudFormation resource to add target group ARNs
        cfn_asg = asg.node.default_child
        cfn_asg.add_property_override("TargetGroupARNs", target_group_arns)

    def _get_security_groups(self) -> List[ec2.ISecurityGroup]:
        """Get security groups for the Auto Scaling Group"""
        security_groups = []
        for sg_id in self.asg_config.security_group_ids:
            # if the security group id contains a comma, it is a list of security group ids
            if "," in sg_id:
                blocks = sg_id.split(",")
                for block in blocks:
                    security_groups.append(
                        ec2.SecurityGroup.from_security_group_id(
                            self, f"SecurityGroup-{block}", block
                        )
                    )
            else:
                # TODO: add some additional checks to make it more robust
                security_groups.append(
                    ec2.SecurityGroup.from_security_group_id(
                        self, f"SecurityGroup-{sg_id}", sg_id
                    )
                )
        return security_groups

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

        return role

    def _create_user_data(self) -> ec2.UserData:
        """Create user data for EC2 instances"""
        user_data = ec2.UserData.for_linux()

        # Add base commands
        user_data.add_commands("set -euxo pipefail")

        # Add custom commands from config
        for command in self.asg_config.user_data_commands:
            user_data.add_commands(command)

        # Add container configuration if specified
        container_config = self.asg_config.container_config
        if container_config:
            self._add_container_user_data(user_data, container_config)

        return user_data

    def _add_container_user_data(
        self, user_data: ec2.UserData, container_config: Dict[str, Any]
    ) -> None:
        """Add container-specific user data commands"""
        # Install Docker
        user_data.add_commands(
            "dnf -y update", "dnf -y install docker jq", "systemctl enable --now docker"
        )

        # ECR configuration
        if "ecr" in container_config:
            ecr_config = container_config["ecr"]
            user_data.add_commands(
                f"ACCOUNT_ID={ecr_config.get('account_id', self.account)}",
                f"REGION={ecr_config.get('region', self.region)}",
                f"REPO={ecr_config.get('repo', 'app')}",
                f"TAG={ecr_config.get('tag', 'latest')}",
                "aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com",
                "docker pull ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO}:${TAG}",
            )

        # Database configuration
        if "database" in container_config:
            db_config = container_config["database"]
            secret_arn = db_config.get("secret_arn", "")
            if secret_arn:
                user_data.add_commands(
                    f"DB_SECRET_ARN={secret_arn}",
                    'if [ -n "$DB_SECRET_ARN" ]; then DB_JSON=$(aws secretsmanager get-secret-value --secret-id $DB_SECRET_ARN --query SecretString --output text --region $REGION); fi',
                    'if [ -n "$DB_SECRET_ARN" ]; then DB_HOST=$(echo $DB_JSON | jq -r .host); DB_USER=$(echo $DB_JSON | jq -r .username); DB_PASS=$(echo $DB_JSON | jq -r .password); DB_NAME=$(echo $DB_JSON | jq -r .dbname); fi',
                )

        # Run container
        if "run_command" in container_config:
            user_data.add_commands(container_config["run_command"])
        elif "ecr" in container_config:
            port = container_config.get("port", 8080)
            user_data.add_commands(
                f"docker run -d --name app -p {port}:{port} "
                '-e DB_HOST="$DB_HOST" -e DB_USER="$DB_USER" -e DB_PASS="$DB_PASS" -e DB_NAME="$DB_NAME" '
                "--restart=always ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO}:${TAG}"
            )

    def _create_launch_template(self, asg_name: str) -> ec2.LaunchTemplate:
        """Create launch template for the Auto Scaling Group"""
        # Get AMI
        ami = None
        if self.asg_config.ami_id:
            ami = ec2.MachineImage.generic_linux({self.region: self.asg_config.ami_id})
        else:
            if self.asg_config.ami_type == "amazon-linux-2023":
                ami = ec2.MachineImage.latest_amazon_linux2023()
            elif self.asg_config.ami_type == "amazon-linux-2":
                ami = ec2.MachineImage.latest_amazon_linux2()
            else:
                ami = ec2.MachineImage.latest_amazon_linux2023()

        # Parse instance type
        instance_type_str = self.asg_config.instance_type
        instance_type = None

        if "." in instance_type_str:
            parts = instance_type_str.split(".")
            if len(parts) == 2:
                try:
                    instance_class = ec2.InstanceClass[parts[0].upper()]
                    instance_size = ec2.InstanceSize[parts[1].upper()]
                    instance_type = ec2.InstanceType.of(instance_class, instance_size)
                except (KeyError, ValueError):
                    instance_type = ec2.InstanceType(instance_type_str)
            else:
                instance_type = ec2.InstanceType(instance_type_str)
        else:
            instance_type = ec2.InstanceType(instance_type_str)

        # Create block device mappings
        block_devices = []
        for device in self.asg_config.block_devices:
            block_devices.append(
                ec2.BlockDevice(
                    device_name=device.get("device_name", "/dev/xvda"),
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=device.get("volume_size", 8),
                        volume_type=ec2.EbsDeviceVolumeType(
                            str(device.get("volume_type", "gp3")).upper()
                        ),
                        delete_on_termination=device.get("delete_on_termination", True),
                        encrypted=device.get("encrypted", True),
                    ),
                )
            )

        # Create launch template
        launch_template = ec2.LaunchTemplate(
            self,
            f"{asg_name}-LaunchTemplate",
            machine_image=ami,
            instance_type=instance_type,
            role=self.instance_role,
            security_group=self.security_groups[0] if self.security_groups else None,
            user_data=self.user_data,
            detailed_monitoring=self.asg_config.detailed_monitoring,
            block_devices=block_devices if block_devices else None,
        )

        return launch_template

    def _create_auto_scaling_group(self, asg_name: str) -> autoscaling.AutoScalingGroup:
        """Create the Auto Scaling Group"""
        # Configure subnet selection
        subnet_group_name = self.asg_config.subnet_group_name
        subnets = ec2.SubnetSelection(subnet_group_name=subnet_group_name)

        # Configure health check
        health_check_type = autoscaling.HealthCheck.ec2()
        if self.asg_config.health_check_type.upper() == "ELB":
            health_check_type = autoscaling.HealthCheck.elb(
                grace=Duration.seconds(self.asg_config.health_check_grace_period)
            )

        # Create Auto Scaling Group
        asg = autoscaling.AutoScalingGroup(
            self,
            asg_name,
            vpc=self.vpc,
            vpc_subnets=subnets,
            min_capacity=self.asg_config.min_capacity,
            max_capacity=self.asg_config.max_capacity,
            desired_capacity=self.asg_config.desired_capacity,
            launch_template=self.launch_template,
            health_check=health_check_type,
            cooldown=Duration.seconds(self.asg_config.cooldown),
            termination_policies=[
                autoscaling.TerminationPolicy(policy)
                for policy in self.asg_config.termination_policies
            ],
        )

        # Attach to target groups after ASG creation
        self._attach_target_groups(asg)

        # Configure update policy
        # Only apply update policy if it was explicitly configured
        if "update_policy" in self.stack_config.dictionary.get("auto_scaling", {}):
            update_policy = self.asg_config.update_policy
            # Apply the update policy to the ASG's CloudFormation resource
            cfn_asg = asg.node.default_child
            cfn_asg.add_override(
                "UpdatePolicy",
                {
                    "AutoScalingRollingUpdate": {
                        "MinInstancesInService": update_policy.get(
                            "min_instances_in_service", 1
                        ),
                        "MaxBatchSize": update_policy.get("max_batch_size", 1),
                        "PauseTime": f"PT{update_policy.get('pause_time', 300) // 60}M",
                    }
                },
            )

        # Add tags
        for key, value in self.asg_config.tags.items():
            cdk.Tags.of(asg).add(key, value)

        return asg

    def _configure_scaling_policies(self) -> None:
        """Configure scaling policies for the Auto Scaling Group"""
        for policy in self.asg_config.scaling_policies:
            policy_type = policy.get("type", "target_tracking")

            if policy_type == "target_tracking":
                self.auto_scaling_group.scale_on_metric(
                    f"{self.asg_config.name}-{policy.get('name', 'scaling-policy')}",
                    metric=self._get_metric(policy),
                    scaling_steps=self._get_scaling_steps(policy),
                    adjustment_type=autoscaling.AdjustmentType.CHANGE_IN_CAPACITY,
                )
            elif policy_type == "step":
                self.auto_scaling_group.scale_on_metric(
                    f"{self.asg_config.name}-{policy.get('name', 'scaling-policy')}",
                    metric=self._get_metric(policy),
                    scaling_steps=self._get_scaling_steps(policy),
                    adjustment_type=autoscaling.AdjustmentType.CHANGE_IN_CAPACITY,
                )

    def _get_metric(self, policy: Dict[str, Any]) -> cloudwatch.Metric:
        """Get metric for scaling policy"""
        # This is a simplified implementation
        # In a real-world scenario, you would use CloudWatch metrics
        return cloudwatch.Metric(
            namespace="AWS/EC2",
            metric_name=policy.get("metric_name", "CPUUtilization"),
            dimensions_map={
                "AutoScalingGroupName": self.auto_scaling_group.auto_scaling_group_name
            },
            statistic=policy.get("statistic", "Average"),
            period=Duration.seconds(policy.get("period", 60)),
        )

    def _get_scaling_steps(
        self, policy: Dict[str, Any]
    ) -> List[autoscaling.ScalingInterval]:
        """Get scaling steps for scaling policy"""
        steps = policy.get("steps", [])
        scaling_intervals = []

        for step in steps:
            # Handle upper bound - if not specified, don't set it (let CDK handle it)
            interval_kwargs = {
                "lower": step.get("lower", 0),
                "change": step.get("change", 1),
            }

            # Only set upper if it's explicitly provided
            if "upper" in step:
                interval_kwargs["upper"] = step["upper"]

            scaling_intervals.append(autoscaling.ScalingInterval(**interval_kwargs))

        return scaling_intervals

    def _add_outputs(self, asg_name: str) -> None:
        """Add CloudFormation outputs for the Auto Scaling Group"""
        if self.auto_scaling_group:
            # Auto Scaling Group Name
            cdk.CfnOutput(
                self,
                f"{asg_name}-name",
                value=self.auto_scaling_group.auto_scaling_group_name,
                export_name=f"{self.deployment.build_resource_name(asg_name)}-name",
            )

            # Auto Scaling Group ARN
            cdk.CfnOutput(
                self,
                f"{asg_name}-arn",
                value=self.auto_scaling_group.auto_scaling_group_arn,
                export_name=f"{self.deployment.build_resource_name(asg_name)}-arn",
            )

            # Launch Template ID
            if self.launch_template:
                cdk.CfnOutput(
                    self,
                    f"{asg_name}-launch-template-id",
                    value=self.launch_template.launch_template_id,
                    export_name=f"{self.deployment.build_resource_name(asg_name)}-launch-template-id",
                )

            # Instance Role ARN
            if self.instance_role:
                cdk.CfnOutput(
                    self,
                    f"{asg_name}-instance-role-arn",
                    value=self.instance_role.role_arn,
                    export_name=f"{self.deployment.build_resource_name(asg_name)}-instance-role-arn",
                )
