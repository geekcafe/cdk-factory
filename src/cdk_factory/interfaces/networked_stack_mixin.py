"""
Networked Stack Mixin - Combined SSM and VPC functionality for network-aware stacks
Maintainers: Eric Wilson
MIT License. See Project Root for license information.
"""

from typing import Any
from aws_cdk import aws_ec2 as ec2
from .standardized_ssm_mixin import StandardizedSsmMixin
from .vpc_provider_mixin import VPCProviderMixin


class NetworkedStackMixin(StandardizedSsmMixin, VPCProviderMixin):
    """
    Combined mixin for stacks that need both SSM imports and VPC resolution.
    
    This mixin provides a complete solution for network-aware stacks by combining:
    - Enhanced SSM parameter import functionality (with standardized configuration)
    - VPC resolution with multiple fallback strategies
    - Standardized initialization patterns
    
    Usage:
        class MyStack(Stack, NetworkedStackMixin):
            def __init__(self, scope, id, **kwargs):
                super().__init__(scope, id, **kwargs)
                # SSM initialization is handled automatically by StandardizedSsmMixin.__init__
                
            def _build(self, stack_config, deployment, workload):
                self.setup_ssm_integration(scope=self, config=stack_config.dictionary, resource_type="my-resource", resource_name="my-name")
                self.vpc = self.resolve_vpc(stack_config, deployment, workload)
    """
    
    def _initialize_networked_stack(self) -> None:
        """
        Initialize all networked stack functionality.
        Note: SSM initialization is handled by StandardizedSsmMixin.__init__
        """
        self._initialize_vpc_cache()
    
    def build_networked_stack(
        self, 
        config: Any, 
        deployment: Any, 
        workload: Any,
        resource_type: str = "resource"
    ) -> None:
        """
        Standard build sequence for networked stacks.
        
        Args:
            config: The stack configuration
            deployment: The deployment configuration  
            workload: The workload configuration
            resource_type: Type name for logging purposes
        """
        # Process SSM imports first (using enhanced SsmParameterMixin)
        self.process_ssm_imports(config, deployment, resource_type)
        
        # Store references for later use
        self.config = config
        self.deployment = deployment
        self.workload = workload
    
    @property
    def vpc(self) -> ec2.IVpc:
        """
        Standard VPC property that uses the combined mixin functionality.
        
        Returns:
            Resolved VPC reference
        """
        if not hasattr(self, 'config') or not hasattr(self, 'deployment') or not hasattr(self, 'workload'):
            raise AttributeError("Networked stack not properly initialized. Call build_networked_stack() first.")
        
        return self.get_vpc_property(self.config, self.deployment, self.workload)
