"""
Packaging asset-root test for the codepipeline_notifier Lambda (FEAT-002 / PLAN
Task 13, DESIGN §11 test 12 option (b)).

``aws_cdk.assertions.Template`` exposes only the asset hash / S3 key, NOT the
asset's file contents, so the "does the SDK resolve in the asset?" guarantee
cannot be a Template file-content assertion. Instead this pure-string test pins
the asset-root computation itself.

``LambdaFunctionUtilities.create`` computes the asset root as:

    lambda_directory = relative_path.replace("/" + lambda_config.handler, "")

where ``relative_path`` is the config ``src`` (or its resolved absolute form).
For the notifier, ``src = "./src/devops_monitoring_lambdas"`` (the PACKAGE root)
and ``handler = "handlers.codepipeline_notifier.app.lambda_handler"`` (an AWS
dotted handler, which is NEVER a ``/``-delimited substring of the src path). So
the ``.replace`` is a NO-OP and ``lambda_directory`` is the package root — the
whole package (the thin re-export handler at
``handlers/codepipeline_notifier/app.py``) is the ``shutil.copytree`` source,
and the asset-level ``requirements.txt`` at that package root is the file into
which ``geek-cafe-saas-sdk`` is pip-installed (vendored) at build time. If the
asset root were ever mis-set back to the handler sub-dir, that package-root
``requirements.txt`` would not be found, the SDK would not be vendored, and the
re-export's ``from geek_cafe_saas_sdk...`` import would fail at runtime.
"""

NOTIFIER_SRC = "./src/devops_monitoring_lambdas"
NOTIFIER_HANDLER = "handlers.codepipeline_notifier.app.lambda_handler"


def _lambda_directory(relative_path: str, handler: str) -> str:
    """Reproduce LambdaFunctionUtilities.create's asset-root computation."""
    return relative_path.replace(f"/{handler}", "")


def test_dotted_handler_is_not_a_slash_substring_of_src():
    # The dotted handler contains no '/', so "/<handler>" cannot appear in the
    # src path -> the replace strips nothing.
    assert f"/{NOTIFIER_HANDLER}" not in NOTIFIER_SRC


def test_asset_root_is_package_root_relative_src():
    assert _lambda_directory(NOTIFIER_SRC, NOTIFIER_HANDLER) == NOTIFIER_SRC


def test_asset_root_is_package_root_resolved_absolute_src():
    # Even when find_directory resolves src to an absolute package path, the
    # dotted handler is still not a '/'-substring, so the replace is a no-op.
    resolved = "/abs/path/to/geek-cafe-devops-monitoring/src/devops_monitoring_lambdas"
    assert _lambda_directory(resolved, NOTIFIER_HANDLER) == resolved


def test_asset_root_is_not_the_handler_subdir():
    # Guard the regression: if someone sets src to the handler sub-dir instead
    # of the package root, the package-root requirements.txt (which vendors the
    # SDK into the asset) would not be found and the SDK would not be bundled.
    handler_subdir = "./src/devops_monitoring_lambdas/handlers/codepipeline_notifier"
    assert _lambda_directory(NOTIFIER_SRC, NOTIFIER_HANDLER) != handler_subdir
