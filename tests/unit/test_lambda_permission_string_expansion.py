"""
Regression test for the permission-STRING expansion defect (9d158d68).

Defect: cdk-factory commit 9d158d68 ("refactor: permissions, internal caching,
validations") removed the string->policy expansion. The string identifiers
``dynamodb_read`` / ``dynamodb_write`` / ``dynamodb_delete`` (and the ``s3_*``
shorthands) still PASS validation (they are listed in
``KNOWN_PERMISSION_STRINGS``), but ``PolicyDocuments.get_permission_details()``
only expanded a tiny ``simple_permissions`` set, so these strings fell through to
an empty ``{}`` and were SILENTLY SKIPPED in
``generate_and_bind_lambda_policy_docs()`` — producing NO IAM statement at all.

The real-world consequence: a public contact-form Lambda declaring
``"permissions": ["dynamodb_read", "dynamodb_write"]`` got ZERO DynamoDB policy,
causing a runtime ``AccessDeniedException`` on ``dynamodb:PutItem``.

The fix re-adds the string->structured expansion (resolving the app table/bucket
name via ``ResourceResolver``) AND fails loudly if a KNOWN permission string
cannot resolve its backing resource — instead of silently dropping the grant.

These tests synthesize a Lambda whose config uses the STRING form and assert
against the SYNTHESIZED template:

* ``dynamodb:PutItem`` + the read actions are rendered, scoped to
  ``table/<name>`` (+ ``/index/*``) — this FAILS on current HEAD and PASSES on
  the fix.
* a KNOWN string that cannot resolve its table RAISES at synth rather than
  silently producing nothing.
* the ``s3_*`` string path renders S3 actions scoped to the configured bucket.
* the STRUCTURED dict path still works (no regression) and the optional-feature
  empty-dict skip is preserved.

Hermetic: no AWS account env vars required (WorkloadConfig gets a stub ``devops``
section); the table/bucket names come from env vars set within each test.
"""

import os
from contextlib import contextmanager

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from cdk_factory.stack_library.aws_lambdas.lambda_stack import LambdaStack
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig
from cdk_factory.configurations.stack import StackConfig


TABLE_NAME = "geekcafe-prod"
BUCKET_NAME = "geekcafe-prod-workload"


@contextmanager
def _env(**overrides):
    """Temporarily set/clear env vars, restoring the prior state afterwards."""
    sentinel = object()
    previous = {k: os.environ.get(k, sentinel) for k in overrides}
    try:
        for key, value in overrides.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, prev in previous.items():
            if prev is sentinel:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev


