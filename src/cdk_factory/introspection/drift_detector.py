"""Drift detection between generated and manually maintained service maps.

Compares the service keys in a generated service map (from
:meth:`AwsIntrospector.generate_service_map`) against a manually maintained
``workflow_service_map.json`` and reports the symmetric difference as drift
warnings.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class DriftReport:
    """Report of differences between generated and manual service maps.

    Attributes:
        in_generated_not_manual: Services present in the generated map
            but missing from the manual map.
        in_manual_not_generated: Services present in the manual map
            but missing from the generated map.
        has_drift: ``True`` if any drift was detected.
    """

    in_generated_not_manual: List[str] = field(default_factory=list)
    in_manual_not_generated: List[str] = field(default_factory=list)
    has_drift: bool = False


def detect_drift(
    generated_map: Dict[str, Any],
    manual_map: Dict[str, Any],
) -> DriftReport:
    """Compare generated service map against manually maintained one.

    Compares the service keys in both maps and reports the symmetric
    difference as drift warnings.

    Args:
        generated_map: Service map produced by
            :meth:`AwsIntrospector.generate_service_map`. Expected to
            have a ``"services"`` key containing a dict of service entries.
        manual_map: Manually maintained service map (e.g., loaded from
            ``configs/workflow_service_map.json``). Expected to have a
            ``"services"`` key containing a dict of service entries.

    Returns:
        A :class:`DriftReport` describing the differences.
    """
    generated_services = set(generated_map.get("services", {}).keys())
    manual_services = set(manual_map.get("services", {}).keys())

    in_generated_not_manual = sorted(generated_services - manual_services)
    in_manual_not_generated = sorted(manual_services - generated_services)

    has_drift = bool(in_generated_not_manual or in_manual_not_generated)

    return DriftReport(
        in_generated_not_manual=in_generated_not_manual,
        in_manual_not_generated=in_manual_not_generated,
        has_drift=has_drift,
    )
