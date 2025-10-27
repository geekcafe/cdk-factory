"""
Unit tests for Enhanced SSM Configuration Path Handling

Tests cover:
- SSM config structure (ssm.exports vs ssm_exports)
- Custom path handling with leading /
- Template variable substitution
- Export/import path matching
- Pattern vs custom path logic
"""

import pytest
from cdk_factory.configurations.enhanced_ssm_config import EnhancedSsmConfig


class TestEnhancedSsmConfigStructure:
    """Test SSM configuration structure requirements"""
    
    def test_ssm_exports_structure(self):
        """Test that ssm.exports structure is recognized"""
        config = {
            "ssm": {
                "auto_export": False,  # Disable auto-export to only get explicit exports
                "exports": {
                    "vpc_id": "/prod/my-app/vpc/id",
                    "vpc_cidr": "/prod/my-app/vpc/cidr"
                }
            }
        }
        
        ssm_config = EnhancedSsmConfig(
            config=config,
            resource_type="vpc",
            resource_name="main-vpc",
            workload_config={"environment": "prod", "name": "my-app"}
        )
        
        assert ssm_config.enabled
        exports = ssm_config.get_export_definitions()
        assert len(exports) == 2
        
    def test_ssm_imports_structure(self):
        """Test that ssm.imports structure is recognized"""
        config = {
            "ssm": {
                "auto_import": False,  # Disable auto-import to only get explicit imports
                "imports": {
                    "vpc_id": "/prod/my-app/vpc/id",
                    "security_group_id": "/prod/my-app/sg/main-id"
                }
            }
        }
        
        ssm_config = EnhancedSsmConfig(
            config=config,
            resource_type="security_group",
            resource_name="main-sg",
            workload_config={"environment": "prod", "name": "my-app"}
        )
        
        imports = ssm_config.get_import_definitions()
        # Filter out metadata fields
        actual_imports = [i for i in imports if i.attribute not in ["workload", "environment", "organization"]]
        assert len(actual_imports) == 2
        
    def test_legacy_ssm_exports_not_recognized(self):
        """Test that old ssm_exports structure is NOT automatically recognized"""
        config = {
            "ssm_exports": {
                "vpc_id": "/prod/my-app/vpc/id"
            }
        }
        
        ssm_config = EnhancedSsmConfig(
            config=config,
            resource_type="vpc",
            resource_name="main-vpc",
            workload_config={"environment": "prod", "name": "my-app"}
        )
        
        # ssm_exports at root level won't be found by config.get("ssm")
        # EnhancedSsmConfig is enabled by default, but exports won't be found
        exports = ssm_config.get_export_definitions()
        # Should not have the vpc_id from ssm_exports (only auto-discovered ones)
        vpc_id_exports = [e for e in exports if e.attribute == "vpc_id" and "/prod/my-app/vpc/id" in e.path]
        assert len(vpc_id_exports) == 0


class TestCustomPathHandling:
    """Test custom SSM path handling"""
    
    def test_custom_path_with_leading_slash_used_as_is(self):
        """Test that custom paths starting with / are used as-is"""
        config = {
            "ssm": {
                "exports": {
                    "vpc_id": "/prod/my-app/vpc/id"
                }
            }
        }
        
        ssm_config = EnhancedSsmConfig(
            config=config,
            resource_type="vpc",
            resource_name="main-vpc",
            workload_config={"environment": "prod", "name": "my-app"}
        )
        
        path = ssm_config.get_parameter_path("vpc_id", "/prod/my-app/vpc/id")
        assert path == "/prod/my-app/vpc/id"
        
    def test_custom_path_without_leading_slash_uses_pattern(self):
        """Test that paths without leading / use the default pattern"""
        config = {
            "ssm": {
                "workload": "my-app",
                "pattern": "/{workload}/{environment}/vpc/{attribute}"
            }
        }
        
        ssm_config = EnhancedSsmConfig(
            config=config,
            resource_type="vpc",
            resource_name="main-vpc",
            workload_config={"environment": "prod", "name": "my-app"}
        )
        
        # No leading slash, so pattern should be applied
        path = ssm_config.get_parameter_path("vpc_id", "prod/my-app/vpc/id")
        # Should use pattern instead
        assert path == "/my-app/prod/vpc/vpc-id"
        
    def test_no_custom_path_uses_default_pattern(self):
        """Test that default pattern is used when no custom path provided"""
        config = {
            "ssm": {
                "workload": "my-app"
            }
        }
        
        ssm_config = EnhancedSsmConfig(
            config=config,
            resource_type="vpc",
            resource_name="main-vpc",
            workload_config={"environment": "prod", "name": "my-app"}
        )
        
        path = ssm_config.get_parameter_path("vpc_id")
        # Default pattern: /{workload}/{environment}/{stack_type}/{resource_name}/{attribute}
        assert path == "/my-app/prod/vpc/main-vpc/vpc-id"


