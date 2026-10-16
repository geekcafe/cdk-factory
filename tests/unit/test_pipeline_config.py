"""
Unit tests for PipelineConfig cross_account_role_arns property.
"""

from cdk_factory.configurations.pipeline import PipelineConfig


class TestPipelineConfig:
    """Test PipelineConfig cross-account role ARNs."""

    def test_cross_account_role_arns_configured(self):
        """Verify cross_account_role_arns returns the configured list."""
        pipeline_dict = {
            "name": "test-pipeline",
            "branch": "main",
            "enabled": True,
            "npm_build_mode": "install",
            "cross_account_role_arns": [
                "arn:aws:iam::111111111111:role/CrossAccountRole",
                "arn:aws:iam::222222222222:role/CrossAccountRole",
            ],
        }
        workload_dict = {"name": "test-workload"}
        config = PipelineConfig(pipeline=pipeline_dict, workload=workload_dict)

        assert config.cross_account_role_arns == [
            "arn:aws:iam::111111111111:role/CrossAccountRole",
            "arn:aws:iam::222222222222:role/CrossAccountRole",
        ]

    def test_cross_account_role_arns_default(self):
        """Verify cross_account_role_arns returns empty list when absent."""
        pipeline_dict = {
            "name": "test-pipeline",
            "branch": "main",
            "enabled": True,
            "npm_build_mode": "install",
        }
        workload_dict = {"name": "test-workload"}
        config = PipelineConfig(pipeline=pipeline_dict, workload=workload_dict)

        assert config.cross_account_role_arns == []

    def test_enable_appsync_key_seeder_default_false(self):
        """Verify enable_appsync_key_seeder defaults to False when absent."""
        pipeline_dict = {
            "name": "test-pipeline",
            "branch": "main",
            "enabled": True,
            "npm_build_mode": "install",
        }
        workload_dict = {"name": "test-workload"}
        config = PipelineConfig(pipeline=pipeline_dict, workload=workload_dict)

        assert config.enable_appsync_key_seeder is False

    def test_enable_appsync_key_seeder_true(self):
        """Verify enable_appsync_key_seeder returns True when opted in."""
        for value in (True, "true", "True"):
            pipeline_dict = {
                "name": "test-pipeline",
                "branch": "main",
                "enabled": True,
                "npm_build_mode": "install",
                "enable_appsync_key_seeder": value,
            }
            workload_dict = {"name": "test-workload"}
            config = PipelineConfig(pipeline=pipeline_dict, workload=workload_dict)

            assert config.enable_appsync_key_seeder is True
