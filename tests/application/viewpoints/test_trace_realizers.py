"""The eligible-realizer set is registry-derived: it includes implementation-family types
permitted to realize a requirement and excludes motivation refiners + structural helpers."""

from __future__ import annotations

from src.application.viewpoints.trace_realizers import eligible_realizer_types
from src.infrastructure.app_bootstrap import get_module_registry


def _eligible() -> frozenset[str]:
    return eligible_realizer_types(get_module_registry())


class TestEligibleRealizerSet:
    def test_includes_implementation_family_realizers(self) -> None:
        eligible = _eligible()
        # Types the ArchiMate ontology permits as incoming realization sources of a requirement.
        assert {"application-component", "business-process", "capability"} & eligible

    def test_excludes_motivation_refiners(self) -> None:
        eligible = _eligible()
        for refiner in ("goal", "outcome", "requirement", "principle", "driver"):
            assert refiner not in eligible

    def test_excludes_structural_helpers(self) -> None:
        eligible = _eligible()
        for helper in ("and-junction", "or-junction", "grouping"):
            assert helper not in eligible

    def test_is_nonempty_and_immutable(self) -> None:
        eligible = _eligible()
        assert eligible
        assert isinstance(eligible, frozenset)
