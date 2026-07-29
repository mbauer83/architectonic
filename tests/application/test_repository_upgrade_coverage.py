"""D17 coverage invariant test: every `ScannedSurface` must have its required step(s)
registered in `DEFAULT_REGISTRY`. Fails loudly (rather than silently passing) if a future
`ScannedSurface` literal is added with no matching `REQUIRED_STEP_IDS_BY_SURFACE` entry, or
if a required step id is ever removed/renamed without updating the map."""

from __future__ import annotations

from src.application.repository_upgrade.coverage import (
    REQUIRED_STEP_IDS_BY_SURFACE,
    missing_step_coverage,
)
from src.application.repository_upgrade.registry import DEFAULT_REGISTRY, StepRegistry


def test_default_registry_has_no_coverage_gaps() -> None:
    assert missing_step_coverage(DEFAULT_REGISTRY) == ()


def test_empty_registry_reports_a_gap_per_surface() -> None:
    gaps = missing_step_coverage(StepRegistry())

    assert len(gaps) == sum(len(ids) for ids in REQUIRED_STEP_IDS_BY_SURFACE.values())


def test_unmapped_surface_is_reported_even_with_a_full_registry() -> None:
    """A literal with no entry in REQUIRED_STEP_IDS_BY_SURFACE is a gap in the map itself —
    this is what protects against a future ScannedSurface literal being added and forgotten."""
    import src.application.repository_upgrade.coverage as coverage_module

    original = dict(coverage_module.REQUIRED_STEP_IDS_BY_SURFACE)
    coverage_module.REQUIRED_STEP_IDS_BY_SURFACE.pop("profiles")
    try:
        gaps = missing_step_coverage(DEFAULT_REGISTRY)
        assert any("'profiles'" in gap and "no required step" in gap for gap in gaps)
    finally:
        coverage_module.REQUIRED_STEP_IDS_BY_SURFACE.clear()
        coverage_module.REQUIRED_STEP_IDS_BY_SURFACE.update(original)
