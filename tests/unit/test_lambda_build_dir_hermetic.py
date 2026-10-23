"""
Hermeticity tests for the Lambda ASSET build directory.

Collision bug (observed, root-caused): ``LambdaFunctionUtilities.create`` used a
FIXED build dir keyed only on ``lambda_config.name``
(``$TMPDIR/cdk-factory/lambda-builds/<name>``), then rmtree'd and copytree'd into
it. Concurrent/consecutive synths of the same name — or a run racing a
half-cleaned dir, or stale ``__pycache__`` from a prior session — collided at the
rmtree/copytree step and raised a non-deterministic ``OSError`` (seen at
``shutil.py:658``). The fix makes the build dir per-invocation unique via
``tempfile.mkdtemp`` (no builtin ``hash()``), keeping a stable parent dir for
discoverability, and best-effort removes the build dir in a ``finally``.

These tests prove:
  (a) two builds of the SAME ``lambda_config.name`` resolve to DIFFERENT output
      dirs that never share a leaf (direct hermeticity proof);
  (b) the unique leaf uses the ``<name>-`` prefix under the stable
      ``$TMPDIR/cdk-factory/lambda-builds`` parent;
  (c) the source file contains no builtin ``hash(`` (steering: no builtin hash);
  (d) the asset hash / Lambda logical id is STABLE across invocations despite the
      per-invocation build-dir name differing (``from_asset`` content-hashes the
      zip, so a changed build-dir name must NOT produce a spurious asset diff);
  (e) the per-invocation build dir is cleaned up after ``create()`` returns.
"""

import os
import re
from pathlib import Path

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.lambda_function import LambdaFunctionConfig
from cdk_factory.utilities.file_operations import FileOperations
from cdk_factory.utilities import lambda_function_utilities as lfu_module
from cdk_factory.utilities.lambda_function_utilities import LambdaFunctionUtilities


LAMBDA_NAME = "hermetic-test-function"


@pytest.fixture
def utilities():
    deployment = DeploymentConfig(
        workload={"name": "test-workload"},
        deployment={
            "name": "test-deployment",
            "account": "123456789012",
            "region": "us-east-1",
            "environment": "test",
        },
    )
    workload = WorkloadConfig(config={"name": "test-workload", "devops": {"name": "d"}})
    return LambdaFunctionUtilities(deployment=deployment, workload=workload)


@pytest.fixture
def lambda_config():
    return LambdaFunctionConfig(
        {
            "name": LAMBDA_NAME,
            "src": "tests/unit/files/lambda",
            "handler": "app.lambda_handler",
            "runtime": "python3.11",
            "timeout": 30,
            "memory_size": 256,
        }
    )


