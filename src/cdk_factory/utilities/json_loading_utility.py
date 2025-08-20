"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import copy
import json
import os
from typing import Any, Dict


class JsonLoadingUtility:
    """
    JSON Loading Utility
    This class is used to load a JSON file.  We have a special syntax that allows
    chaining JSON files together using __inherits__

    Examples:
     TODO - show some examples
    """

    def __init__(self, path) -> None:
        self.path = path
        self.base_path = os.path.dirname(path)
        self.nested_key = "__inherits__"

    def load(self):
        """Load and parse the JSON object for nested resources."""
        data = self.__load_json_file(self.path)
        data = self.resolve_references(data, data)
        return data

    def __load_json_file(self, path) -> Any:
        if path:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            return {}

    def get_nested_config(self, config: dict, path: str):
        """Retrieve a nested configuration section given a dot-separated path, supporting array indices."""
        keys = path.replace("]", "").split(".")
        section = config
        for key in keys:
            if "[" in key:
                key, index = key.split("[")
                section = section[key][int(index)]
            else:
                section = section[key]
        return section

    def resolve_references(self, config: dict | list, root_config: dict):
        """Resolve references in a configuration dictionary."""
        resolved_config = copy.deepcopy(config)
        return self.resolve_section(resolved_config, config, root_config)

    def resolve_section(
        self, section: dict | list, parent_section: dict | list, root_config: dict
    ):
        """Resolve references in a configuration section."""
        if isinstance(section, dict):
            if self.nested_key in section:
                nested_path = str(section.pop(self.nested_key))
                # print(f"Resolving parent path: {nested_path}")
                if nested_path.endswith(".json"):
                    nested_root_path = os.path.join(self.base_path, nested_path)
                    nested_section = self.__load_json_file(nested_root_path)
                elif os.path.isdir(os.path.join(self.base_path, nested_path)):
                    nested_section = []
                    dir_path = os.path.join(self.base_path, nested_path)
                    for filename in os.listdir(dir_path):
                        if filename.endswith(".json"):
                            file_path = os.path.join(dir_path, filename)
                            # print(f"Loading file: {file_path}")
                            file_section = self.__load_json_file(file_path)
                            nested_section.append(file_section)

                    # print("done with nested sections")
                else:
                    nested_section = self.get_nested_config(root_config, nested_path)

                nested_section_resolved = self.resolve_references(
                    nested_section, root_config
                )
                if len(section) > 0 and isinstance(nested_section_resolved, dict):
                    nested_section_resolved.update(section)
                elif len(section) > 0 and isinstance(nested_section_resolved, list):
                    raise RuntimeError("we need to resolve this section")
                    # nested_section_resolved.append(section)

                section = nested_section_resolved

            if isinstance(section, dict):
                for key, value in section.items():
                    tmp = self.resolve_section(
                        value, parent_section=parent_section, root_config=root_config
                    )
                    if isinstance(parent_section, list):
                        section[key] = tmp
                    else:
                        section[key] = tmp
            elif isinstance(section, list):
                for i, _ in enumerate(section):
                    section[i] = self.resolve_section(
                        section[i],
                        parent_section=parent_section,
                        root_config=root_config,
                    )

        elif isinstance(section, list):
            for i, _ in enumerate(section):
                section[i] = self.resolve_section(
                    section[i], parent_section=parent_section, root_config=root_config
                )

        return section

    def merge_sections(self, base: dict, new: dict):
        """Merge two configuration sections, with new section overriding base section."""
        for key, value in new.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self.merge_sections(base[key], value)
            else:
                base[key] = value
        return base

    @staticmethod
    def get_boolean_setting(config: dict, key: str, default: bool = True) -> bool:
        """Get a boolean setting from a configuration dictionary."""

        setting = str(config.get(key, default)).lower() == "true"
        if setting is None:
            setting = default

        return setting

    @staticmethod
    def save(config: dict, path: str):
        """Save a configuration dictionary to a JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

    @staticmethod
    def recursive_replace(data: dict | list | str, replacements: Dict[str, Any]):
        """
        Recursively replaces substrings in all string values and keys within a JSON-like structure.

        :param data: The input data (dict, list, or other) to process.
        :param replacements: A dictionary where keys are substrings to find and values are the replacements.
            replacements = {
                "{{workload-name}}": "geekcafe",
                "{{deployment-name}}": "dev",
                "{{awsAccount}}": "123456789012",
                "{{hostedZoneName}}": "sandbox.geekcafe.com",
                "{{placeholder}}": "DYNAMIC_VALUE"
            }
        :return: A new data structure with the replacements applied.
        """
        if isinstance(data, dict):
            result = {}
            for k, v in data.items():
                # Replace placeholders in the key if it's a string
                new_key = k
                if isinstance(k, str):
                    for find_str, replace_str in replacements.items():
                        new_key = new_key.replace(find_str, replace_str)
                
                # Recursively process the value
                new_value = JsonLoadingUtility.recursive_replace(v, replacements)
                result[new_key] = new_value
            return result
        elif isinstance(data, list):
            return [
                JsonLoadingUtility.recursive_replace(item, replacements)
                for item in data
            ]
        elif isinstance(data, str):
            for find_str, replace_str in replacements.items():
                data = data.replace(find_str, replace_str)
            return data
        else:
            # Return the data unchanged if it's not a dict, list, or string.
            return data


def main():
    json_config_path = "config.json"
    json_utility = JsonLoadingUtility(json_config_path)
    resolved_config = json_utility.load()
    print(json.dumps(resolved_config, indent=2))


# Example usage
if __name__ == "__main__":
    main()
