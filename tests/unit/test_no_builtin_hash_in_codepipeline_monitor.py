"""
Deterministic-construct-id guard for the codepipeline_monitor module (FEAT-001).

Mirrors the intent of test_appsync_events_stack.py's
``test_no_builtin_hash_in_appsync_events_stack_source``: the builtin ``hash()``
is randomized per process (``PYTHONHASHSEED``), so using it in a construct id
produces a different CloudFormation logical id on every synth. Construct ids in
this module must be explicit slugged strings (and ``hashlib`` if a suffix is ever
needed), never the builtin ``hash``.

This scan asserts no builtin ``hash(`` call appears in the module source. It
deliberately allows ``hashlib`` (``hashlib.sha1(`` etc.) since the pattern
requires an opening paren immediately after ``hash``.
"""

import re
from pathlib import Path


def test_no_builtin_hash_in_codepipeline_monitor_source():
    stack_dir = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "cdk_factory"
        / "stack_library"
        / "codepipeline_monitor"
    )
    config_file = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "cdk_factory"
        / "configurations"
        / "resources"
        / "codepipeline_monitor.py"
    )

    files = list(stack_dir.glob("*.py")) + [config_file]
    assert files, "no codepipeline_monitor source files found to scan"

    # Match a builtin hash( call but not hashlib.<...> — i.e. 'hash' immediately
    # followed by '(' and not preceded by 'lib'.
    builtin_hash = re.compile(r"(?<!lib)\bhash\(")
    for py in files:
        text = py.read_text(encoding="utf-8")
        assert not builtin_hash.search(text), f"builtin hash( found in {py}"
