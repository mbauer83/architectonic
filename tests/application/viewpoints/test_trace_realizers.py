"""The eligible-realizer set is registry-derived: it includes implementation-family types
permitted to realize a requirement and excludes motivation refiners + structural helpers."""

from __future__ import annotations

from src.application.viewpoints.trace_realizers import eligible_realizer_types, structural_helper_types
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


class TestStructuralHelpersComeFromTheRules:
    """The exclusion is the ontology's statement, not this layer's list.

    A rule that names a type or class as the intermediate it derives *through* is saying that type
    stands for something else — which is exactly the reason it cannot be a realizer. Reading it back
    keeps one fact in one place: `RJ3` names the junction class, `PDR12` names the grouping.
    """

    def test_the_declared_intermediates_are_recognised(self) -> None:
        helpers = structural_helper_types(get_module_registry())

        assert {"and-junction", "or-junction", "grouping"} <= helpers

    def test_the_set_is_not_silently_empty(self) -> None:
        """An empty set would exclude nothing and read as "no helpers exist" — the failure mode of a
        derived value whose source moved."""
        assert structural_helper_types(get_module_registry())

    def test_an_ordinary_realizer_is_not_a_helper(self) -> None:
        helpers = structural_helper_types(get_module_registry())

        assert not ({"application-component", "business-process", "capability"} & helpers)