class TestExportImportPathMatching:
    """Test that export and import paths match correctly"""
    
    def test_vpc_export_import_match(self):
        """Test VPC exports and imports use same paths"""
        export_config = {
            "ssm": {
                "exports": {
                    "vpc_id": "/prod/trav-talks/vpc/id",
                    "public_subnet_ids": "/prod/trav-talks/vpc/public-subnet-ids"
                }
            }
        }
        
        import_config = {
            "ssm": {
                "imports": {
                    "vpc_id": "/prod/trav-talks/vpc/id"
                }
            }
        }
        
        workload = {"environment": "prod", "name": "trav-talks"}
        
        export_ssm = EnhancedSsmConfig(
            config=export_config,
            resource_type="vpc",
            resource_name="main-vpc",
            workload_config=workload
        )
        
        import_ssm = EnhancedSsmConfig(
            config=import_config,
            resource_type="security_group",
            resource_name="main-sg",
            workload_config=workload
        )
        
        exports = export_ssm.get_export_definitions()
        imports = import_ssm.get_import_definitions()
        
        # Find the vpc_id export and import
        vpc_id_export = next(e for e in exports if e.attribute == "vpc_id")
        vpc_id_import = next(i for i in imports if i.attribute == "vpc_id")
        
        # Paths should match exactly
        assert vpc_id_export.path == vpc_id_import.path == "/prod/trav-talks/vpc/id"
        
    def test_security_group_export_import_match(self):
        """Test security group exports and imports use same paths"""
        sg_export_config = {
            "ssm": {
                "exports": {
                    "security_group_id": "/prod/trav-talks/sg/alb-id"
                }
            }
        }
        
        sg_import_config = {
            "ssm": {
                "imports": {
                    "source_security_group_id": "/prod/trav-talks/sg/alb-id"
                }
            }
        }
        
        workload = {"environment": "prod", "name": "trav-talks"}
        
        export_ssm = EnhancedSsmConfig(
            config=sg_export_config,
            resource_type="security_group",
            resource_name="alb-sg",
            workload_config=workload
        )
        
        import_ssm = EnhancedSsmConfig(
            config=sg_import_config,
            resource_type="security_group",
            resource_name="ecs-sg",
            workload_config=workload
        )
        
        exports = export_ssm.get_export_definitions()
        imports = import_ssm.get_import_definitions()
        
        sg_export = next(e for e in exports if e.attribute == "security_group_id")
        sg_import = next(i for i in imports if i.attribute == "source_security_group_id")
        
        # Paths should match
        assert sg_export.path == sg_import.path == "/prod/trav-talks/sg/alb-id"


class TestAttributeFormatting:
    """Test attribute name formatting in paths"""
    
    def test_underscore_to_hyphen_conversion(self):
        """Test that underscores in attributes are converted to hyphens"""
        config = {"ssm": {}}
        
        ssm_config = EnhancedSsmConfig(
            config=config,
            resource_type="vpc",
            resource_name="main-vpc",
            workload_config={"environment": "prod", "name": "my-app"}
        )
        
        # Attribute with underscores
        path = ssm_config.get_parameter_path("public_subnet_ids")
        # Should have hyphens in the path
        assert "public-subnet-ids" in path
        assert "public_subnet_ids" not in path


class TestEnvironmentResolution:
    """Test environment resolution from different sources"""
    
    def test_environment_from_workload_config(self):
        """Test environment is read from workload config"""
        config = {"ssm": {}}
        
        ssm_config = EnhancedSsmConfig(
            config=config,
            resource_type="vpc",
            resource_name="main-vpc",
            workload_config={"environment": "staging", "name": "my-app"}
        )
        
        assert ssm_config.environment == "staging"
        
    def test_environment_in_generated_path(self):
        """Test environment appears in generated path"""
        config = {"ssm": {}}
        
        ssm_config = EnhancedSsmConfig(
            config=config,
            resource_type="vpc",
            resource_name="main-vpc",
            workload_config={"environment": "prod", "name": "my-app"}
        )
        
        path = ssm_config.get_parameter_path("vpc_id")
        assert "/prod/" in path
        
    def test_workload_name_in_generated_path(self):
        """Test workload name appears in generated path"""
        config = {
            "ssm": {
                "workload": "trav-talks"
            }
        }
        
        ssm_config = EnhancedSsmConfig(
            config=config,
            resource_type="vpc",
            resource_name="main-vpc",
            workload_config={"environment": "prod", "name": "trav-talks"}
        )
        
        path = ssm_config.get_parameter_path("vpc_id")
        assert "/trav-talks/" in path


