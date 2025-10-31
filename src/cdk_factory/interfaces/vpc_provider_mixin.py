"""
VPC Provider Mixin - Reusable VPC resolution functionality
Maintainers: Eric Wilson
MIT License. See Project Root for license information.
"""

from typing import Optional, List, Any
from aws_lambda_powertools import Logger
from aws_cdk import aws_ec2 as ec2
from constructs import Construct

logger = Logger(__name__)


class VPCProviderMixin:
    """
    Mixin class that provides reusable VPC resolution functionality for stacks.
    
    This mixin eliminates code duplication across stacks that need to resolve
    VPC references, providing a standardized way to handle:
    - SSM imported VPC parameters (works with enhanced SsmParameterMixin)
    - Configuration-based VPC resolution
    - Workload-level VPC fallback
    - Error handling and validation
    
    Note: This mixin does NOT handle SSM imports directly - it expects
    the SSM values to be available via the enhanced SsmParameterMixin.
    """

    def _initialize_vpc_cache(self) -> None:
        """Initialize the VPC cache attribute"""
        if not hasattr(self, '_vpc'):
            self._vpc: Optional[ec2.IVpc] = None

    def resolve_vpc(
        self,
        config: Any,
        deployment: Any,
        workload: Any,
        availability_zones: Optional[List[str]] = None
    ) -> ec2.IVpc:
        """
        Resolve VPC from multiple sources with standardized priority order.
        
        Priority order:
        1. SSM imported VPC ID (from enhanced SsmParameterMixin)
        2. Config-level VPC ID
        3. Workload-level VPC ID
        4. Raise error if none found
        
        Args:
            config: The stack configuration
            deployment: The deployment configuration
            workload: The workload configuration
            availability_zones: Optional AZ list for VPC attributes
            
        Returns:
            Resolved VPC reference
            
        Raises:
            ValueError: If no VPC configuration is found
        """
        if self._vpc:
            return self._vpc

        # Default availability zones if not provided
        if not availability_zones:
            availability_zones = ["us-east-1a", "us-east-1b"]

        # Check SSM imported values first (tokens from SSM parameters)
        # This works with the enhanced SsmParameterMixin
        if hasattr(self, '_ssm_imported_values') and "vpc_id" in self._ssm_imported_values:
            vpc_id = self._ssm_imported_values["vpc_id"]
            
            # Get subnet IDs first to determine AZ count
            subnet_ids = []
            if hasattr(self, '_ssm_imported_values') and "subnet_ids" in self._ssm_imported_values:
                imported_subnets = self._ssm_imported_values["subnet_ids"]
                if isinstance(imported_subnets, str):
                    subnet_ids = [s.strip() for s in imported_subnets.split(",") if s.strip()]
                elif isinstance(imported_subnets, list):
                    subnet_ids = imported_subnets
            
            # Adjust availability zones to match subnet count
            if subnet_ids and availability_zones:
                availability_zones = [f"us-east-1{chr(97+i)}" for i in range(len(subnet_ids))]
            
            return self._create_vpc_from_ssm(vpc_id, availability_zones)
        
        # Check config-level VPC ID
        if hasattr(config, 'vpc_id') and config.vpc_id:
            return ec2.Vpc.from_lookup(self, f"{self.stack_name}-VPC", vpc_id=config.vpc_id)
        
        # Check workload-level VPC ID
        if hasattr(workload, 'vpc_id') and workload.vpc_id:
            return ec2.Vpc.from_lookup(self, f"{self.stack_name}-VPC", vpc_id=workload.vpc_id)
        
        # No VPC found - raise descriptive error
        raise self._create_vpc_not_found_error(config, workload)

    def _create_vpc_from_ssm(
        self, 
        vpc_id: str, 
        availability_zones: List[str]
    ) -> ec2.IVpc:
        """
        Create VPC reference from SSM imported VPC ID.
        
        Args:
            vpc_id: The VPC ID from SSM
            availability_zones: List of availability zones
            
        Returns:
            VPC reference created from attributes
        """
        # Build VPC attributes
        vpc_attrs = {
            "vpc_id": vpc_id,
            "availability_zones": availability_zones,
        }
        
        # If we have subnet_ids from SSM, use the actual subnet IDs
        if hasattr(self, '_ssm_imported_values') and "subnet_ids" in self._ssm_imported_values:
            imported_subnets = self._ssm_imported_values["subnet_ids"]
            if isinstance(imported_subnets, str):
                # Split comma-separated subnet IDs
                subnet_ids = [s.strip() for s in imported_subnets.split(",") if s.strip()]
            elif isinstance(imported_subnets, list):
                subnet_ids = imported_subnets
            else:
                subnet_ids = []
            
            # Use the actual subnet IDs from SSM
            if subnet_ids:
                vpc_attrs["public_subnet_ids"] = subnet_ids
            else:
                # Fallback to dummy subnets if no valid subnet IDs
                vpc_attrs["public_subnet_ids"] = ["subnet-dummy1", "subnet-dummy2"]
        
        # Use from_vpc_attributes() for SSM tokens with unique construct name
        self._vpc = ec2.Vpc.from_vpc_attributes(self, f"{self.stack_name}-VPC", **vpc_attrs)
        return self._vpc

    def _create_vpc_not_found_error(self, config: Any, workload: Any) -> ValueError:
        """
        Create a descriptive error message for missing VPC configuration.
        
        Args:
            config: The stack configuration
            workload: The workload configuration
            
        Returns:
            ValueError with descriptive message
        """
        config_name = getattr(config, 'name', 'unknown')
        workload_name = getattr(workload, 'name', 'unknown')
        
        return ValueError(
            f"VPC is not defined in the configuration for {config_name}. "
            f"You can provide it at the following locations:\n"
            f"  1. As an SSM import: config.ssm_imports.vpc_id\n"
            f"  2. At the config level: config.vpc_id\n"
            f"  3. At the workload level: workload.vpc_id\n"
            f"Current workload: {workload_name}"
        )

    def get_vpc_property(self, config: Any, deployment: Any, workload: Any) -> ec2.IVpc:
        """
        Standard VPC property implementation that can be used by stacks.
        
        Args:
            config: The stack configuration
            deployment: The deployment configuration
            workload: The workload configuration
            
        Returns:
            Resolved VPC reference
        """
        return self.resolve_vpc(config, deployment, workload)
