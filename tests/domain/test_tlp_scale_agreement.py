"""The declared TLP scale and the exposure order must agree — and stay separate.

TLP is now declared ordinal in the shipped schemata so a query can ask for "more sensitive
than". That introduces a second written statement of an order the exposure policy already
depends on, and two statements of one order is how they come to disagree. This asserts they
agree, by reading both.

It also asserts they stay independent. Exposure is a security decision: which records leave the
store is decided by `TLP_ORDER` in the domain, never by a schema file an operator can edit. The
declaration exists to make TLP sortable, not to become the authority for withholding content.
"""

from __future__ import annotations

from src.domain.assurance.classification import TLP_ORDER
from src.domain.ontology_representation.attribute_scales import ORDINAL_KIND, declares_ordinal
from src.domain.repository.repo_default_assurance_schemata import ASSURANCE_ATTRIBUTE_SCHEMATA


def _tlp_properties() -> list[tuple[str, dict]]:
    found: list[tuple[str, dict]] = []
    for filename, schema in ASSURANCE_ATTRIBUTE_SCHEMATA.items():
        prop = schema.get("properties", {}).get("tlp")
        if isinstance(prop, dict):
            found.append((filename, prop))
    return found


class TestTheDeclaredScaleMatchesTheExposureOrder:
    def test_at_least_one_schema_declares_tlp(self) -> None:
        """Guards the rest of this file against passing vacuously."""
        assert _tlp_properties(), "no shipped schema declares a tlp attribute"

    def test_every_declared_tlp_enum_is_in_exposure_order(self) -> None:
        for filename, prop in _tlp_properties():
            assert tuple(prop.get("enum") or ()) == TLP_ORDER, (
                f"{filename} declares TLP in an order that differs from the exposure order; "
                "ranking would then disagree with which records are withheld"
            )

    def test_every_declared_tlp_enum_is_ranked(self) -> None:
        for filename, prop in _tlp_properties():
            assert declares_ordinal(prop), f"{filename} declares TLP without a rank, so it sorts alphabetically"


class TestExposureRemainsIndependentOfTheSchema:
    def test_the_exposure_order_is_a_domain_constant(self) -> None:
        """Read from the domain, not resolved from a schema file: an operator editing a schema
        must not be able to change who may see what."""
        assert TLP_ORDER == ("TLP:WHITE", "TLP:GREEN", "TLP:AMBER", "TLP:RED")

    def test_the_exposure_policy_does_not_consult_declared_scales(self) -> None:
        import inspect

        from src.application import assurance_exposure

        source = inspect.getsource(assurance_exposure)
        assert "x-scale" not in source
        assert ORDINAL_KIND not in source
        assert "attribute_scales" not in source
