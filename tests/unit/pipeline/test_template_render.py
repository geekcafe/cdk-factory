"""Unit tests for cdk_factory.pipeline.conventions.template_render."""

from cdk_factory.pipeline.conventions.template_render import render_template


def test_render_template_replaces_double_brace_tokens() -> None:
    """Matched placeholders are replaced with context values."""
    result = render_template("/{{ENV}}/{{NAME}}", {"ENV": "dev", "NAME": "svc"})
    assert result == "/dev/svc"


def test_render_template_leaves_unmatched_placeholders() -> None:
    """Placeholders not in context remain unchanged."""
    result = render_template("{{FOUND}}-{{MISSING}}", {"FOUND": "yes"})
    assert result == "yes-{{MISSING}}"


def test_render_template_empty_context() -> None:
    """An empty context leaves all placeholders unchanged."""
    template = "{{A}}/{{B}}"
    assert render_template(template, {}) == template


def test_render_template_no_placeholders() -> None:
    """A template without placeholders is returned as-is."""
    assert render_template("plain text", {"KEY": "val"}) == "plain text"


def test_render_template_non_string_values_converted() -> None:
    """Non-string context values are converted via str()."""
    result = render_template("port={{PORT}}", {"PORT": 8080})
    assert result == "port=8080"


def test_render_template_empty_string_value() -> None:
    """An empty string value replaces the placeholder with nothing."""
    result = render_template("prefix-{{MID}}-suffix", {"MID": ""})
    assert result == "prefix--suffix"
