"""
Unit tests for the opt-in generic shared-secret seeder IAM statement on the
shared CodeBuild role (CodeBuildPolicy.code_build_policies).

Asserts the SharedSecretSeeder statement is ABSENT by default and PRESENT only
when `pipeline.shared_secret_seeder_secrets` declares one or more secret
patterns. When present it must be Secrets-Manager-only (Get+Put) and scoped to
the configured pattern ARN(s) — NEVER "*".

Synthesis is CDK-only (no live boto3 / no AWS calls), mirroring the AppSync
seeder policy test.
"""

from aws_cdk import App, Stack
from aws_cdk import aws_iam as iam

from cdk_factory.configurations.pipeline import PipelineConfig
from cdk_factory.pipeline.security.policies import CodeBuildPolicy


SEEDER_SID = "SharedSecretSeeder"


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


def _build_policies(secrets):
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
    if secrets is not None:
        pipeline_dict["shared_secret_seeder_secrets"] = secrets

    pipeline = PipelineConfig(pipeline=pipeline_dict, workload=_workload_dict())
    return CodeBuildPolicy().code_build_policies(pipeline, role)


def _collect_sids(statements) -> set:
    sids = set()
    for stmt in statements:
        sid = stmt.to_statement_json().get("Sid")
        if sid:
            sids.add(sid)
    return sids


class TestSharedSecretSeederPolicyGating:
    """The shared-secret seeder statement is opt-in (default off)."""

    def test_default_absent_when_unset(self):
        """List absent -> no SharedSecretSeeder statement on the shared role."""
        assert (
            PipelineConfig(
                pipeline={"name": "p", "branch": "main", "npm_build_mode": "install"},
                workload=_workload_dict(),
            ).shared_secret_seeder_secrets
            == []
        )

        sids = _collect_sids(_build_policies(secrets=None))
        assert SEEDER_SID not in sids

    def test_default_absent_when_empty_list(self):
        """Empty list -> no SharedSecretSeeder statement (default-off)."""
        sids = _collect_sids(_build_policies(secrets=[]))
        assert SEEDER_SID not in sids

    def test_present_scoped_when_configured(self):
        """Configured -> Get+Put only, scoped to the configured pattern ARN."""
        statements = _build_policies(
            secrets=["event-bus/ingress/shared-secret*"]
        )
        sids = _collect_sids(statements)
        assert SEEDER_SID in sids

        stmt = next(
            s.to_statement_json()
            for s in statements
            if s.to_statement_json().get("Sid") == SEEDER_SID
        )

        # Secrets Manager Get+Put ONLY — no appsync actions, no wildcards.
        assert set(stmt["Action"]) == {
            "secretsmanager:GetSecretValue",
            "secretsmanager:PutSecretValue",
        }

        # Scoped to the configured pattern ARN — NEVER "*".
        assert stmt["Resource"] == (
            "arn:aws:secretsmanager:us-east-1:123456789012:"
            "secret:event-bus/ingress/shared-secret*"
        )
        assert stmt["Resource"] != "*"

    def test_multiple_patterns_each_scoped(self):
        """Each configured pattern becomes its own scoped ARN resource."""
        statements = _build_policies(
            secrets=[
                "event-bus/ingress/shared-secret*",
                "other/service/token*",
            ]
        )
        stmt = next(
            s.to_statement_json()
            for s in statements
            if s.to_statement_json().get("Sid") == SEEDER_SID
        )
        resources = stmt["Resource"]
        assert isinstance(resources, list)
        assert set(resources) == {
            "arn:aws:secretsmanager:us-east-1:123456789012:"
            "secret:event-bus/ingress/shared-secret*",
            "arn:aws:secretsmanager:us-east-1:123456789012:secret:other/service/token*",
        }
        assert "*" not in resources
