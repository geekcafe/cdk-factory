"""
Unit tests for ApiGatewayConfig nested_stacks properties.
Validates requirements 5.1, 6.1, 6.2, 6.3.
"""

from cdk_factory.configurations.resources.api_gateway import ApiGatewayConfig


class TestApiGatewayNestedStacksConfig:
    """Test ApiGatewayConfig nested_stacks configuration properties."""

    def test_nested_stacks_config_returns_section_when_present(self):
        """Verify nested_stacks_config returns the nested_stacks dict."""
        config = ApiGatewayConfig(
            config={
                "name": "test-api",
                "nested_stacks": {
                    "enabled": True,
                    "max_resources_per_stack": 150,
                    "grouping": {"users": ["users"]},
                },
            }
        )
        result = config.nested_stacks_config
        assert result is not None
        assert result["enabled"] is True
        assert result["max_resources_per_stack"] == 150
        assert result["grouping"] == {"users": ["users"]}

    def test_nested_stacks_config_returns_none_when_absent(self):
        """Verify nested_stacks_config returns None when section is absent."""
        config = ApiGatewayConfig(config={"name": "test-api"})
        assert config.nested_stacks_config is None

    def test_nested_stacks_enabled_true(self):
        """Verify nested_stacks_enabled returns True when enabled is set."""
        config = ApiGatewayConfig(
            config={
                "name": "test-api",
                "nested_stacks": {"enabled": True},
            }
        )
        assert config.nested_stacks_enabled is True

    def test_nested_stacks_enabled_false(self):
        """Verify nested_stacks_enabled returns False when enabled is False."""
        config = ApiGatewayConfig(
            config={
                "name": "test-api",
                "nested_stacks": {"enabled": False},
            }
        )
        assert config.nested_stacks_enabled is False

    def test_nested_stacks_enabled_defaults_false_when_key_omitted(self):
        """Verify nested_stacks_enabled defaults to False when enabled key is omitted (Req 6.3)."""
        config = ApiGatewayConfig(
            config={
                "name": "test-api",
                "nested_stacks": {"grouping": {"users": ["users"]}},
            }
        )
        assert config.nested_stacks_enabled is False

    def test_nested_stacks_enabled_defaults_false_when_section_absent(self):
        """Verify nested_stacks_enabled defaults to False when section is absent (Req 6.1)."""
        config = ApiGatewayConfig(config={"name": "test-api"})
        assert config.nested_stacks_enabled is False

    def test_nested_stacks_grouping_returns_map(self):
        """Verify nested_stacks_grouping returns the grouping map."""
        grouping = {
            "users": ["users"],
            "workflow-api": ["workflow/api"],
            "file-system": ["file-system"],
        }
        config = ApiGatewayConfig(
            config={
                "name": "test-api",
                "nested_stacks": {"enabled": True, "grouping": grouping},
            }
        )
        assert config.nested_stacks_grouping == grouping

    def test_nested_stacks_grouping_returns_empty_dict_when_absent(self):
        """Verify nested_stacks_grouping returns empty dict when grouping key is absent."""
        config = ApiGatewayConfig(
            config={
                "name": "test-api",
                "nested_stacks": {"enabled": True},
            }
        )
        assert config.nested_stacks_grouping == {}

    def test_nested_stacks_grouping_returns_empty_dict_when_section_absent(self):
        """Verify nested_stacks_grouping returns empty dict when section is absent."""
        config = ApiGatewayConfig(config={"name": "test-api"})
        assert config.nested_stacks_grouping == {}

    def test_max_resources_per_stack_returns_configured_value(self):
        """Verify max_resources_per_stack returns the configured value."""
        config = ApiGatewayConfig(
            config={
                "name": "test-api",
                "nested_stacks": {"enabled": True, "max_resources_per_stack": 150},
            }
        )
        assert config.max_resources_per_stack == 150

    def test_max_resources_per_stack_defaults_to_200(self):
        """Verify max_resources_per_stack defaults to 200 when key is absent."""
        config = ApiGatewayConfig(
            config={
                "name": "test-api",
                "nested_stacks": {"enabled": True},
            }
        )
        assert config.max_resources_per_stack == 200

    def test_max_resources_per_stack_defaults_to_200_when_section_absent(self):
        """Verify max_resources_per_stack defaults to 200 when section is absent."""
        config = ApiGatewayConfig(config={"name": "test-api"})
        assert config.max_resources_per_stack == 200
