"""D17 coverage invariant: every `ScannedSurface` this plan introduced must have at least
one registered step or read-only detector — enforced here rather than left as a manual
inventory, so a future format surface added without a step fails a test instead of silently
lacking coverage.

`REQUIRED_STEP_IDS_BY_SURFACE` is keyed by every `ScannedSurface` literal
(`typing.get_args`-derived, so a new literal with no entry here is itself a coverage gap).
"""

from __future__ import annotations

from typing import get_args

from src.application.repository_upgrade.registry import StepRegistry
from src.domain.repository.repository_upgrade import ScannedSurface

REQUIRED_STEP_IDS_BY_SURFACE: dict[ScannedSurface, tuple[str, ...]] = {
    "profiles": ("schema-file-scan", "default-schemata-ensure"),
    "customizations": ("specialization-declaration-scan", "viewpoint-declaration-scan"),
    "entity_frontmatter": ("unrecognized-structure-scan",),
    "connection_declarations": ("connection-metadata-scan",),
    "diagram_frontmatter": ("d9-multiplicity-rename", "viewpoint-application-scan"),
    "group_registry": ("group-meta-ontology-archimate-4-rename",),
    "modification_stamps": ("modification-stamp-datetime",),
}


def missing_step_coverage(registry: StepRegistry) -> tuple[str, ...]:
    """Return one message per (surface, required step id) pair not satisfied by *registry*.

    Empty means every declared `ScannedSurface` has its required steps registered.
    """
    registered_ids = {step.id for step in registry.steps()}
    gaps: list[str] = []
    for surface in get_args(ScannedSurface):
        required = REQUIRED_STEP_IDS_BY_SURFACE.get(surface, ())
        if not required:
            gaps.append(f"surface {surface!r} has no required step(s) registered in REQUIRED_STEP_IDS_BY_SURFACE")
            continue
        for step_id in required:
            if step_id not in registered_ids:
                gaps.append(f"surface {surface!r}: required step {step_id!r} is not registered")
    return tuple(gaps)
