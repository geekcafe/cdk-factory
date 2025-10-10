"""Unit tests for JsonLoadingUtility"""

import json
import os
import tempfile
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


class TestJsonLoadingUtilityInheritance(unittest.TestCase):
    """Test cases for __inherits__ functionality"""

    def setUp(self):
        """Set up temporary directory and test files"""
        self.test_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        """Clean up temporary files"""
        import shutil
        shutil.rmtree(self.test_dir)
    
    def create_test_file(self, filename, content):
        """Helper to create a test JSON file"""
        filepath = os.path.join(self.test_dir, filename)
        with open(filepath, 'w') as f:
            json.dump(content, f)
        return filepath
    
    def test_single_inherits_string(self):
        """Test __inherits__ with a single string path (backward compatibility)"""
        # Create base file
        base_content = {"key1": "value1", "key2": "value2"}
        self.create_test_file("base.json", base_content)
        
        # Create main file that inherits
        main_content = {
            "__inherits__": "./base.json",
            "key3": "value3"
        }
        main_file = self.create_test_file("main.json", main_content)
        
        # Load and resolve
        loader = JsonLoadingUtility(main_file)
        result = loader.load()
        
        # Should have all keys
        self.assertEqual(result["key1"], "value1")
        self.assertEqual(result["key2"], "value2")
        self.assertEqual(result["key3"], "value3")
    
    def test_multiple_inherits_array_dict(self):
        """Test __inherits__ with array of paths for dict types"""
        # Create first base file
        base1_content = {"key1": "value1", "key2": "value2"}
        self.create_test_file("base1.json", base1_content)
        
        # Create second base file
        base2_content = {"key3": "value3", "key4": "value4"}
        self.create_test_file("base2.json", base2_content)
        
        # Create main file that inherits from both
        main_content = {
            "__inherits__": ["./base1.json", "./base2.json"],
            "key5": "value5"
        }
        main_file = self.create_test_file("main.json", main_content)
        
        # Load and resolve
        loader = JsonLoadingUtility(main_file)
        result = loader.load()
        
        # Should have all keys merged
        self.assertEqual(result["key1"], "value1")
        self.assertEqual(result["key2"], "value2")
        self.assertEqual(result["key3"], "value3")
        self.assertEqual(result["key4"], "value4")
        self.assertEqual(result["key5"], "value5")
    
    def test_multiple_inherits_array_list(self):
        """Test __inherits__ with array of paths for list types"""
        # Create first base file (list)
        base1_content = [
            {"name": "item1", "value": "val1"},
            {"name": "item2", "value": "val2"}
        ]
        self.create_test_file("list1.json", base1_content)
        
        # Create second base file (list)
        base2_content = [
            {"name": "item3", "value": "val3"},
            {"name": "item4", "value": "val4"}
        ]
        self.create_test_file("list2.json", base2_content)
        
        # Create main file that inherits from both
        main_content = {
            "__inherits__": ["./list1.json", "./list2.json"]
        }
        main_file = self.create_test_file("main.json", main_content)
        
        # Load and resolve
        loader = JsonLoadingUtility(main_file)
        result = loader.load()
        
        # Should have all items concatenated
        self.assertEqual(len(result), 4)
        self.assertEqual(result[0]["name"], "item1")
        self.assertEqual(result[1]["name"], "item2")
        self.assertEqual(result[2]["name"], "item3")
        self.assertEqual(result[3]["name"], "item4")
    
    def test_multiple_inherits_override(self):
        """Test that later files override earlier files"""
        # Create first base file
        base1_content = {"key1": "original", "key2": "value2"}
        self.create_test_file("base1.json", base1_content)
        
        # Create second base file that overrides key1
        base2_content = {"key1": "overridden", "key3": "value3"}
        self.create_test_file("base2.json", base2_content)
        
        # Create main file that inherits from both
        main_content = {
            "__inherits__": ["./base1.json", "./base2.json"]
        }
        main_file = self.create_test_file("main.json", main_content)
        
        # Load and resolve
        loader = JsonLoadingUtility(main_file)
        result = loader.load()
        
        # key1 should be overridden by base2
        self.assertEqual(result["key1"], "overridden")
        self.assertEqual(result["key2"], "value2")
        self.assertEqual(result["key3"], "value3")
    
    def test_multiple_inherits_with_override_in_main(self):
        """Test that main file properties override inherited properties"""
        # Create first base file
        base1_content = {"key1": "value1", "key2": "value2"}
        self.create_test_file("base1.json", base1_content)
        
        # Create second base file
        base2_content = {"key3": "value3"}
        self.create_test_file("base2.json", base2_content)
        
        # Create main file that inherits and overrides
        main_content = {
            "__inherits__": ["./base1.json", "./base2.json"],
            "key1": "main_override",
            "key4": "value4"
        }
        main_file = self.create_test_file("main.json", main_content)
        
        # Load and resolve
        loader = JsonLoadingUtility(main_file)
        result = loader.load()
        
        # Main file should override inherited values
        self.assertEqual(result["key1"], "main_override")
        self.assertEqual(result["key2"], "value2")
        self.assertEqual(result["key3"], "value3")
        self.assertEqual(result["key4"], "value4")
    
    def test_nested_inherits_in_section(self):
        """Test __inherits__ in a nested section"""
        # Create environment vars file
        env_vars = [
            {"name": "ENV1", "value": "val1"},
            {"name": "ENV2", "value": "val2"}
        ]
        self.create_test_file("env-vars.json", env_vars)
        
        # Create API keys file
        api_keys = [
            {"name": "API_KEY", "value": "secret123"},
            {"name": "AUTH_TYPE", "value": "api_key"}
        ]
        self.create_test_file("api-keys.json", api_keys)
        
        # Create main config with nested inherits
        main_content = {
            "name": "my-lambda",
            "environment_variables": {
                "__inherits__": ["./env-vars.json", "./api-keys.json"]
            }
        }
        main_file = self.create_test_file("main.json", main_content)
        
        # Load and resolve
        loader = JsonLoadingUtility(main_file)
        result = loader.load()
        
        # Should have merged environment variables
        self.assertEqual(result["name"], "my-lambda")
        self.assertEqual(len(result["environment_variables"]), 4)
        self.assertEqual(result["environment_variables"][0]["name"], "ENV1")
        self.assertEqual(result["environment_variables"][1]["name"], "ENV2")
        self.assertEqual(result["environment_variables"][2]["name"], "API_KEY")
        self.assertEqual(result["environment_variables"][3]["name"], "AUTH_TYPE")
    
    def test_invalid_inherits_type(self):
        """Test that invalid __inherits__ type raises error"""
        # Create main file with invalid inherits (number)
        main_content = {
            "__inherits__": 123
        }
        main_file = self.create_test_file("main.json", main_content)
        
        # Should raise ValueError
        loader = JsonLoadingUtility(main_file)
        with self.assertRaises(ValueError) as context:
            loader.load()
        
        self.assertIn("must be a string or list", str(context.exception))


