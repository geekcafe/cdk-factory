#!/usr/bin/env python3
"""
Migration script to update all configuration classes to use the enhanced SSM pattern.
This script will:
1. Update imports to use EnhancedBaseConfig
2. Update class inheritance
3. Update constructor calls
4. Preserve existing functionality
"""

import os
import re
from pathlib import Path
from typing import List, Tuple

# Configuration classes that need to be migrated
CONFIG_CLASSES_TO_MIGRATE = [
    "api_gateway.py",
    "auto_scaling.py",
    "cloudfront.py",
    "cognito.py",
    "dynamodb.py",
    "lambda_function.py",
    "load_balancer.py",
    "rds.py",
    "s3.py",
    "security_group.py",
]

# Resource type mappings for auto-discovery
RESOURCE_TYPE_MAPPINGS = {
    "api_gateway.py": "api_gateway",
    "auto_scaling.py": "auto_scaling",
    "cloudfront.py": "cloudfront",
    "cognito.py": "cognito",
    "dynamodb.py": "dynamodb",
    "lambda_function.py": "lambda",
    "load_balancer.py": "load_balancer",
    "rds.py": "rds",
    "s3.py": "s3",
    "security_group.py": "security_group",
}


def find_config_files(base_path: str) -> List[Path]:
    """Find all configuration files that need migration"""
    config_dir = (
        Path(base_path) / "src" / "cdk_factory" / "configurations" / "resources"
    )
    files_to_migrate = []

    for filename in CONFIG_CLASSES_TO_MIGRATE:
        file_path = config_dir / filename
        if file_path.exists():
            files_to_migrate.append(file_path)
        else:
            print(f"Warning: {filename} not found at {file_path}")

    return files_to_migrate


def backup_file(file_path: Path) -> Path:
    """Create a backup of the original file"""
    backup_path = file_path.with_suffix(f"{file_path.suffix}.backup")
    backup_path.write_text(file_path.read_text())
    return backup_path


def update_imports(content: str) -> str:
    """Update imports to use EnhancedBaseConfig"""
    # Replace BaseConfig import
    content = re.sub(
        r"from cdk_factory\.configurations\.base_config import BaseConfig",
        "from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig",
        content,
    )

    # Also handle cases where BaseConfig might be imported differently
    content = re.sub(
        r"from \.\.base_config import BaseConfig",
        "from ..enhanced_base_config import EnhancedBaseConfig",
        content,
    )

    return content


def update_class_inheritance(content: str, filename: str) -> str:
    """Update class inheritance to use EnhancedBaseConfig"""
    # Find class definitions that inherit from BaseConfig
    class_pattern = r"class\s+(\w+Config)\s*\([^)]*BaseConfig[^)]*\):"

    def replace_inheritance(match):
        class_name = match.group(1)
        return f"class {class_name}(EnhancedBaseConfig):"

    content = re.sub(class_pattern, replace_inheritance, content)

    # Handle classes that don't inherit from anything but should inherit from EnhancedBaseConfig
    standalone_config_pattern = r"class\s+(\w+Config)\s*:"

    def replace_standalone(match):
        class_name = match.group(1)
        # Only replace if it's not already inheriting from something
        if "EnhancedBaseConfig" not in match.group(0):
            return f"class {class_name}(EnhancedBaseConfig):"
        return match.group(0)

    content = re.sub(standalone_config_pattern, replace_standalone, content)

    return content


