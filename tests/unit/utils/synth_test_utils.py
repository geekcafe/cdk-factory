"""
Utilities for synthesis-based testing of CDK stacks
"""
from typing import Dict, List, Any, Optional, Callable, Union
from aws_cdk import App
import json


def synth_stack(stack):
    """
    Synthesize a stack to CloudFormation template
    
    Args:
        stack: The CDK stack to synthesize
        
    Returns:
        dict: The CloudFormation template
    """
    return stack.node.root.synth().get_stack_by_name(stack.stack_name).template


def get_resources_by_type(template: Dict[str, Any], resource_type: str) -> List[Dict[str, Any]]:
    """
    Get all resources of a specific type from a CloudFormation template
    
    Args:
        template: The CloudFormation template
        resource_type: The resource type to filter by (e.g., 'AWS::EC2::VPC')
        
    Returns:
        list: List of resources matching the specified type
    """
    resources = template.get("Resources", {})
    return [
        {"logical_id": logical_id, "resource": resource}
        for logical_id, resource in resources.items()
        if resource.get("Type") == resource_type
    ]


def get_resource_by_logical_id(template: Dict[str, Any], logical_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a resource by its logical ID from a CloudFormation template
    
    Args:
        template: The CloudFormation template
        logical_id: The logical ID of the resource
        
    Returns:
        dict: The resource if found, None otherwise
    """
    resources = template.get("Resources", {})
    return resources.get(logical_id)


def get_resource_property(resource: Dict[str, Any], property_path: str) -> Any:
    """
    Get a property from a resource using a dot-notation path
    
    Args:
        resource: The resource dictionary
        property_path: The path to the property (e.g., 'Properties.VpcId')
        
    Returns:
        The property value if found, None otherwise
    """
    if not resource:
        return None
        
    parts = property_path.split(".")
    current = resource
    
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
            
    return current


def find_tag_value(tags: List[Dict[str, str]], key: str) -> Optional[str]:
    """
    Find a tag value by key in a list of tags
    
    Args:
        tags: List of tag dictionaries with 'Key' and 'Value' properties
        key: The tag key to search for
        
    Returns:
        str: The tag value if found, None otherwise
    """
    for tag in tags:
        if tag.get("Key") == key:
            return tag.get("Value")
    return None


def get_outputs(template: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get all outputs from a CloudFormation template
    
    Args:
        template: The CloudFormation template
        
    Returns:
        dict: The outputs dictionary
    """
    return template.get("Outputs", {})


def get_output_value(template: Dict[str, Any], output_name: str) -> Optional[str]:
    """
    Get an output value by name from a CloudFormation template
    
    Args:
        template: The CloudFormation template
        output_name: The name of the output
        
    Returns:
        str: The output value if found, None otherwise
    """
    outputs = get_outputs(template)
    output = outputs.get(output_name, {})
    return output.get("Value")


def assert_resource_count(template: Dict[str, Any], resource_type: str, expected_count: int) -> bool:
    """
    Assert that a template has the expected number of resources of a specific type
    
    Args:
        template: The CloudFormation template
        resource_type: The resource type to count
        expected_count: The expected number of resources
        
    Returns:
        bool: True if the count matches, False otherwise
    """
    resources = get_resources_by_type(template, resource_type)
    return len(resources) == expected_count


def assert_has_resource_with_properties(
    template: Dict[str, Any], 
    resource_type: str, 
    properties: Dict[str, Any]
) -> bool:
    """
    Assert that a template has a resource of a specific type with the specified properties
    
    Args:
        template: The CloudFormation template
        resource_type: The resource type to check
        properties: Dictionary of property paths and expected values
        
    Returns:
        bool: True if a matching resource is found, False otherwise
    """
    resources = get_resources_by_type(template, resource_type)
    
    for resource_info in resources:
        resource = resource_info["resource"]
        matches_all = True
        
        for prop_path, expected_value in properties.items():
            actual_value = get_resource_property(resource, prop_path)
            
            if actual_value != expected_value:
                matches_all = False
                break
                
        if matches_all:
            return True
            
    return False


def assert_has_tag(template: Dict[str, Any], resource_type: str, tag_key: str, tag_value: Optional[str] = None) -> bool:
    """
    Assert that a template has a resource with a specific tag
    
    Args:
        template: The CloudFormation template
        resource_type: The resource type to check
        tag_key: The tag key to check for
        tag_value: The expected tag value (optional)
        
    Returns:
        bool: True if a matching resource is found, False otherwise
    """
    resources = get_resources_by_type(template, resource_type)
    
    for resource_info in resources:
        resource = resource_info["resource"]
        tags = get_resource_property(resource, "Properties.Tags")
        
        if not tags:
            continue
            
        found_value = find_tag_value(tags, tag_key)
        
        if found_value is not None and (tag_value is None or found_value == tag_value):
            return True
            
    return False


def print_template_summary(template: Dict[str, Any]) -> None:
    """
    Print a summary of a CloudFormation template
    
    Args:
        template: The CloudFormation template
    """
    resources = template.get("Resources", {})
    resource_types = {}
    
    for resource_id, resource in resources.items():
        resource_type = resource.get("Type", "Unknown")
        if resource_type not in resource_types:
            resource_types[resource_type] = []
        resource_types[resource_type].append(resource_id)
    
    print("Template Summary:")
    print(f"Total Resources: {len(resources)}")
    
    for resource_type, resource_ids in sorted(resource_types.items()):
        print(f"  {resource_type}: {len(resource_ids)}")
        
    outputs = template.get("Outputs", {})
    print(f"Total Outputs: {len(outputs)}")
