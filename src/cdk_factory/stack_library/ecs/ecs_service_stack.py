"""
ECS Service Stack Pattern for CDK-Factory
Supports Fargate and EC2 launch types with auto-scaling, load balancing, and blue-green deployments.
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

from typing import Dict, Any, List, Optional

import aws_cdk as cdk
from aws_cdk import (
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_logs as logs,
    aws_iam as iam,
    aws_elasticloadbalancingv2 as elbv2,
    aws_applicationautoscaling as appscaling,
)
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.ecs_service import EcsServiceConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.vpc_provider_mixin import VPCProviderMixin
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="EcsServiceStack")


@register_stack("ecs_service_library_module")
@register_stack("ecs_service_stack")
@register_stack("fargate_service_stack")
class EcsServiceStack(IStack, VPCProviderMixin, StandardizedSsmMixin):
    """
    Reusable stack for ECS/Fargate services with Docker container support.
    Supports blue-green deployments, maintenance mode, and auto-scaling.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.ecs_config: Optional[EcsServiceConfig] = None
        self.stack_config: Optional[StackConfig] = None
        self.deployment: Optional[DeploymentConfig] = None
        self.workload: Optional[WorkloadConfig] = None
        self.cluster: Optional[ecs.ICluster] = None
        self.service: Optional[ecs.FargateService] = None
        self.task_definition: Optional[ecs.FargateTaskDefinition] | Optional[ecs.EcsTaskDefinition] = None
        self._vpc: Optional[ec2.IVpc] = None
        # SSM imported values
        self.ssm_imported_values: Dict[str, Any] = {}

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Build the ECS Service stack"""
        self._build(stack_config, deployment, workload)

    def _build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Internal build method for the ECS Service stack"""
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload
        
        # Load ECS configuration
        self.ecs_config = EcsServiceConfig(
            stack_config.dictionary.get("ecs_service") or stack_config.dictionary.get("ecs", {})
        )
        
        service_name = deployment.build_resource_name(self.ecs_config.name)
        
        # Process SSM imports first
        self._process_ssm_imports()
        
        # Load VPC
        self._load_vpc()
        
        # Create or load ECS cluster
        self._create_or_load_cluster()
        
        # Create task definition
        self._create_task_definition(service_name)
        
        # Create ECS service
        self._create_service(service_name)
        
        # Setup auto-scaling
        if self.ecs_config.enable_auto_scaling:
            self._setup_auto_scaling()
        
        # Add outputs
        self._add_outputs(service_name)
        self._export_to_ssm(service_name)

    def _load_vpc(self) -> None:
        """Load VPC using the centralized VPC provider mixin."""
        # Use the centralized VPC resolution from VPCProviderMixin
        self._vpc = self.resolve_vpc(
            config=self.ecs_config,
            deployment=self.deployment,
            workload=self.workload
        )

    def _process_ssm_imports(self) -> None:
        """
        Process SSM imports from configuration.
        Follows the same pattern as RDS, Load Balancer, and Security Group stacks.
        """
        from aws_cdk import aws_ssm as ssm
        
        ssm_imports = self.ecs_config.ssm_imports
        
        if not ssm_imports:
            logger.debug("No SSM imports configured for ECS Service")
            return
        
        logger.info(f"Processing {len(ssm_imports)} SSM imports for ECS Service")
        
        for param_key, param_value in ssm_imports.items():
            try:
                # Handle list values (like security_group_ids)
                if isinstance(param_value, list):
                    imported_list = []
                    for idx, param_path in enumerate(param_value):
                        if not param_path.startswith('/'):
                            param_path = f"/{param_path}"
                        
                        construct_id = f"ssm-import-{param_key}-{idx}-{hash(param_path) % 10000}"
                        param = ssm.StringParameter.from_string_parameter_name(
                            self, construct_id, param_path
                        )
                        imported_list.append(param.string_value)
                    
                    self.ssm_imported_values[param_key] = imported_list
                    logger.info(f"Imported SSM parameter list: {param_key} with {len(imported_list)} items")
                else:
                    # Handle string values
                    param_path = param_value
                    if not param_path.startswith('/'):
                        param_path = f"/{param_path}"
                    
                    construct_id = f"ssm-import-{param_key}-{hash(param_path) % 10000}"
                    param = ssm.StringParameter.from_string_parameter_name(
                        self, construct_id, param_path
                    )
                    
                    self.ssm_imported_values[param_key] = param.string_value
                    logger.info(f"Imported SSM parameter: {param_key} from {param_path}")
                    
            except Exception as e:
                logger.error(f"Failed to import SSM parameter {param_key}: {e}")
                raise

    def _create_or_load_cluster(self) -> None:
        """Create a new ECS cluster or load an existing one"""
        cluster_name = self.ecs_config.cluster_name
        
        if cluster_name:
            # Try to load existing cluster
            try:
                self.cluster = ecs.Cluster.from_cluster_attributes(
                    self,
                    "Cluster",
                    cluster_name=cluster_name,
                    vpc=self._vpc,
                )
                logger.info(f"Using existing cluster: {cluster_name}")
            except Exception as e:
                logger.warning(f"Could not load cluster {cluster_name}, creating new one: {e}")
                self._create_new_cluster(cluster_name)
        else:
            # Create a new cluster with auto-generated name
            cluster_name = f"{self.deployment.workload_name}-{self.deployment.environment}-cluster"
            self._create_new_cluster(cluster_name)

    def _create_new_cluster(self, cluster_name: str) -> None:
        """Create a new ECS cluster"""
        self.cluster = ecs.Cluster(
            self,
            "Cluster",
            cluster_name=cluster_name,
            vpc=self._vpc,
            container_insights=True,
        )
        
        cdk.Tags.of(self.cluster).add("Name", cluster_name)
        cdk.Tags.of(self.cluster).add("Environment", self.deployment.environment)

    def _create_task_definition(self, service_name: str) -> None:
        """Create ECS task definition with container definitions"""
        
        # Create task execution role
        execution_role = iam.Role(
            self,
            "TaskExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                ),
            ],
        )
        
        # Create task role for application permissions
        task_role = iam.Role(
            self,
            "TaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        
        # Enable ECS Exec if configured
        if self.ecs_config.enable_execute_command:
            task_role.add_managed_policy(
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "CloudWatchAgentServerPolicy"
                )
            )

        # add any custom policies
        self._add_custom_task_policies(task_role)
        
        # Create task definition based on launch type
        if self.ecs_config.launch_type == "EC2":
            # EC2 task definition
            network_mode = self.ecs_config.task_definition.get("network_mode", "bridge")
            self.task_definition = ecs.Ec2TaskDefinition(
                self,
                "TaskDefinition",
                family=f"{service_name}-task",
                network_mode=ecs.NetworkMode(network_mode.upper()) if network_mode else ecs.NetworkMode.BRIDGE,
                execution_role=execution_role,
                task_role=task_role,
            )
        else:
            # Fargate task definition
            self.task_definition = ecs.FargateTaskDefinition(
                self,
                "TaskDefinition",
                family=f"{service_name}-task",
                cpu=int(self.ecs_config.cpu),
                memory_limit_mib=int(self.ecs_config.memory),
                execution_role=execution_role,
                task_role=task_role,
            )
        
        # Add volumes to task definition
        self._add_volumes_to_task()
        
        # Add containers
        self._add_containers_to_task()

    def _add_custom_task_policies(self, task_role: iam.Role) -> None:
        """
        Add custom task policies to the task definition.
        """

        resource_id = 1
        for policy in self.ecs_config.task_definition.get("policies", []):

            effect = policy.get("effect", "Allow")
            action = policy.get("action", None)
            actions = policy.get("actions", [])
            if action:
                actions.append(action)
            
            resources = policy.get("resources", [])
            resource = policy.get("resource", None)
            if resource:
                resources.append(resource)

            # Resolve SSM parameters in resource ARNs (resolve_ssm_value handles embedded SSM refs)
            resolved_resources = []
            for resource in resources:
                policy_name = policy.get("name", "unnamed")
                ssm_id = f"policy-{policy_name}-{resource_id}-resource"
                resource_id += 1
                resolved_resource = self.resolve_ssm_value(self, str(resource), ssm_id)
                resolved_resources.append(resolved_resource)
            
            resources = resolved_resources

            if effect == "Allow" and actions:
                effect = iam.Effect.ALLOW
            if effect == "Deny" and actions:
                effect = iam.Effect.DENY

            sid = policy.get("sid", None)
            task_role.add_to_policy(
                iam.PolicyStatement(
                    effect=effect,
                    actions=actions,
                    resources=resources,
                    sid=sid,
                )
            )

    def _add_volumes_to_task(self) -> None:
        """
        Add volumes to the task definition.
        Supports host volumes for EC2 launch type and EFS volumes for both.
        """
        volumes = self.ecs_config.volumes
        
        if not volumes:
            return  # No volumes to add
        
        for volume_config in volumes:
            volume_name = volume_config.get("name")
            if not volume_name:
                logger.warning("Volume name is required, skipping")
                continue
            
            # Check volume type
            if "host" in volume_config:
                # Host volume (bind mount for EC2)
                if self.ecs_config.launch_type != "EC2":
                    logger.warning(f"Host volumes are only supported for EC2 launch type, skipping volume {volume_name}")
                    continue
                
                host_config = volume_config["host"]
                source_path = host_config.get("source_path")
                
                if not source_path:
                    logger.warning(f"Host source_path is required for volume {volume_name}, skipping")
                    continue
                
                # Add host volume to task definition
                self.task_definition.add_volume(
                    name=volume_name,
                    host=ecs.Host(source_path=source_path)
                )
                
                logger.info(f"Added host volume: {volume_name} -> {source_path}")
                
            elif "efs" in volume_config:
                # EFS volume (supported for both EC2 and Fargate)
                efs_config = volume_config["efs"]
                file_system_id = efs_config.get("file_system_id")
                
                if not file_system_id:
                    logger.warning(f"EFS file_system_id is required for volume {volume_name}, skipping")
                    continue
                
                # Build EFS volume configuration
                efs_volume_config = ecs.EfsVolumeConfiguration(
                    file_system_id=file_system_id,
                    root_directory=efs_config.get("root_directory", "/"),
                    transit_encryption="ENABLED" if efs_config.get("transit_encryption", True) else "DISABLED",
                    authorization_config=ecs.AuthorizationConfig(
                        access_point_id=efs_config.get("access_point_id")
                    ) if efs_config.get("access_point_id") else None
                )
                
                self.task_definition.add_volume(
                    name=volume_name,
                    efs_volume_configuration=efs_volume_config
                )
                
                logger.info(f"Added EFS volume: {volume_name} -> {file_system_id}")
            else:
                logger.warning(f"Volume {volume_name} must specify either 'host' or 'efs' configuration")

    def _add_containers_to_task(self) -> None:
        """Add container definitions to the task"""
        container_definitions = self.ecs_config.container_definitions
        
        if not container_definitions:
            raise ValueError("At least one container definition is required")
        
        for idx, container_config in enumerate(container_definitions):
            container_name = container_config.get("name", f"container-{idx}")
            image_uri = container_config.get("image")
            tag_override = container_config.get("tag_override")
            if tag_override:
                logger.info(f"Tag override for {container_name}: {tag_override}")
                # find the end of the image uri
                end_of_image_uri = image_uri.rfind(":")
                if end_of_image_uri == -1:
                    # raise ValueError(f"Invalid image URI for {container_name}")
                    logger.warning(f"Invalid image URI for {container_name}")
                    # attempt to set it anyway
                    image_uri = image_uri + ":" + tag_override
                else:
                    image_uri = image_uri[:end_of_image_uri] + ":" + tag_override
            if not image_uri:
                raise ValueError(f"Container image is required for {container_name}")
            
            logger.info(f"Adding container: {container_name} -> {image_uri}")

            # Create log group for container
            log_group = logs.LogGroup(
                self,
                f"LogGroup-{container_name}",
                log_group_name=f"/ecs/{self.deployment.workload_name}/{self.deployment.environment}/{container_name}",
                retention=logs.RetentionDays.ONE_WEEK,
                removal_policy=cdk.RemovalPolicy.DESTROY,
            )
            
            # Build health check if configured
            health_check_config = container_config.get("health_check")
            health_check = None
            if health_check_config:
                health_check = ecs.HealthCheck(
                    command=health_check_config.get("command", ["CMD-SHELL", "exit 0"]),
                    interval=cdk.Duration.seconds(health_check_config.get("interval", 30)),
                    timeout=cdk.Duration.seconds(health_check_config.get("timeout", 5)),
                    retries=health_check_config.get("retries", 3),
                    start_period=cdk.Duration.seconds(health_check_config.get("start_period", 0)),
                )
            
            # Build linux parameters if configured
            linux_parameters_config = container_config.get("linux_parameters")
            linux_parameters = None
            if linux_parameters_config:
                linux_parameters = self._build_linux_parameters(linux_parameters_config)
            
            # Add container to task definition
            container = self.task_definition.add_container(
                container_name,
                image=ecs.ContainerImage.from_registry(image_uri),
                logging=ecs.LogDriver.aws_logs(
                    stream_prefix=container_name,
                    log_group=log_group,
                ),
                environment=self._load_environment_variables(container_config.get("environment", {})),
                secrets=self._load_secrets(container_config.get("secrets", {})),
                cpu=container_config.get("cpu"),
                memory_limit_mib=container_config.get("memory"),
                memory_reservation_mib=container_config.get("memory_reservation"),
                essential=container_config.get("essential", True),
                health_check=health_check,
                linux_parameters=linux_parameters,
                privileged=container_config.get("privileged", False),
            )
            
            # Add port mappings
            port_mappings = container_config.get("port_mappings", [])
            for port_mapping in port_mappings:
                container.add_port_mappings(
                    ecs.PortMapping(
                        container_port=port_mapping.get("container_port", 80),
                        protocol=ecs.Protocol.TCP,
                    )
                )
            
            # Add mount points (bind volumes to container)
            mount_points = container_config.get("mount_points", [])
            for mount_point in mount_points:
                source_volume = mount_point.get("source_volume")
                container_path = mount_point.get("container_path")
                read_only = mount_point.get("read_only", False)
                
                if not source_volume or not container_path:
                    logger.warning(f"Mount point requires source_volume and container_path, skipping")
                    continue
                
                container.add_mount_points(
                    ecs.MountPoint(
                        source_volume=source_volume,
                        container_path=container_path,
                        read_only=read_only
                    )
                )
                
                logger.info(f"Added mount point: {source_volume} -> {container_path} (read_only={read_only})")

    def _build_linux_parameters(self, config: Dict[str, Any]) -> ecs.LinuxParameters:
        """Build Linux parameters for container including device mappings"""
        linux_params = ecs.LinuxParameters(self, f"LinuxParams-{id(config)}")
        
        # Add device mappings (e.g., /dev/fuse)
        devices = config.get("devices", [])
        for device in devices:
            host_path = device.get("host_path")
            container_path = device.get("container_path", host_path)
            permissions = device.get("permissions", ["read", "write"])
            
            if not host_path:
                logger.warning("Device mapping requires host_path, skipping")
                continue
            
            # Map permissions to ECS DevicePermission
            device_permissions = []
            for perm in permissions:
                if perm.lower() == "read":
                    device_permissions.append(ecs.DevicePermission.READ)
                elif perm.lower() == "write":
                    device_permissions.append(ecs.DevicePermission.WRITE)
                elif perm.lower() == "mknod":
                    device_permissions.append(ecs.DevicePermission.MKNOD)
            
            linux_params.add_devices(
                ecs.Device(
                    host_path=host_path,
                    container_path=container_path,
                    permissions=device_permissions,
                )
            )
            logger.info(f"Added device mapping: {host_path} -> {container_path} with permissions {permissions}")
        
        return linux_params

    def _load_environment_variables(self, environment_variables_config: Dict[str, str]) -> Dict[str, str]:
        """Load environment variables from SSM Parameter Store"""
        environment_variables = {}

        for key, value in environment_variables_config.items():
            
            value = self.resolve_ssm_value(scope=self, value=value, unique_id=key)
            
            environment_variables[key] = value
        
        return environment_variables

    def _load_secrets(self, secrets_config: Dict[str, str]) -> Dict[str, ecs.Secret]:
        """Load secrets from Secrets Manager or SSM Parameter Store"""
        secrets = {}
        # TODO
        # for key, value in secrets_config.items():
        #     self.logger.info(f"Loading secret: {key} -> {value}")
        #     value = self.resolve_ssm_value(value)
            
        #     secrets[key] = value

        # Implement secret loading logic here
        # This would integrate with AWS Secrets Manager or SSM Parameter Store
        return secrets

    def _create_service(self, service_name: str) -> None:
        """Create ECS service (Fargate or EC2)"""
        
        # Load security groups
        security_groups = self._load_security_groups()
        
        # Load subnets
        subnets = self._load_subnets()
        
        # Create service based on launch type
        if self.ecs_config.launch_type == "EC2":
            self.service = ecs.Ec2Service(
                self,
                "Service",
                service_name=service_name,
                cluster=self.cluster,
                task_definition=self.task_definition,
                desired_count=self.ecs_config.desired_count,
                enable_execute_command=self.ecs_config.enable_execute_command,
                health_check_grace_period=cdk.Duration.seconds(
                    self.ecs_config.health_check_grace_period
                ) if self.ecs_config.target_group_arns else None,
                circuit_breaker=ecs.DeploymentCircuitBreaker(
                    enable=self.ecs_config.deployment_circuit_breaker.get("enable", True),
                    rollback=self.ecs_config.deployment_circuit_breaker.get("rollback", True)
                ) if self.ecs_config.deployment_circuit_breaker else None,
                placement_strategies=self._get_placement_strategies(),
                placement_constraints=self._get_placement_constraints(),
                max_healthy_percent=self.ecs_config.deployment_configuration.get("maximum_percent"),
                min_healthy_percent=self.ecs_config.deployment_configuration.get("minimum_healthy_percent")
            )
        else:
            # Fargate service
            self.service = ecs.FargateService(
                self,
                "Service",
                service_name=service_name,
                cluster=self.cluster,
                task_definition=self.task_definition,
                desired_count=self.ecs_config.desired_count,
                security_groups=security_groups,
                vpc_subnets=ec2.SubnetSelection(subnets=subnets) if subnets else None,
                assign_public_ip=self.ecs_config.assign_public_ip,
                enable_execute_command=self.ecs_config.enable_execute_command,
                health_check_grace_period=cdk.Duration.seconds(
                    self.ecs_config.health_check_grace_period
                ) if self.ecs_config.target_group_arns else None,
                circuit_breaker=ecs.DeploymentCircuitBreaker(
                    enable=self.ecs_config.deployment_circuit_breaker.get("enable", True),
                    rollback=self.ecs_config.deployment_circuit_breaker.get("rollback", True)
                ) if self.ecs_config.deployment_circuit_breaker else None,
            )
        
        # Attach to load balancer target groups
        self._attach_to_load_balancer()
        
        # Apply tags
        for key, value in self.ecs_config.tags.items():
            cdk.Tags.of(self.service).add(key, value)
    
    def _get_placement_strategies(self) -> List[ecs.PlacementStrategy]:
        """Get placement strategies for EC2 launch type"""
        strategies = []
        placement_config = self.ecs_config._config.get("placement_strategies", [])
        
        for strategy in placement_config:
            strategy_type = strategy.get("type", "spread")
            field = strategy.get("field", "instanceId")
            
            if strategy_type == "spread":
                strategies.append(ecs.PlacementStrategy.spread_across(field))
            elif strategy_type == "binpack":
                strategies.append(ecs.PlacementStrategy.packed_by(field))
            elif strategy_type == "random":
                strategies.append(ecs.PlacementStrategy.randomly())
        
        # Default strategy if none specified
        if not strategies:
            strategies = [
                ecs.PlacementStrategy.spread_across_instances(),
                ecs.PlacementStrategy.spread_across("attribute:ecs.availability-zone"),
            ]
        
        return strategies
    
    def _get_placement_constraints(self) -> List[ecs.PlacementConstraint]:
        """Get placement constraints for EC2 launch type"""
        constraints = []
        constraint_config = self.ecs_config._config.get("placement_constraints", [])
        
        for constraint in constraint_config:
            constraint_type = constraint.get("type")
            expression = constraint.get("expression", "")
            
            if constraint_type == "distinctInstance":
                constraints.append(ecs.PlacementConstraint.distinct_instances())
            elif constraint_type == "memberOf" and expression:
                constraints.append(ecs.PlacementConstraint.member_of(expression))
        
        return constraints

    def _load_security_groups(self) -> List[ec2.ISecurityGroup]:
        """Load security groups from IDs"""
        security_groups = []
        
        for sg_id in self.ecs_config.security_group_ids:
            sg = ec2.SecurityGroup.from_security_group_id(
                self,
                f"SG-{sg_id[:8]}",
                security_group_id=sg_id,
            )
            security_groups.append(sg)
        
        return security_groups

    def _load_subnets(self) -> Optional[List[ec2.ISubnet]]:
        """Load subnets by subnet group name"""
        subnet_group_name = self.ecs_config.subnet_group_name
        
        if not subnet_group_name:
            return None
        
        # This would need to be implemented based on your subnet naming convention
        # For now, returning None to use default VPC subnets
        return None

    def _attach_to_load_balancer(self) -> None:
        """Attach service to load balancer target groups"""
        target_group_arns = self.ecs_config.target_group_arns
        
        if target_group_arns:
            tmp = []
            for tg_arn in target_group_arns:
                import hashlib
                unique_id = hashlib.md5(tg_arn.encode()).hexdigest()
                tmp.append(self.resolve_ssm_value(self, tg_arn, unique_id))
            target_group_arns = tmp
        
        if not target_group_arns:
            # Try to load from SSM if configured
            target_group_arns = self._load_target_groups_from_ssm()
        
        for tg_arn in target_group_arns:
            target_group = elbv2.ApplicationTargetGroup.from_target_group_attributes(
                self,
                f"TG-{tg_arn.split('/')[-1][:8]}",
                target_group_arn=tg_arn,
            )
            
            self.service.attach_to_application_target_group(target_group)

    def _load_target_groups_from_ssm(self) -> List[str]:
        """Load target group ARNs from SSM parameters"""
        target_group_arns = []
        
        # Load SSM imports and look for target group ARNs
        ssm_imports = self.ecs_config.ssm_imports
        
        for param_key, param_name in ssm_imports.items():
            if 'target_group' in param_key.lower() or 'tg' in param_key.lower():
                try:
                    param_value = self.get_ssm_imported_value(param_name)
                    if param_value and param_value.startswith('arn:'):
                        target_group_arns.append(param_value)
                except Exception as e:
                    logger.warning(f"Could not load target group from SSM {param_name}: {e}")
        
        return target_group_arns

    def _setup_auto_scaling(self) -> None:
        """Configure auto-scaling for the ECS service"""
        
        scalable_target = self.service.auto_scale_task_count(
            min_capacity=self.ecs_config.min_capacity,
            max_capacity=self.ecs_config.max_capacity,
        )
        
        # CPU-based scaling
        scalable_target.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=self.ecs_config.auto_scaling_target_cpu,
            scale_in_cooldown=cdk.Duration.seconds(60),
            scale_out_cooldown=cdk.Duration.seconds(60),
        )
        
        # Memory-based scaling
        scalable_target.scale_on_memory_utilization(
            "MemoryScaling",
            target_utilization_percent=self.ecs_config.auto_scaling_target_memory,
            scale_in_cooldown=cdk.Duration.seconds(60),
            scale_out_cooldown=cdk.Duration.seconds(60),
        )

    

    def _add_outputs(self, service_name: str) -> None:
        """Add CloudFormation outputs"""
        return
        
        

    def _export_to_ssm(self, service_name: str) -> None:
        """Export resource ARNs and names to SSM Parameter Store"""
        ssm_exports = self.ecs_config.ssm_exports
        
        if not ssm_exports:
            return
        
        # Service name
        if "service_name" in ssm_exports:
            self.export_ssm_parameter(
                scope=self,
                id="ServiceNameParam",
                value=self.service.service_name,
                parameter_name=ssm_exports["service_name"],
                description=f"ECS Service Name: {service_name}",
            )
        
        # Service ARN
        if "service_arn" in ssm_exports:
            self.export_ssm_parameter(
                scope=self,
                id="ServiceArnParam",
                value=self.service.service_arn,
                parameter_name=ssm_exports["service_arn"],
                description=f"ECS Service ARN: {service_name}",
            )
        
        
        # Task definition ARN
        if "task_definition_arn" in ssm_exports:
            self.export_ssm_parameter(
                scope=self,
                id="TaskDefinitionArnParam",
                value=self.task_definition.task_definition_arn,
                parameter_name=ssm_exports["task_definition_arn"],
                description=f"ECS Task Definition ARN for {service_name}",
            )

        # roles
        if "service_role_arn" in ssm_exports:
            self.export_ssm_parameter(
                scope=self,
                id="ServiceRoleArnParam",
                value=self.service.role.role_arn,
                parameter_name=ssm_exports["service_role_arn"],
                description=f"ECS Service Role ARN for {service_name}",
            )

        # task roles
        if "task_role_arn" in ssm_exports:
            self.export_ssm_parameter(
                scope=self,
                id="TaskRoleArnParam",
                value=self.task_definition.task_role.role_arn,
                parameter_name=ssm_exports["task_role_arn"],
                description=f"ECS Task Role ARN for {service_name}",
            )