def update_constructor(content: str, filename: str) -> str:
    """Update constructor to call EnhancedBaseConfig with resource type and name"""
    resource_type = RESOURCE_TYPE_MAPPINGS.get(filename, "unknown")

    # Find __init__ methods and update them
    init_pattern = r"def __init__\(self[^)]*\) -> None:\s*\n(\s+)(.*?)(?=\n\s*@|\n\s*def|\nclass|\Z)"

    def replace_init(match):
        indent = match.group(1)
        init_body = match.group(2)

        # Check if super().__init__ is already called
        if "super().__init__" in init_body:
            # Update existing super call
            super_pattern = r"super\(\).__init__\([^)]*\)"

            def replace_super(super_match):
                # Extract config parameter from existing call
                if "config" in super_match.group(0):
                    return f'super().__init__(config or {{}}, resource_type="{resource_type}", resource_name=config.get("name", "{resource_type}") if config else "{resource_type}")'
                else:
                    return f'super().__init__({{}}, resource_type="{resource_type}", resource_name="{resource_type}")'

            init_body = re.sub(super_pattern, replace_super, init_body)
        else:
            # Add super call at the beginning
            lines = init_body.split("\n")
            if lines and lines[0].strip():
                # Insert super call before the first line
                super_call = f'{indent}super().__init__(config or {{}}, resource_type="{resource_type}", resource_name=config.get("name", "{resource_type}") if config else "{resource_type}")'
                lines.insert(0, super_call)
                init_body = "\n".join(lines)

        return f'def __init__(self{match.group(0)[len("def __init__(self"):-len(init_body)-1]}) -> None:\n{indent}{init_body}'

    content = re.sub(init_pattern, replace_init, content, flags=re.DOTALL)

    return content


def migrate_config_file(file_path: Path) -> bool:
    """Migrate a single configuration file"""
    print(f"Migrating {file_path.name}...")

    try:
        # Read original content
        original_content = file_path.read_text()

        # Create backup
        backup_path = backup_file(file_path)
        print(f"  Created backup: {backup_path}")

        # Apply transformations
        content = original_content
        content = update_imports(content)
        content = update_class_inheritance(content, file_path.name)
        content = update_constructor(content, file_path.name)

        # Write updated content
        file_path.write_text(content)
        print(f"  ✓ Updated {file_path.name}")

        return True

    except Exception as e:
        print(f"  ✗ Error migrating {file_path.name}: {e}")
        return False


def update_stack_files(base_path: str) -> None:
    """Update stack files to use EnhancedSsmParameterMixin"""
    stack_dir = Path(base_path) / "src" / "cdk_factory" / "stack_library"

    # Find all stack files
    stack_files = []
    for stack_type_dir in stack_dir.iterdir():
        if stack_type_dir.is_dir():
            stack_file = stack_type_dir / f"{stack_type_dir.name}_stack.py"
            if stack_file.exists():
                stack_files.append(stack_file)

    for stack_file in stack_files:
        print(f"Updating stack: {stack_file.name}")

        try:
            content = stack_file.read_text()

            # Create backup
            backup_path = backup_file(stack_file)

            # Add EnhancedSsmParameterMixin import if not present
            if "EnhancedSsmParameterMixin" not in content:
                import_pattern = r"(from cdk_factory\.interfaces\.istack import IStack)"
                replacement = r"\1\nfrom cdk_factory.interfaces.enhanced_ssm_parameter_mixin import EnhancedSsmParameterMixin"
                content = re.sub(import_pattern, replacement, content)

            # Update class inheritance to include EnhancedSsmParameterMixin
            class_pattern = r"class\s+(\w+Stack)\(IStack\):"
            replacement = r"class \1(IStack, EnhancedSsmParameterMixin):"
            content = re.sub(class_pattern, replacement, content)

            # Write updated content
            stack_file.write_text(content)
            print(f"  ✓ Updated {stack_file.name}")

        except Exception as e:
            print(f"  ✗ Error updating {stack_file.name}: {e}")


def main():
    """Main migration function"""
    base_path = (
        "/Users/eric.wilson/Documents/projects/geek-cafe/my-cool-app/cdk-factory"
    )

    print("🚀 Starting Enhanced SSM Parameter Pattern Migration")
    print("=" * 60)

    # Find configuration files to migrate
    config_files = find_config_files(base_path)
    print(f"Found {len(config_files)} configuration files to migrate")

    # Migrate configuration files
    success_count = 0
    for config_file in config_files:
        if migrate_config_file(config_file):
            success_count += 1

    print(f"\n📊 Configuration Migration Results:")
    print(f"  ✓ Successfully migrated: {success_count}")
    print(f"  ✗ Failed to migrate: {len(config_files) - success_count}")

    # Update stack files
    print(f"\n🔧 Updating stack files...")
    update_stack_files(base_path)

    print(f"\n✅ Migration completed!")
    print(f"📝 Backup files created with .backup extension")
    print(f"🧪 Please run tests to verify the migration")


if __name__ == "__main__":
    main()