class TestLambdaPermissionStringExpansion:
    """Verify string-shorthand permissions render real IAM statements."""

    @pytest.fixture
    def app(self):
        return App()

    @pytest.fixture
    def deployment_config(self):
        return DeploymentConfig(
            workload={"name": "test-workload"},
            deployment={
                "name": "test-deployment",
                "account": "123456789012",
                "region": "us-east-1",
                "environment": "test",
            },
        )

    @pytest.fixture
    def workload_config(self):
        # Stub "devops" so the test is hermetic (no AWS account env vars needed).
        return WorkloadConfig(config={"name": "test-workload", "devops": {"name": "d"}})

    def _build_template(
        self, app, deployment_config, workload_config, permissions
    ) -> Template:
        stack_dict = {
            "name": "test-perm-string-stack",
            "auto_export": True,
            "resources": [
                {
                    "name": "perm-string-lambda",
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [],
                    "schedule": None,
                    "permissions": permissions,
                }
            ],
        }
        stack_config = StackConfig(stack=stack_dict, workload={"name": "test-workload"})

        stack = LambdaStack(
            scope=app,
            id="test-perm-string-expansion",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        return Template.from_stack(stack)

    @staticmethod
    def _statements_with_actions(template: Template, required_actions: set):
        """Return IAM policy statements that include all of ``required_actions``."""
        policies = template.find_resources("AWS::IAM::Policy")
        matches = []
        for policy in policies.values():
            statements = policy["Properties"]["PolicyDocument"]["Statement"]
            for statement in statements:
                actions = statement.get("Action", [])
                if isinstance(actions, str):
                    actions = [actions]
                if required_actions.issubset(set(actions)):
                    matches.append(statement)
        return matches

    @staticmethod
    def _all_actions(template: Template) -> set:
        actions = set()
        for policy in template.find_resources("AWS::IAM::Policy").values():
            for statement in policy["Properties"]["PolicyDocument"]["Statement"]:
                acts = statement.get("Action", [])
                if isinstance(acts, str):
                    acts = [acts]
                actions.update(acts)
        return actions

    # ---- the crux: the string path must render a DynamoDB policy ----

    def test_dynamodb_string_permissions_render_policy(
        self, app, deployment_config, workload_config
    ):
        """
        ``["dynamodb_read", "dynamodb_write"]`` (STRING form) MUST render IAM
        statements containing ``dynamodb:PutItem`` and the read actions scoped to
        the app table. This is the exact grant that was silently dropped before
        the fix (0 of 18 policies had any dynamodb action in the real synth).
        """
        with _env(APP_TABLE_NAME=TABLE_NAME):
            template = self._build_template(
                app,
                deployment_config,
                workload_config,
                permissions=["dynamodb_read", "dynamodb_write"],
            )

        write_matches = self._statements_with_actions(template, {"dynamodb:PutItem"})
        assert write_matches, (
            "No IAM statement granting dynamodb:PutItem was rendered from the "
            "STRING-form permissions. The DynamoDB grant was silently dropped "
            "(the 9d158d68 regression)."
        )

        read_matches = self._statements_with_actions(
            template,
            {
                "dynamodb:GetItem",
                "dynamodb:Query",
                "dynamodb:Scan",
                "dynamodb:BatchGetItem",
            },
        )
        assert read_matches, "dynamodb_read string did not render the read actions."

        # The write grant must be scoped to the app table (+ index), not "*".
        for statement in write_matches:
            resources = statement.get("Resource", [])
            if isinstance(resources, str):
                resources = [resources]
            flat = " ".join(str(r) for r in resources)
            assert "*" != resources, "DynamoDB grant must not be a bare wildcard."
            assert f"table/{TABLE_NAME}" in flat, (
                f"DynamoDB grant should be scoped to table/{TABLE_NAME}, "
                f"got: {resources!r}"
            )
            assert (
                f"table/{TABLE_NAME}/index/*" in flat
            ), "DynamoDB grant should include the table index ARN."

    def test_dynamodb_delete_string_renders_delete_action(
        self, app, deployment_config, workload_config
    ):
        """``dynamodb_delete`` renders dynamodb:DeleteItem scoped to the table."""
        with _env(APP_TABLE_NAME=TABLE_NAME):
            template = self._build_template(
                app,
                deployment_config,
                workload_config,
                permissions=["dynamodb_delete"],
            )
        assert self._statements_with_actions(
            template, {"dynamodb:DeleteItem"}
        ), "dynamodb_delete string did not render dynamodb:DeleteItem."

    # ---- fail loudly: a known string that cannot resolve its table ----

    def test_unresolvable_dynamodb_string_raises(
        self, app, deployment_config, workload_config
    ):
        """
        A KNOWN permission string whose table cannot be resolved (no
        APP_TABLE_NAME, no SSM) must RAISE at synth — not silently drop the
        grant. This is the fail-loud guard that the refactor removed.
        """
        with _env(APP_TABLE_NAME=None):
            with pytest.raises(ValueError, match="resolved to no IAM statement"):
                self._build_template(
                    app,
                    deployment_config,
                    workload_config,
                    permissions=["dynamodb_write"],
                )

    # ---- the s3_* string path renders S3 actions ----

    def test_s3_string_permissions_render_policy(
        self, app, deployment_config, workload_config
    ):
        """``s3_write_workload`` renders S3 write actions scoped to the bucket."""
        with _env(WORKLOAD_BUCKET_NAME=BUCKET_NAME):
            template = self._build_template(
                app,
                deployment_config,
                workload_config,
                permissions=["s3_read_workload", "s3_write_workload"],
            )

        write_matches = self._statements_with_actions(template, {"s3:PutObject"})
        assert write_matches, "s3_write_workload string did not render s3:PutObject."
        for statement in write_matches:
            resources = statement.get("Resource", [])
            if isinstance(resources, str):
                resources = [resources]
            flat = " ".join(str(r) for r in resources)
            assert BUCKET_NAME in flat, (
                f"S3 grant should be scoped to the {BUCKET_NAME} bucket, "
                f"got: {resources!r}"
            )

        assert "s3:GetObject" in self._all_actions(
            template
        ), "s3_read_workload string did not render s3:GetObject."

    # ---- the structured DICT path still works (no regression) ----

    def test_structured_dict_path_still_renders(
        self, app, deployment_config, workload_config
    ):
        """The structured dict form must continue to render (unchanged)."""
        template = self._build_template(
            app,
            deployment_config,
            workload_config,
            permissions=[{"dynamodb": "write", "table": TABLE_NAME}],
        )
        assert self._statements_with_actions(
            template, {"dynamodb:PutItem"}
        ), "Structured dict form regressed — dynamodb:PutItem not rendered."

    def test_structured_dict_empty_table_is_skipped_not_raised(
        self, app, deployment_config, workload_config
    ):
        """
        The optional-feature skip for the STRUCTURED dict form with an empty
        table must be preserved: synth succeeds and simply omits the grant
        (contrast the known-STRING form, which raises).
        """
        template = self._build_template(
            app,
            deployment_config,
            workload_config,
            permissions=[{"dynamodb": "write", "table": ""}],
        )
        # No dynamodb statement, but synth did not raise.
        assert not self._statements_with_actions(
            template, {"dynamodb:PutItem"}
        ), "Empty structured dict should produce no DynamoDB grant."

    # ------------------------------------------------------------------
    # Sweep: NO string in KNOWN_PERMISSION_STRINGS may validate and then
    # silently render an empty / no-action policy. Each known string must
    # EITHER produce a statement with >=1 action OR raise at synth.
    # ------------------------------------------------------------------

    def _single_perm_actions(
        self, app_factory, deployment_config, workload_config, perm
    ):
        """Synthesize one Lambda with a single permission; return the set of
        all IAM actions rendered across its policies. Raises propagate."""
        template = self._build_template(
            app_factory(), deployment_config, workload_config, permissions=[perm]
        )
        return self._all_actions(template)

    def test_no_known_string_silently_renders_empty_policy(
        self, deployment_config, workload_config
    ):
        """
        Iterate EVERY entry in KNOWN_PERMISSION_STRINGS. With all backing
        resource env vars provided, each known string must EITHER render at
        least one IAM action OR raise a ValueError at synth. None may validate
        and then silently produce nothing (the 9d158d68 regression class).
        """
        from cdk_factory.stack_library.aws_lambdas.lambda_validation import (
            KNOWN_PERMISSION_STRINGS,
        )
        from cdk_factory.constructs.lambdas.policies.policy_docs import PolicyDocuments

        # Provide every env var any resource string could resolve, so the ones
        # that CAN expand do expand (and must then yield actions).
        resource_env = {
            spec["env"]: f"test-{spec['env'].lower()}"
            for spec in PolicyDocuments._RESOURCE_STRING_PERMISSIONS.values()
        }

        silently_empty = []
        with _env(**resource_env):
            for perm in sorted(KNOWN_PERMISSION_STRINGS):
                try:
                    actions = self._single_perm_actions(
                        App, deployment_config, workload_config, perm
                    )
                except ValueError:
                    # Fail-loud path — acceptable (never silent).
                    continue
                # Subtract the always-present default lambda actions so we only
                # measure what THIS permission string contributed.
                default_actions = {
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "cloudwatch:PutMetricData",
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                }
                contributed = actions - default_actions
                if not contributed:
                    silently_empty.append(perm)

        assert not silently_empty, (
            "These KNOWN_PERMISSION_STRINGS validated but silently produced NO "
            f"IAM action (neither expanded nor raised): {sorted(silently_empty)}. "
            "Every known string must expand to a real policy or fail loudly."
        )

    def test_resource_strings_fail_loud_when_unresolvable(
        self, deployment_config, workload_config
    ):
        """
        With NO backing resource env vars set, every resource-backed known
        string (the dynamodb_*/s3_* set) must RAISE at synth rather than
        silently render nothing. Non-resource strings (cognito_*,
        parameter_store_read) are unaffected and still render.
        """
        from cdk_factory.constructs.lambdas.policies.policy_docs import PolicyDocuments

        resource_env_keys = {
            spec["env"]
            for spec in PolicyDocuments._RESOURCE_STRING_PERMISSIONS.values()
        }
        cleared = {k: None for k in resource_env_keys}

        with _env(**cleared):
            for perm in sorted(PolicyDocuments._RESOURCE_STRING_PERMISSIONS):
                with pytest.raises(ValueError, match="resolved to no IAM statement"):
                    self._single_perm_actions(
                        App, deployment_config, workload_config, perm
                    )

    def test_audit_logging_known_but_unhandled_fails_loud(
        self, app, deployment_config, workload_config
    ):
        """
        'audit_logging' is in KNOWN_PERMISSION_STRINGS but has no expander and
        no recoverable intent — it must hit the fail-loud guard, not silently
        render nothing.
        """
        with pytest.raises(ValueError):
            self._build_template(
                app,
                deployment_config,
                workload_config,
                permissions=["audit_logging"],
            )
