"""
Packaging guard: the codepipeline_notifier asset vendors geek-cafe-saas-sdk.

This is the cdk-factory-side half of the three-part "SDK import resolves in the
asset" guarantee (DESIGN §11). The notifier handler in the sibling
``geek-cafe-devops-monitoring`` project is a THIN RE-EXPORT of
``geek_cafe_saas_sdk.modules.devops_monitoring.handlers.codepipeline_notifier.app``;
the SDK must therefore be present in the Lambda asset at runtime.

``LambdaFunctionUtilities.create`` vendors runtime deps by pip-installing a
``requirements.txt`` found at the resolved asset root (the package root, see
``test_codepipeline_notifier_asset_root.py``) into the asset output dir
(``dependencies_to_layer=false``). So the load-bearing contract this test guards
is simply: that asset-level ``requirements.txt`` carries a ``geek-cafe-saas-sdk``
pin. This replaces the prior build's "is ``notify/`` bundled?" intent with
"does ``requirements.txt`` pull the SDK into the asset?".

The sibling repo is not a hard dependency of cdk-factory's own CI, so when it is
absent (e.g. a cdk-factory-only checkout) this test skips rather than fails.
"""

from pathlib import Path

import pytest

# cdk-factory and geek-cafe-devops-monitoring are sibling checkouts under the
# same parent directory. tests/unit/<this file> -> parents[2] == cdk-factory
# repo root -> its parent is the shared projects dir containing the sibling.
_CDK_FACTORY_ROOT = Path(__file__).resolve().parents[2]
_NOTIFIER_ASSET_REQUIREMENTS = (
    _CDK_FACTORY_ROOT.parent
    / "geek-cafe-devops-monitoring"
    / "src"
    / "devops_monitoring_lambdas"
    / "requirements.txt"
)


def test_notifier_asset_requirements_pins_the_sdk():
    if not _NOTIFIER_ASSET_REQUIREMENTS.is_file():
        pytest.skip(
            "sibling geek-cafe-devops-monitoring asset requirements.txt not present "
            f"(looked at {_NOTIFIER_ASSET_REQUIREMENTS})"
        )

    lines = [
        line.strip()
        for line in _NOTIFIER_ASSET_REQUIREMENTS.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    sdk_pins = [line for line in lines if line.split("=")[0].split(">")[0].split("<")[0].strip() == "geek-cafe-saas-sdk"]
    assert sdk_pins, (
        "the notifier asset requirements.txt must pin geek-cafe-saas-sdk so the "
        "packaging helper vendors the SDK into the asset (the handler is a thin "
        f"re-export); non-comment lines were: {lines!r}"
    )
