"""The scratchpad's link verification, against the real ArchiMate ontology.

`test_scratchpad_link_verdict` covers the vocabulary with a toy ontology, which is where the many
cases belong. This covers the wiring, which is where the mistakes are: the argument order of
`permits`, the alias between the name a scratchpad writes (`archimate-4`) and the name the registry
keys on (`archimate-4-0`), and whether the narrowing tier appears at all.

Against real ontology content rather than a fixture, so it asserts the invariant rather than the
population: that a relation the ontology declares is permitted and its reverse is refused, not that
any particular count of relations exists.
"""

from __future__ import annotations

import pytest

from src.application.scratchpad.verification import (
    ontology_view,
    typing_options,
    verdict_for,
)
from src.domain.scratchpad import Endpoint


@pytest.fixture(scope="module")
def registry():
    from src.infrastructure.app_bootstrap import get_module_registry

    return get_module_registry()


def _element(element_type: str, specialization: str | None = None) -> Endpoint:
    return Endpoint(destination="element", element_type=element_type, specialization=specialization)


class TestFindingTheOntology:
    def test_the_name_a_scratchpad_writes_finds_the_module_the_registry_keys_on(self, registry) -> None:
        """A scratchpad says `archimate-4`; the registry says `archimate-4-0`. One spelling must
        not become a silent "this ontology does not exist"."""
        view = ontology_view(registry, "archimate-4")

        assert view.entity_types, "the alias did not resolve to a registered ontology"
        assert "goal" in view.entity_types

    def test_the_registry_s_own_name_works_too(self, registry) -> None:
        assert ontology_view(registry, "archimate-4-0").entity_types

    def test_an_unknown_meta_ontology_is_an_empty_view_rather_than_an_error(self, registry) -> None:
        """A scratchpad naming a vocabulary this workspace lacks is still readable; it simply
        cannot verify anything, which is what `unverified` already means."""
        view = ontology_view(registry, "no-such-ontology")

        assert view.entity_types == ()
        assert view.levels == ()


class TestTheTypingLadder:
    def test_it_offers_the_levels_the_ontology_declares_in_order(self, registry) -> None:
        levels = typing_options(registry, "archimate-4")

        assert [level.level_id for level in levels] == ["domain", "entity_type", "specialization"]

    def test_the_type_level_offers_the_ontology_s_entity_types(self, registry) -> None:
        by_id = {level.level_id: level for level in typing_options(registry, "archimate-4")}

        assert "requirement" in by_id["entity_type"].values
        assert by_id["entity_type"].required

    def test_the_specialization_level_is_offered_but_not_required(self, registry) -> None:
        by_id = {level.level_id: level for level in typing_options(registry, "archimate-4")}

        assert not by_id["specialization"].required


class TestVerifyingAgainstTheRealOntology:
    def _verdict(self, registry, source: str, target: str, conn: str | None):
        return verdict_for(
            registry, meta_ontology="archimate-4",
            source=_element(source), target=_element(target), connection_type=conn,
        )

    def test_a_declared_relation_is_permitted(self, registry) -> None:
        """A requirement realizes an outcome — the chain the motivation layer is built on."""
        verdict = self._verdict(registry, "requirement", "outcome", "archimate-realization")

        assert verdict.kind == "permitted", verdict.message

    def test_the_reverse_of_that_relation_is_refused(self, registry) -> None:
        """Regression for the argument-order trap: `permits` takes (source, target, connection),
        not the order the triple reads in. Passing them the reading way is silently always False,
        which would make *every* link refused and look like a working verifier."""
        verdict = self._verdict(registry, "outcome", "requirement", "archimate-realization")

        assert verdict.kind == "refused"
        assert verdict.code == "E126"
        assert verdict.reverse_permitted, "the remedy that leads should be 'reverse the link'"

    def test_both_ends_typed_without_a_connection_type_offers_what_is_permitted(self, registry) -> None:
        verdict = self._verdict(registry, "requirement", "outcome", None)

        assert "archimate-realization" in verdict.alternatives

    def test_an_undecided_end_stays_unverified(self, registry) -> None:
        verdict = verdict_for(
            registry, meta_ontology="archimate-4",
            source=_element("requirement"), target=Endpoint(), connection_type=None,
        )

        assert verdict.kind == "unverified"

    def test_an_element_to_document_link_is_a_reference(self, registry) -> None:
        verdict = verdict_for(
            registry, meta_ontology="archimate-4",
            source=_element("requirement"),
            target=Endpoint(destination="document", document_type="budget"),
            connection_type=None,
        )

        assert verdict.kind == "reference"

    def test_an_unknown_meta_ontology_verifies_nothing_rather_than_crashing(self, registry) -> None:
        verdict = verdict_for(
            registry, meta_ontology="no-such-ontology",
            source=_element("requirement"), target=_element("outcome"),
            connection_type="archimate-realization",
        )

        assert verdict.kind == "refused"


class TestTheNarrowingTierIsWiredToTheDeclaration:
    def test_archimate_declares_a_narrowing_level_so_the_probe_exists(self, registry) -> None:
        """The tier's presence is read off `classification_levels`, not assumed — which is what
        makes a meta-ontology without one produce one-tier verdicts and no stub."""
        from src.application.scratchpad.verification import _narrowing_probe

        module = registry.all_ontologies()["archimate-4-0"]

        assert _narrowing_probe(module) is not None

    def test_a_real_restriction_narrows_the_verdict(self, registry) -> None:
        """Regression, and the gap that let a broken probe pass.

        The first version guessed the restriction's field names — `connection_types` plural against
        a type that declares `connection_type` — so `getattr` returned empty, "empty means any"
        fired, and the narrowing tier never triggered on anything. Every test still passed, because
        none of them exercised a restriction that should bite. This one builds one and asserts it
        does, through the same shared predicate the verifier's own W128/W129 rules use.
        """
        from src.domain.ontology_representation.specializations import (
            RelationshipRestriction,
            SpecializationInfo,
            specialization_narrows,
        )

        # Allows realization only onto a goal; an outcome target is therefore outside it.
        info = SpecializationInfo(
            slug="goal-only",
            name="Goal only",
            concept_kind="entity",
            parent_type="requirement",
            module_alias="archimate-4-0",
            restrict_relationships=(
                RelationshipRestriction(connection_type="archimate-realization", target_type="goal"),
            ),
        )

        assert specialization_narrows(
            info, conn_type="archimate-realization", source_type="requirement", target_type="outcome"
        )
        assert not specialization_narrows(
            info, conn_type="archimate-realization", source_type="requirement", target_type="goal"
        )

    def test_declaring_no_restriction_narrows_nothing(self, registry) -> None:
        """An allow-list is only a restriction once it has an entry."""
        from src.domain.ontology_representation.specializations import (
            SpecializationInfo,
            specialization_narrows,
        )

        info = SpecializationInfo(
            slug="plain", name="Plain", concept_kind="entity", parent_type="requirement",
            module_alias="archimate-4-0",
        )

        assert not specialization_narrows(
            info, conn_type="archimate-realization", source_type="requirement", target_type="outcome"
        )

    def test_a_specialization_that_restricts_nothing_leaves_a_permitted_verdict_alone(
        self, registry
    ) -> None:
        verdict = verdict_for(
            registry, meta_ontology="archimate-4",
            source=_element("requirement", "no-such-specialization"),
            target=_element("outcome"), connection_type="archimate-realization",
        )

        assert verdict.kind == "permitted"
