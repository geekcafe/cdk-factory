"""
Unit tests for the opt-in AppSync key-seeder IAM statements on the shared
CodeBuild role (CodeBuildPolicy.code_build_policies).

Asserts the two seeder statements are ABSENT by default and PRESENT only when
`pipeline.enable_appsync_key_seeder` is set true. Scope of the statements is
fixed by design — these tests guard the opt-in gating, not the scope.
"""

from aws_cdk import App, Stack
from aws_cdk import aws_iam as iam

from cdk_factory.configurations.pipeline import PipelineConfig
from cdk_factory.pipeline.security.policies import CodeBuildPolicy


SEEDER_SIDS = {"AppSyncEventsApiKeySeeder", "RealtimeApiKeySecretSeeder"}


def _workload_dict() -> dict:
    return {
        "name": "test-workload",
        "devops": {
            "name": "test-devops",
            "account": "123456789012",
            "region": "us-east-1",
        },
        "deployments": [],
    }


def _build_policies(enable_seeder: bool):
    app = App()
    stack = Stack(app, "TestStack")
    role = iam.Role(
        stack,
        "CodeArtifactAccessRole",
        assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
    )

    pipeline_dict = {
        "name": "test-pipeline",
        "branch": "main",
        "enabled": True,
        "npm_build_mode": "install",
    }
    if enable_seeder:
        pipeline_dict["enable_appsync_key_seeder"] = True

    pipeline = PipelineConfig(pipeline=pipeline_dict, workload=_workload_dict())
    statements = CodeBuildPolicy().code_build_policies(pipeline, role)
    return statements


def _collect_sids(statements) -> set:
    sids = set()
    for stmt in statements:
        sid = stmt.to_statement_json().get("Sid")
        if sid:
            sids.add(sid)
    return sids


class TestAppSyncKeySeederPolicyGating:
    """The seeder statements are opt-in (default off)."""

    def test_default_absent(self):
        """Flag absent -> neither seeder statement is on the shared role."""
        assert (
            PipelineConfig(
                pipeline={"name": "p", "branch": "main", "npm_build_mode": "install"},
                workload=_workload_dict(),
            ).enable_appsync_key_seeder
            is False
        )

        sids = _collect_sids(_build_policies(enable_seeder=False))
        assert not (
            SEEDER_SIDS & sids
        ), f"seeder statements must be absent by default; found {SEEDER_SIDS & sids}"

    def test_present_when_enabled(self):
        """Flag true -> both seeder statements are present with the design scope."""
        statements = _build_policies(enable_seeder=True)
        sids = _collect_sids(statements)
        assert SEEDER_SIDS <= sids, f"expected both seeder statements; got {sids}"

        by_sid = {
            s.to_statement_json().get("Sid"): s.to_statement_json()
            for s in statements
            if s.to_statement_json().get("Sid") in SEEDER_SIDS
        }

        appsync = by_sid["AppSyncEventsApiKeySeeder"]
        assert set(appsync["Action"]) == {
            "appsync:ListApiKeys",
            "appsync:CreateApiKey",
            "appsync:GetApiKey",
        }
        # appsync:ListApiKeys/CreateApiKey/GetApiKey are not resource-scopable
        # (empty resource-type column in the AWS Service Authorization
        # Reference), so the only Resource that matches them is "*".
        assert appsync["Resource"] == "*"

        secret = by_sid["RealtimeApiKeySecretSeeder"]
        assert set(secret["Action"]) == {
            "secretsmanager:GetSecretValue",
            "secretsmanager:PutSecretValue",
        }
        assert secret["Resource"] == (
            "arn:aws:secretsmanager:us-east-1:123456789012:"
            "secret:realtime/appsync-events/api-key*"
        )
