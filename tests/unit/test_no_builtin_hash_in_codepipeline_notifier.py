"""
Deterministic-construct-id guard for the codepipeline_notifier module (FEAT-002).

Mirrors test_no_builtin_hash_in_codepipeline_monitor.py: the builtin ``hash()``
is randomized per process (``PYTHONHASHSEED``), so using it in a construct id
produces a different CloudFormation logical id on every synth. Construct ids in
this module must be explicit slugged strings (and ``hashlib`` if a suffix is ever
needed), never the builtin ``hash``.

Also asserts the SSM-export fallback literal in the stack source is exactly
``codepipeline-notifier`` (NOT the monitor module's ``codepipeline-monitor`` — a
copy-paste of the old literal is a defect; design §6.2 step 7 / §11 test 11).
"""

import re
from pathlib import Path


_STACK_DIR = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "cdk_factory"
    / "stack_library"
    / "codepipeline_notifier"
)
_CONFIG_FILE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "cdk_factory"
    / "configurations"
    / "resources"
    / "codepipeline_notifier.py"
)


def test_no_builtin_hash_in_codepipeline_notifier_source():
    files = list(_STACK_DIR.glob("*.py")) + [_CONFIG_FILE]
    assert files, "no codepipeline_notifier source files found to scan"

    # Match a builtin hash( call but not hashlib.<...> — 'hash' immediately
    # followed by '(' and not preceded by 'lib'.
    builtin_hash = re.compile(r"(?<!lib)\bhash\(")
    for py in files:
        text = py.read_text(encoding="utf-8")
        assert not builtin_hash.search(text), f"builtin hash( found in {py}"


def test_ssm_fallback_literal_is_codepipeline_notifier():
    stack_file = _STACK_DIR / "codepipeline_notifier_stack.py"
    text = stack_file.read_text(encoding="utf-8")
    assert "codepipeline-notifier" in text
    # The fallback must not reuse the monitor module's literal.
    assert "codepipeline-monitor" not in text