def _capture_output_dirs(utilities, lambda_config, monkeypatch, n=2):
    """Drive ``create()`` ``n`` times for the SAME config, capturing the
    ``output_dir`` passed to the build seams on each call.

    The build/zip seams are stubbed so no real copytree/pip/zip happens — the
    test is only concerned with which build dir ``create()`` resolves.
    """
    captured = []

    class _StopAfterCapture(Exception):
        pass

    def fake_validate(self, output_dir, lambda_directory):  # noqa: ARG001
        captured.append(output_dir)

    def fake_requirements(self, *args, **kwargs):  # noqa: ARG001
        return None

    def fake_zip(output_dir, exclude_list=None):  # noqa: ARG001
        # Short-circuit before the real aws_lambda.Function is built — this test
        # only cares about which build dir create() resolves, not the synth.
        raise _StopAfterCapture()

    # Name-mangled private methods.
    monkeypatch.setattr(
        LambdaFunctionUtilities,
        "_LambdaFunctionUtilities__validate_directories",
        fake_validate,
    )
    monkeypatch.setattr(
        LambdaFunctionUtilities,
        "_LambdaFunctionUtilities__requirements",
        fake_requirements,
    )
    monkeypatch.setattr(FileOperations, "zip_directory", staticmethod(fake_zip))

    from aws_cdk import Stack

    for _ in range(n):
        # Build a lightweight scope: a Stack inside a fresh App.
        app = App()
        scope = Stack(
            app,
            "hermetic-scope",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        try:
            utilities.create(
                scope=scope,
                id=LAMBDA_NAME,
                lambda_config=lambda_config,
            )
        except _StopAfterCapture:
            pass

    return captured


def test_two_builds_resolve_to_different_output_dirs(
    utilities, lambda_config, monkeypatch
):
    """Two builds of the SAME lambda name must not share a build dir (leaf)."""
    captured = _capture_output_dirs(utilities, lambda_config, monkeypatch, n=2)
    assert len(captured) == 2
    # Different leaf paths -> no shared dir -> no rmtree/copytree collision.
    assert captured[0] != captured[1]
    # Both live under the same stable parent for discoverability/cleanup.
    parents = {str(Path(p).parent) for p in captured}
    assert len(parents) == 1
    parent = next(iter(parents))
    assert parent.endswith(os.path.join("cdk-factory", "lambda-builds"))


def test_output_dir_uses_name_prefix_under_builds_parent(
    utilities, lambda_config, monkeypatch
):
    """The unique leaf is ``<name>-<unique>`` under $TMPDIR/cdk-factory/lambda-builds."""
    captured = _capture_output_dirs(utilities, lambda_config, monkeypatch, n=1)
    assert len(captured) == 1
    output_dir = captured[0]
    leaf = os.path.basename(output_dir)
    assert leaf.startswith(f"{LAMBDA_NAME}-")

    temp_dir = os.environ.get("TMPDIR", "/tmp")
    if not os.path.exists(temp_dir):
        temp_dir = "/tmp"
    expected_parent = os.path.join(temp_dir, "cdk-factory", "lambda-builds")
    assert os.path.dirname(output_dir) == expected_parent


def test_no_builtin_hash_in_lambda_function_utilities_source():
    """Guard: this file must not use the builtin ``hash(`` for the unique suffix.

    builtin ``hash`` is randomized per process (PYTHONHASHSEED); the fix uses
    ``tempfile.mkdtemp``. (Matches the pattern in
    ``test_no_builtin_hash_in_codepipeline_notifier.py``.)
    """
    source_path = Path(lfu_module.__file__)
    text = source_path.read_text(encoding="utf-8")
    # 'hash(' not preceded by 'lib' (so hashlib.<...>( is allowed).
    builtin_hash = re.compile(r"(?<!lib)\bhash\(")
    assert not builtin_hash.search(text), f"builtin hash( found in {source_path}"


# --- Real-synth tests (SKIP_PIP) -------------------------------------------


def _build_lambda_template(app_id: str) -> Template:
    """Synthesize a single-Lambda stack and return its CloudFormation Template."""
    from cdk_factory.stack_library.aws_lambdas.lambda_stack import LambdaStack

    workload_dict = {
        "name": "test-workload",
        "description": "Test workload for hermetic build-dir testing",
        "devops": {"ci_cd": {"enabled": True}},
    }
    deployment = DeploymentConfig(
        workload=workload_dict,
        deployment={
            "name": "test-deployment",
            "account": "123456789012",
            "region": "us-east-1",
            "environment": "test",
            "devops": {"ci_cd": {"enabled": True}},
        },
    )
    workload = WorkloadConfig(config=workload_dict)
    stack_dict = {
        "name": "test-lambda-stack",
        "enabled": True,
        "resources": [
            {
                "name": LAMBDA_NAME,
                "src": "tests/unit/files/lambda",
                "handler": "app.lambda_handler",
                "runtime": "python3.11",
                "timeout": 30,
                "memory_size": 256,
                "triggers": [],
                "sqs": {"queues": []},
                "schedule": None,
            }
        ],
    }
    stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

    app = App()
    stack = LambdaStack(
        scope=app,
        id=app_id,
        env=Environment(account="123456789012", region="us-east-1"),
    )
    stack.build(
        stack_config=stack_config,
        deployment=deployment,
        workload=workload,
    )
    return Template.from_stack(stack)


def _lambda_logical_id_and_code(template: Template):
    resources = template.find_resources("AWS::Lambda::Function")
    assert len(resources) == 1, f"expected exactly one Lambda, got {len(resources)}"
    logical_id, body = next(iter(resources.items()))
    code = body["Properties"]["Code"]
    return logical_id, code


def test_asset_hash_stable_across_builds(monkeypatch):
    """Asset hash / logical id must be stable across invocations.

    ``aws_lambda.Code.from_asset`` content-hashes the asset (the zip) by default,
    so changing only the per-invocation build-dir NAME must not change the asset
    hash or the Lambda logical id. Outcome recorded: this PASSES with the
    mkdtemp change and no ``AssetHashType.SOURCE`` pin is required (the default
    content hash already ignores the staging path).
    """
    monkeypatch.setenv("SKIP_PIP", "1")

    t1 = _build_lambda_template("stable-stack")
    id1, code1 = _lambda_logical_id_and_code(t1)

    t2 = _build_lambda_template("stable-stack")
    id2, code2 = _lambda_logical_id_and_code(t2)

    # Logical id is derived from the construct id + asset hash; it must be
    # deterministic across synths despite the build-dir name differing.
    assert id1 == id2
    # The asset reference (S3 key / hash) must be identical.
    assert code1 == code2


def test_build_dir_cleaned_up_after_create(utilities, lambda_config, monkeypatch):
    """The per-invocation build dir is removed after ``create()`` returns."""
    monkeypatch.setenv("SKIP_PIP", "1")

    captured = {}
    real_validate = (
        LambdaFunctionUtilities._LambdaFunctionUtilities__validate_directories
    )

    def spy_validate(self, output_dir, lambda_directory):
        captured["output_dir"] = output_dir
        return real_validate(
            self, output_dir=output_dir, lambda_directory=lambda_directory
        )

    monkeypatch.setattr(
        LambdaFunctionUtilities,
        "_LambdaFunctionUtilities__validate_directories",
        spy_validate,
    )

    from aws_cdk import Stack

    app = App()
    scope = Stack(
        app,
        "cleanup-scope",
        env=Environment(account="123456789012", region="us-east-1"),
    )
    utilities.create(scope=scope, id=LAMBDA_NAME, lambda_config=lambda_config)

    output_dir = captured.get("output_dir")
    assert output_dir, "create() did not reach the build-dir validation seam"
    # The finally-block best-effort rmtree should have removed it.
    assert not os.path.exists(
        output_dir
    ), f"per-invocation build dir was not cleaned up: {output_dir}"
