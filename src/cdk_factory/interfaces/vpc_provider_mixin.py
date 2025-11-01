"""
VPC Provider Mixin - Reusable VPC resolution functionality
Maintainers: Eric Wilson
MIT License. See Project Root for license information.
"""

from typing import Optional, List, Any
from aws_lambda_powertools import Logger
from aws_cdk import aws_ec2 as ec2, aws_ssm as ssm
from constructs import Construct

logger = Logger(__name__)


class VPCProviderMixin:
    """
    Mixin class that provides reusable VPC resolution functionality for stacks.
    
    This mixin eliminates code duplication across stacks that need to resolve
    VPC references, providing a standardized way to handle:
    - SSM imported VPC parameters (works with enhanced StandardizedSsmMixin)
    - Configuration-based VPC resolution
    - Workload-level VPC fallback
    - Error handling and validation
    
    Note: This mixin does NOT handle SSM imports directly - it expects
    the SSM values to be available via the enhanced StandardizedSsmMixin.
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
        1. SSM imported VPC ID (from config.ssm.imports)
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

        # Default availability zones if not provided - use region-appropriate defaults
        if not availability_zones:
            region = getattr(deployment, 'region', 'us-east-1')
            availability_zones = self._get_default_azs_for_region(region)

        # Check SSM imports directly from config (source of truth)
        ssm_config = getattr(config, 'ssm', {})
        ssm_imports = ssm_config.get('imports', {})
        
        if ssm_imports and "vpc_id" in ssm_imports:
            vpc_id = ssm_imports["vpc_id"]
            
            # Get subnet IDs first to determine AZ count
            subnet_ids = []
            if "subnet_ids" in ssm_imports:
                imported_subnets = ssm_imports["subnet_ids"]
                if isinstance(imported_subnets, str):
                    subnet_ids = [s.strip() for s in imported_subnets.split(",") if s.strip()]
                elif isinstance(imported_subnets, list):
                    subnet_ids = imported_subnets
            
            # Adjust availability zones to match subnet count
            if subnet_ids and availability_zones:
                region = getattr(deployment, 'region', 'us-east-1')
                region_code = region.split('-')[0] + '-' + region.split('-')[1]
                availability_zones = [f"{region_code}{chr(97+i)}" for i in range(len(subnet_ids))]
            
            return self._create_vpc_from_ssm(vpc_id, availability_zones, subnet_ids if subnet_ids else None)
        
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
        availability_zones: List[str],
        subnet_ids: Optional[List[str]] = None
    ) -> ec2.IVpc:
        """
        Create VPC reference from SSM imported VPC ID.
        
        Args:
            vpc_id: The VPC ID from SSM (can be SSM path or actual VPC ID)
            availability_zones: List of availability zones
            subnet_ids: Optional list of subnet IDs from SSM
            
        Returns:
            VPC reference created from attributes
        """
        # Check if vpc_id is an SSM path (starts with /) or actual VPC ID
        if vpc_id.startswith('/'):
            # Create CDK token for VPC ID from SSM parameter
            vpc_id_token = ssm.StringParameter.from_string_parameter_name(
                self, f"{self.stack_name}-VPC-ID-Token", vpc_id
            ).string_value
        else:
            # Use the VPC ID directly (for testing or direct configuration)
            vpc_id_token = vpc_id
        
        # Build VPC attributes
        vpc_attrs = {
            "vpc_id": vpc_id_token,
            "availability_zones": availability_zones,
        }
        
        # If we have subnet_ids from SSM, add them to the attributes
        if subnet_ids:
            # Use the actual subnet IDs from SSM
            vpc_attrs["public_subnet_ids"] = subnet_ids
        
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

    def _get_default_azs_for_region(self, region: str) -> List[str]:
        """
        Get default availability zones for a given region.
        
        Args:
            region: AWS region name (e.g., 'us-east-1', 'us-west-2')
            
        Returns:
            List of availability zone names for the region
        """
        # Common AZ mappings for major AWS regions
        region_az_map = {
            'us-east-1': ['us-east-1a', 'us-east-1b'],
            'us-east-2': ['us-east-2a', 'us-east-2b'],
            'us-west-1': ['us-west-1a', 'us-west-1b'],
            'us-west-2': ['us-west-2a', 'us-west-2b'],
            'eu-west-1': ['eu-west-1a', 'eu-west-1b'],
            'eu-west-2': ['eu-west-2a', 'eu-west-2b'],
            'eu-central-1': ['eu-central-1a', 'eu-central-1b'],
            'ap-southeast-1': ['ap-southeast-1a', 'ap-southeast-1b'],
            'ap-southeast-2': ['ap-southeast-2a', 'ap-southeast-2b'],
            'ap-northeast-1': ['ap-northeast-1a', 'ap-northeast-1b'],
        }
        
        # Return region-specific AZs if available, otherwise fall back to us-east-1
        return region_az_map.get(region, ['us-east-1a', 'us-east-1b'])