class TestRealWorldScenarios:
    """Test real-world configuration scenarios"""
    
    def test_vpc_configuration(self):
        """Test VPC SSM configuration as used in real configs"""
        vpc_config = {
            "ssm": {
                "auto_export": False,  # Disable auto-export to test only explicit exports
                "exports": {
                    "vpc_id": "/prod/trav-talks/vpc/id",
                    "vpc_cidr": "/prod/trav-talks/vpc/cidr",
                    "public_subnet_ids": "/prod/trav-talks/vpc/public-subnet-ids",
                    "private_subnet_ids": "/prod/trav-talks/vpc/private-subnet-ids"
                }
            }
        }
        
        ssm_config = EnhancedSsmConfig(
            config=vpc_config,
            resource_type="vpc",
            resource_name="trav-talks-prod-vpc",
            workload_config={"environment": "prod", "name": "trav-talks"}
        )
        
        exports = ssm_config.get_export_definitions()
        assert len(exports) == 4
        
        # Check all paths start with / and contain the expected pattern
        explicit_exports = {e.attribute: e.path for e in exports}
        assert explicit_exports["vpc_id"] == "/prod/trav-talks/vpc/id"
        assert explicit_exports["vpc_cidr"] == "/prod/trav-talks/vpc/cidr"
        assert explicit_exports["public_subnet_ids"] == "/prod/trav-talks/vpc/public-subnet-ids"
        assert explicit_exports["private_subnet_ids"] == "/prod/trav-talks/vpc/private-subnet-ids"
            
    def test_rds_configuration(self):
        """Test RDS SSM configuration with imports"""
        rds_config = {
            "ssm": {
                "auto_import": False,  # Disable auto-import to test only explicit imports
                "imports": {
                    "vpc_id": "/prod/trav-talks/vpc/id",
                    "subnet_ids": "/prod/trav-talks/vpc/private-subnet-ids",
                    "security_group_rds_id": "/prod/trav-talks/sg/rds-id"
                }
            }
        }
        
        ssm_config = EnhancedSsmConfig(
            config=rds_config,
            resource_type="rds",
            resource_name="trav-talks-prod-rds",
            workload_config={"environment": "prod", "name": "trav-talks"}
        )
        
        imports = ssm_config.get_import_definitions()
        actual_imports = [i for i in imports if i.attribute not in ["workload", "environment", "organization"]]
        assert len(actual_imports) == 3
        
        # Verify all import paths
        vpc_import = next(i for i in imports if i.attribute == "vpc_id")
        assert vpc_import.path == "/prod/trav-talks/vpc/id"
        
        subnet_import = next(i for i in imports if i.attribute == "subnet_ids")
        assert subnet_import.path == "/prod/trav-talks/vpc/private-subnet-ids"
        
        sg_import = next(i for i in imports if i.attribute == "security_group_rds_id")
        assert sg_import.path == "/prod/trav-talks/sg/rds-id"


class TestEdgeCases:
    """Test edge cases and error scenarios"""
    
    def test_empty_ssm_config(self):
        """Test handling of empty SSM config"""
        config = {}
        
        ssm_config = EnhancedSsmConfig(
            config=config,
            resource_type="vpc",
            resource_name="main-vpc",
            workload_config={"environment": "prod", "name": "my-app"}
        )
        
        # EnhancedSsmConfig is enabled by default even without ssm key
        # But it will use auto-discovery instead of explicit config
        assert ssm_config.enabled
        
    def test_ssm_disabled_explicitly(self):
        """Test explicit SSM disable"""
        config = {
            "ssm": {
                "enabled": False
            }
        }
        
        ssm_config = EnhancedSsmConfig(
            config=config,
            resource_type="vpc",
            resource_name="main-vpc",
            workload_config={"environment": "prod", "name": "my-app"}
        )
        
        assert not ssm_config.enabled
        
    def test_invalid_custom_path_ignored(self):
        """Test that non-string or non-dict export values don't break"""
        config = {
            "ssm": {
                "exports": {
                    "enabled": True  # This shouldn't be treated as a path
                }
            }
        }
        
        ssm_config = EnhancedSsmConfig(
            config=config,
            resource_type="vpc",
            resource_name="main-vpc",
            workload_config={"environment": "prod", "name": "my-app"}
        )
        
        # Should handle gracefully - enabled is not a valid export path
        exports = ssm_config.get_export_definitions()
        # enabled=True won't create a valid export since it's not a string path
        enabled_exports = [e for e in exports if e.attribute == "enabled"]
        if enabled_exports:
            # If it does create one, it should use the pattern
            assert enabled_exports[0].path.startswith("/")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