class TestJsonLoadingUtilityImports(unittest.TestCase):
    """Test cases for __imports__ functionality (v0.8.2+)"""

    def setUp(self):
        """Set up temporary directory and test files"""
        self.test_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        """Clean up temporary files"""
        import shutil
        shutil.rmtree(self.test_dir)
    
    def create_test_file(self, filename, content):
        """Helper to create a test JSON file"""
        filepath = os.path.join(self.test_dir, filename)
        with open(filepath, 'w') as f:
            json.dump(content, f)
        return filepath
    
    def test_single_imports_string(self):
        """Test __imports__ with a single string path"""
        # Create base file
        base_content = {"api_version": "v1", "timeout": 30}
        self.create_test_file("base.json", base_content)
        
        # Create main file that imports
        main_content = {
            "__imports__": "./base.json",
            "name": "my-lambda"
        }
        main_file = self.create_test_file("main.json", main_content)
        
        # Load and resolve
        loader = JsonLoadingUtility(main_file)
        result = loader.load()
        
        # Should have all keys
        self.assertEqual(result["api_version"], "v1")
        self.assertEqual(result["timeout"], 30)
        self.assertEqual(result["name"], "my-lambda")
    
    def test_multiple_imports_array(self):
        """Test __imports__ with array of paths"""
        # Create first base file
        base1_content = {"memory": 128, "timeout": 30}
        self.create_test_file("base1.json", base1_content)
        
        # Create second base file
        base2_content = {"runtime": "python3.13", "layers": ["layer1"]}
        self.create_test_file("base2.json", base2_content)
        
        # Create main file that imports from both
        main_content = {
            "__imports__": ["./base1.json", "./base2.json"],
            "handler": "index.handler"
        }
        main_file = self.create_test_file("main.json", main_content)
        
        # Load and resolve
        loader = JsonLoadingUtility(main_file)
        result = loader.load()
        
        # Should have all keys merged
        self.assertEqual(result["memory"], 128)
        self.assertEqual(result["timeout"], 30)
        self.assertEqual(result["runtime"], "python3.13")
        self.assertEqual(result["layers"], ["layer1"])
        self.assertEqual(result["handler"], "index.handler")
    
    def test_imports_with_override(self):
        """Test __imports__ with property override"""
        # Create base file
        base_content = {"memory": 128, "timeout": 30, "environment": "dev"}
        self.create_test_file("base.json", base_content)
        
        # Create main file that imports and overrides
        main_content = {
            "__imports__": "./base.json",
            "timeout": 60,  # Override
            "handler": "index.handler"  # New property
        }
        main_file = self.create_test_file("main.json", main_content)
        
        # Load and resolve
        loader = JsonLoadingUtility(main_file)
        result = loader.load()
        
        # Should have overridden timeout
        self.assertEqual(result["memory"], 128)
        self.assertEqual(result["timeout"], 60)  # Overridden
        self.assertEqual(result["environment"], "dev")
        self.assertEqual(result["handler"], "index.handler")
    
    def test_imports_nested_section(self):
        """Test __imports__ in nested configuration sections"""
        # Create env vars file
        env_vars = [
            {"name": "DB_HOST", "value": "localhost"},
            {"name": "DB_PORT", "value": "5432"}
        ]
        self.create_test_file("env-vars.json", env_vars)
        
        # Create API keys file
        api_keys = [
            {"name": "API_KEY", "value": "secret"}
        ]
        self.create_test_file("api-keys.json", api_keys)
        
        # Create main file with nested imports
        main_content = {
            "name": "my-lambda",
            "runtime": "python3.13",
            "environment_variables": {
                "__imports__": ["./env-vars.json", "./api-keys.json"]
            }
        }
        main_file = self.create_test_file("main.json", main_content)
        
        # Load and resolve
        loader = JsonLoadingUtility(main_file)
        result = loader.load()
        
        # Should have merged environment variables
        self.assertEqual(result["name"], "my-lambda")
        self.assertEqual(len(result["environment_variables"]), 3)
        self.assertEqual(result["environment_variables"][0]["name"], "DB_HOST")
        self.assertEqual(result["environment_variables"][2]["name"], "API_KEY")
    
    def test_invalid_imports_type(self):
        """Test that invalid __imports__ type raises error"""
        # Create main file with invalid imports (number)
        main_content = {
            "__imports__": 456
        }
        main_file = self.create_test_file("main.json", main_content)
        
        # Should raise ValueError
        loader = JsonLoadingUtility(main_file)
        with self.assertRaises(ValueError) as context:
            loader.load()
        
        self.assertIn("must be a string or list", str(context.exception))
        self.assertIn("__imports__", str(context.exception))
    
    def test_imports_takes_precedence_over_inherits(self):
        """Test that __imports__ takes precedence when both are present"""
        # Create import file
        import_content = {"source": "imports", "value": 1}
        self.create_test_file("import.json", import_content)
        
        # Create inherits file
        inherit_content = {"source": "inherits", "value": 2}
        self.create_test_file("inherit.json", inherit_content)
        
        # Create main file with both keywords (edge case)
        main_content = {
            "__imports__": "./import.json",
            "__inherits__": "./inherit.json"
        }
        main_file = self.create_test_file("main.json", main_content)
        
        # Load and resolve
        loader = JsonLoadingUtility(main_file)
        result = loader.load()
        
        # Should use __imports__ (takes precedence)
        self.assertEqual(result["source"], "imports")
        self.assertEqual(result["value"], 1)
    
    def test_backward_compatibility_inherits_still_works(self):
        """Test that __inherits__ still works for backward compatibility"""
        # Create base file
        base_content = {"legacy": True, "version": "0.8.1"}
        self.create_test_file("base.json", base_content)
        
        # Create main file using legacy __inherits__
        main_content = {
            "__inherits__": "./base.json",
            "new_feature": False
        }
        main_file = self.create_test_file("main.json", main_content)
        
        # Load and resolve
        loader = JsonLoadingUtility(main_file)
        result = loader.load()
        
        # Should work exactly as before
        self.assertEqual(result["legacy"], True)
        self.assertEqual(result["version"], "0.8.1")
        self.assertEqual(result["new_feature"], False)


if __name__ == "__main__":
    unittest.main()
