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
