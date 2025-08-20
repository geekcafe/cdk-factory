"""Unit tests for JsonLoadingUtility"""

import unittest
from src.cdk_factory.utilities.json_loading_utility import JsonLoadingUtility


class TestJsonLoadingUtility(unittest.TestCase):
    """Test cases for JsonLoadingUtility"""

    def test_recursive_replace_values_only(self):
        """Test recursive_replace with placeholders only in values"""
        data = {
            "name": "{{workload-name}}",
            "environment": "{{env}}",
            "config": {
                "vpc_id": "{{vpc-id}}",
                "subnets": ["{{subnet-1}}", "{{subnet-2}}"]
            }
        }
        
        replacements = {
            "{{workload-name}}": "myapp",
            "{{env}}": "prod",
            "{{vpc-id}}": "vpc-12345",
            "{{subnet-1}}": "subnet-abc",
            "{{subnet-2}}": "subnet-def"
        }
        
        result = JsonLoadingUtility.recursive_replace(data, replacements)
        
        self.assertEqual(result["name"], "myapp")
        self.assertEqual(result["environment"], "prod")
        self.assertEqual(result["config"]["vpc_id"], "vpc-12345")
        self.assertEqual(result["config"]["subnets"], ["subnet-abc", "subnet-def"])

    def test_recursive_replace_keys_only(self):
        """Test recursive_replace with placeholders only in keys"""
        data = {
            "{{env}}_config": "static_value",
            "{{resource_type}}": {
                "static_key": "another_static_value"
            }
        }
        
        replacements = {
            "{{env}}": "prod",
            "{{resource_type}}": "load_balancer"
        }
        
        result = JsonLoadingUtility.recursive_replace(data, replacements)
        
        self.assertIn("prod_config", result)
        self.assertIn("load_balancer", result)
        self.assertEqual(result["prod_config"], "static_value")
        self.assertEqual(result["load_balancer"]["static_key"], "another_static_value")

    def test_recursive_replace_keys_and_values(self):
        """Test recursive_replace with placeholders in both keys and values"""
        data = {
            "{{env}}_config": {
                "name": "{{workload-name}}-{{env}}",
                "{{resource_type}}": {
                    "vpc_id": "{{vpc-id}}",
                    "subnets": ["{{subnet-1}}", "{{subnet-2}}"]
                }
            },
            "static_key": "{{dynamic-value}}"
        }
        
        replacements = {
            "{{env}}": "prod",
            "{{workload-name}}": "myapp",
            "{{resource_type}}": "load_balancer",
            "{{vpc-id}}": "vpc-12345",
            "{{subnet-1}}": "subnet-abc",
            "{{subnet-2}}": "subnet-def",
            "{{dynamic-value}}": "replaced_value"
        }
        
        result = JsonLoadingUtility.recursive_replace(data, replacements)
        
        # Verify key replacements
        self.assertIn("prod_config", result)
        self.assertIn("load_balancer", result["prod_config"])
        
        # Verify value replacements
        self.assertEqual(result["prod_config"]["name"], "myapp-prod")
        self.assertEqual(result["static_key"], "replaced_value")
        self.assertEqual(result["prod_config"]["load_balancer"]["vpc_id"], "vpc-12345")
        self.assertEqual(result["prod_config"]["load_balancer"]["subnets"], ["subnet-abc", "subnet-def"])

    def test_recursive_replace_nested_structures(self):
        """Test recursive_replace with deeply nested structures"""
        data = {
            "{{level1}}": {
                "{{level2}}": {
                    "{{level3}}": "{{value}}"
                }
            }
        }
        
        replacements = {
            "{{level1}}": "first",
            "{{level2}}": "second", 
            "{{level3}}": "third",
            "{{value}}": "deep_value"
        }
        
        result = JsonLoadingUtility.recursive_replace(data, replacements)
        
        self.assertEqual(result["first"]["second"]["third"], "deep_value")

    def test_recursive_replace_list_with_dicts(self):
        """Test recursive_replace with lists containing dictionaries"""
        data = {
            "items": [
                {"{{key1}}": "{{value1}}"},
                {"{{key2}}": "{{value2}}"}
            ]
        }
        
        replacements = {
            "{{key1}}": "name",
            "{{value1}}": "item1",
            "{{key2}}": "type",
            "{{value2}}": "item2"
        }
        
        result = JsonLoadingUtility.recursive_replace(data, replacements)
        
        self.assertEqual(result["items"][0]["name"], "item1")
        self.assertEqual(result["items"][1]["type"], "item2")

    def test_recursive_replace_no_placeholders(self):
        """Test recursive_replace with no placeholders"""
        data = {
            "name": "static_name",
            "config": {
                "vpc_id": "vpc-static",
                "subnets": ["subnet-1", "subnet-2"]
            }
        }
        
        replacements = {
            "{{placeholder}}": "replacement"
        }
        
        result = JsonLoadingUtility.recursive_replace(data, replacements)
        
        # Should return identical structure
        self.assertEqual(result, data)

    def test_recursive_replace_partial_matches(self):
        """Test recursive_replace with partial placeholder matches"""
        data = {
            "{{env}}_{{type}}_config": "{{env}}-{{type}}-value"
        }
        
        replacements = {
            "{{env}}": "prod",
            "{{type}}": "web"
        }
        
        result = JsonLoadingUtility.recursive_replace(data, replacements)
        
        self.assertIn("prod_web_config", result)
        self.assertEqual(result["prod_web_config"], "prod-web-value")

    def test_recursive_replace_non_string_keys(self):
        """Test recursive_replace with non-string keys"""
        data = {
            123: "numeric_key",
            "{{string_key}}": "string_value"
        }
        
        replacements = {
            "{{string_key}}": "replaced_key"
        }
        
        result = JsonLoadingUtility.recursive_replace(data, replacements)
        
        # Numeric key should remain unchanged
        self.assertIn(123, result)
        self.assertEqual(result[123], "numeric_key")
        
        # String key should be replaced
        self.assertIn("replaced_key", result)
        self.assertEqual(result["replaced_key"], "string_value")

    def test_recursive_replace_empty_structures(self):
        """Test recursive_replace with empty structures"""
        # Empty dict
        result = JsonLoadingUtility.recursive_replace({}, {"{{key}}": "value"})
        self.assertEqual(result, {})
        
        # Empty list
        result = JsonLoadingUtility.recursive_replace([], {"{{key}}": "value"})
        self.assertEqual(result, [])
        
        # Empty string
        result = JsonLoadingUtility.recursive_replace("", {"{{key}}": "value"})
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
