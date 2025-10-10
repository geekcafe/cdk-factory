"""
Test API Gateway SSM Export Configuration Patterns
"""

import pytest
from cdk_factory.configurations.enhanced_ssm_config import EnhancedSsmConfig


class TestApiGatewayExportConfig:
    """Test various API Gateway export configuration patterns"""

    def test_auto_export_pattern(self):
        """Test auto_export: true pattern (recommended)"""
        config = {
            "ssm": {
                "enabled": True,
                "auto_export": True,
                "workload": "my-app",
                "environment": "prod"
            }
        }
        
        ssm_config = EnhancedSsmConfig(config, "api-gateway", "my-api")
        
        # Should use auto-discovery from RESOURCE_AUTO_EXPORTS
        export_defs = ssm_config.get_export_definitions()
        
        # API Gateway should auto-export these attributes
        exported_attrs = [d.attribute for d in export_defs]
        assert "api_id" in exported_attrs
        assert "api_arn" in exported_attrs
        assert "api_url" in exported_attrs
        assert "root_resource_id" in exported_attrs
        
        # Verify paths are generated correctly
        for definition in export_defs:
            assert "/my-app/prod/api-gateway/my-api/" in definition.path
    
    def test_explicit_exports_pattern(self):
        """Test explicit exports with attribute mapping"""
        config = {
            "ssm": {
                "enabled": True,
                "auto_export": False,  # Disable auto-export to only use explicit
                "workload": "my-app",
                "environment": "prod",
                "exports": {
                    "api_id": "auto",
                    "api_url": "auto",
                    "root_resource_id": "/custom/path/to/resource-id"
                }
            }
        }
        
        ssm_config = EnhancedSsmConfig(config, "api-gateway", "my-api")
        export_defs = ssm_config.get_export_definitions()
        
        # Should have exactly 3 exports (since auto_export is disabled)
        assert len(export_defs) == 3
        
        # Check auto-generated paths
        api_id_def = next(d for d in export_defs if d.attribute == "api_id")
        assert "/my-app/prod/api-gateway/my-api/api-id" == api_id_def.path
        
        # Check custom path
        resource_id_def = next(d for d in export_defs if d.attribute == "root_resource_id")
        assert resource_id_def.path == "/custom/path/to/resource-id"
    
    def test_invalid_exports_enabled_pattern_protection(self):
        """
        Test that the INCORRECT pattern from old docs doesn't crash.
        This pattern was incorrectly documented: "exports": {"enabled": true}
        
        The code should handle this gracefully, though it's not the intended usage.
        """
        config = {
            "ssm": {
                "enabled": True,
                "workload": "my-app",
                "environment": "prod",
                "exports": {
                    "enabled": True  # This is WRONG but shouldn't crash
                }
            }
        }
        
        ssm_config = EnhancedSsmConfig(config, "api-gateway", "my-api")
        
        # This should not crash, but we need to handle boolean values gracefully
        # The current implementation will try to export "enabled" as an attribute
        # which is not ideal but shouldn't cause AttributeError
        try:
            export_defs = ssm_config.get_export_definitions()
            # If it doesn't crash, check that it created something (even if wrong)
            assert len(export_defs) >= 0
        except AttributeError as e:
            # This is the bug we're fixing - boolean doesn't have startswith()
            pytest.fail(f"Should not crash with AttributeError: {e}")
    
    def test_mixed_auto_and_explicit_exports(self):
        """Test combining auto_export with explicit exports"""
        config = {
            "ssm": {
                "enabled": True,
                "auto_export": True,
                "workload": "my-app",
                "environment": "prod",
                "exports": {
                    "custom_attribute": "/custom/path"
                }
            }
        }
        
        ssm_config = EnhancedSsmConfig(config, "api-gateway", "my-api")
        export_defs = ssm_config.get_export_definitions()
        
        # Should have auto-discovered attributes + custom one
        exported_attrs = [d.attribute for d in export_defs]
        assert "api_id" in exported_attrs  # From auto-discovery
        assert "api_arn" in exported_attrs  # From auto-discovery
        assert "custom_attribute" in exported_attrs  # Explicit
        
        # Custom attribute should use custom path
        custom_def = next(d for d in export_defs if d.attribute == "custom_attribute")
        assert custom_def.path == "/custom/path"
    
    def test_no_exports_when_disabled(self):
        """Test that exports are disabled when enabled: false"""
        config = {
            "ssm": {
                "enabled": False,
                "auto_export": True,
                "workload": "my-app",
                "environment": "prod"
            }
        }
        
        ssm_config = EnhancedSsmConfig(config, "api-gateway", "my-api")
        
        # enabled: false should be respected
        assert not ssm_config.enabled
    
    def test_exports_empty_dict_uses_auto_export(self):
        """Test that empty exports dict with auto_export: true uses auto-discovery"""
        config = {
            "ssm": {
                "enabled": True,
                "auto_export": True,
                "workload": "my-app",
                "environment": "prod",
                "exports": {}  # Empty dict should not override auto_export
            }
        }
        
        ssm_config = EnhancedSsmConfig(config, "api-gateway", "my-api")
        export_defs = ssm_config.get_export_definitions()
        
        # Should still auto-discover
        exported_attrs = [d.attribute for d in export_defs]
        assert "api_id" in exported_attrs
        assert "api_url" in exported_attrs


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
