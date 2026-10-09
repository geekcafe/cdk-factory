"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.

Helpers for building cross-platform (Linux-correct) pip install commands for
Lambda packaging. The AWS Lambda Python runtime executes on Linux, so native
wheels must target manylinux regardless of the build host (a developer's Mac or
a Linux CodeBuild runner). These helpers derive the pip ``--platform`` tag and
``--python-version`` generically from the configured Lambda runtime/architecture
so nothing is hardcoded to a single app.
"""

from __future__ import annotations

from typing import Tuple

from aws_cdk import aws_lambda


# Default manylinux family used for the pip --platform tag. Overridable so a
# caller can raise it (e.g. manylinux_2_28) via config in the future.
DEFAULT_MANYLINUX_FAMILY = "manylinux2014"

# Map a Lambda architecture name to the pip platform-tag arch suffix.
_ARCH_TO_PIP_SUFFIX = {
    "x86_64": "x86_64",
    "arm64": "aarch64",
}


def python_version_from_runtime(runtime: aws_lambda.Runtime) -> str:
    """Return the bare python version (e.g. ``3.12``) from a Lambda runtime.

    Derived from ``runtime.name`` (``python3.12``) by stripping the ``python``
    prefix. Raises ``ValueError`` for a non-python runtime so the caller fails
    loudly rather than building a nonsensical pip command.
    """
    name = runtime.name
    if not name or not name.lower().startswith("python"):
        raise ValueError(
            f"Cannot derive a python version from non-python runtime '{name}'. "
            "Cross-platform pip packaging only supports python runtimes."
        )
    return name[len("python"):]


def platform_tag_from_architecture(
    architecture: aws_lambda.Architecture,
    manylinux_family: str = DEFAULT_MANYLINUX_FAMILY,
) -> str:
    """Return the pip ``--platform`` tag for a Lambda architecture.

    e.g. ``x86_64`` -> ``manylinux2014_x86_64``;
         ``arm64``  -> ``manylinux2014_aarch64``.
    """
    arch_name = architecture.name
    suffix = _ARCH_TO_PIP_SUFFIX.get(arch_name.lower())
    if suffix is None:
        raise ValueError(
            f"Unsupported Lambda architecture '{arch_name}' for cross-platform "
            f"pip packaging. Known: {sorted(_ARCH_TO_PIP_SUFFIX)}."
        )
    return f"{manylinux_family}_{suffix}"


def resolve_pip_target_platform(
    runtime: aws_lambda.Runtime,
    architecture: aws_lambda.Architecture,
    manylinux_family: str = DEFAULT_MANYLINUX_FAMILY,
) -> Tuple[str, str]:
    """Return ``(python_version, platform_tag)`` for the configured Lambda.

    Both values are derived generically from the runtime/architecture config so
    the pip command targets the Linux runtime the Lambda actually executes on,
    regardless of the build host OS/python.
    """
    return (
        python_version_from_runtime(runtime),
        platform_tag_from_architecture(architecture, manylinux_family),
    )
