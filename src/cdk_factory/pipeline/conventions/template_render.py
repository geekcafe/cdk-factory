"""Template rendering utility for pipeline configuration strings.

Substitutes ``{{PLACEHOLDER}}`` patterns in template strings using
values from a context dictionary.  Placeholders whose keys are not
present in the context are left unchanged.
"""

from __future__ import annotations

from typing import Any, Dict


def render_template(template: str, context: Dict[str, Any]) -> str:
    """Replace ``{{KEY}}`` placeholders in *template* with values from *context*.

    Keys present in *context* are substituted (values are converted to
    ``str``); placeholders whose keys are absent remain in the output
    unchanged.

    Args:
        template: A string potentially containing ``{{KEY}}`` patterns.
        context: A mapping of placeholder names to replacement values.

    Returns:
        The rendered string with matched placeholders replaced.
    """
    rendered = template
    for key, value in context.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
    return rendered
