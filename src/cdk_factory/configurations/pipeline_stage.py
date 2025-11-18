"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

# import os
# from typing import List, Optional
from typing import List, Dict, Any

from cdk_factory.configurations.stack import StackConfig


class PipelineStageConfig:
    """A Representation of a pipeline stage"""

    def __init__(self, stage: dict, workload: dict) -> None:
        self.__dictionary: dict = stage
        self.__workload: dict = workload
        self.__stacks: List[StackConfig] = []

        self.__load_stacks()

    @property
    def workload(self) -> dict:
        """
        Returns the workload name
        """
        return self.__workload

    @property
    def workload_name(self) -> str:
        """
        Returns the workload name
        """

        value = self.workload.get("name")
        if not value:
            raise ValueError("Workload name is not defined in the configuration")

        return value

    @property
    def dictionary(self) -> dict:
        """
        Returns the dictionary of the stage
        """
        return self.__dictionary

    @property
    def name(self) -> str:
        """
        Returns the stage name
        """
        value = self.dictionary.get("name")
        if not value:
            raise ValueError("Stage name is not defined in the configuration")

        return value

    @property
    def stable_id(self) -> str:
        """
        Returns a stable construct ID for the stage based on stack names.
        This ensures CloudFormation logical IDs don't change when stage names are renamed.
        
        Uses the first stack's name if available, otherwise falls back to a sanitized stage name.
        """
        import re
        
        # Try to use the first stack name as the stable ID
        if self.stacks and len(self.stacks) > 0:
            # Get the first stack's name and sanitize it for use as construct ID
            stack_name = self.stacks[0].name
            # Remove environment/workload prefix if present for cleaner IDs
            # e.g., "prod-workload-rds" -> "rds"
            parts = stack_name.split('-')
            if len(parts) > 2:
                # Use the last meaningful part (e.g., "rds", "vpc", "ecs")
                stable_name = parts[-1]
            else:
                stable_name = stack_name
            
            # Sanitize: remove any non-alphanumeric characters except hyphens
            stable_name = re.sub(r'[^a-zA-Z0-9-]', '', stable_name)
            return stable_name
        
        # Fallback: use sanitized stage name (shouldn't happen if stage has stacks)
        sanitized = re.sub(r'[^a-zA-Z0-9-]', '', self.name)
        return sanitized

    @property
    def enabled(self) -> bool:
        """
        Returns the stage enabled status
        """
        return str(self.dictionary.get("enabled", True)).lower() == "true"

    @property
    def description(self) -> str | None:
        """
        Returns the stage description
        """
        return self.dictionary.get("description")

    @property
    def wave_name(self) -> str | None:
        """
        Returns the wave name if found
        """
        return self.dictionary.get("wave") or self.dictionary.get("wave_name")

    @property
    def module(self) -> str | None:
        """
        Returns the module name
        """
        return self.dictionary.get("module")

    @property
    def stacks(self) -> List[StackConfig]:
        """Deployment Stacks"""
        return self.__stacks

    def __load_stacks(self):
        """
        Loads the stacks for the deployment
        """
        stacks = self.__dictionary.get("stacks", [])
        self.__stacks = []
        for stack in stacks:
            if isinstance(stack, dict):
                self.__stacks.append(StackConfig(stack, self.__workload))
            if isinstance(stack, str):
                # if the stack is a string, it's the stack name
                # and we need to load the stack configuration
                # from the workload
                stack_list: List[dict] = self.__workload.get("stacks", [])
                stack_dict: dict | None = None
                for stack_item in stack_list:
                    if stack_item.get("name") == stack:
                        stack_dict = stack_item
                        break
                if stack_dict is None:
                    raise ValueError(f"Stack {stack} not found in workload")
                self.__stacks.append(StackConfig(stack_dict, self.__workload))

    @property
    def builds(self) -> List[Dict[str, Any]]:
        """
        Returns the builds configured for this stage.
        
        If the stage has a "builds" array of strings, resolve them to the
        corresponding build objects defined at workload["builds"].
        Otherwise, return an empty list.
        """
        stage_build_refs = self.dictionary.get("builds", [])
        if not stage_build_refs:
            return []

        workload_builds: List[Dict[str, Any]] = self.workload.get("builds", [])
        by_name: Dict[str, Dict[str, Any]] = {}
        for b in workload_builds:
            name = b.get("name") or b.get("id")
            if name:
                by_name[name] = b

        resolved: List[Dict[str, Any]] = []
        for ref in stage_build_refs:
            if isinstance(ref, str):
                if ref in by_name:
                    resolved.append(by_name[ref])
                else:
                    raise ValueError(f"Build '{ref}' referenced by stage '{self.name}' not found in workload.builds")
            elif isinstance(ref, dict):
                # Allow inline build definitions at the stage level as a fallback
                resolved.append(ref)

        return resolved
