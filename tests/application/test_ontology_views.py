"""What the meta-ontology declares, as a client receives it.

Two reads that replace hardcoding: how elements are drawn, and how they are classified. Both are
served as *data* — opaque string ids, values rather than types — because the requirement they exist
for is that a **different meta-ontology, declaring its own chain and its own palette, works with no
code changes**. Only one module declares classification levels today, so that requirement cannot be
proved against the shipped ontology: the proof needs a second declaration, which is what the
fixture below is.

A generated union over `archimate_4`'s level ids would satisfy every test written against
`archimate_4` and fail the requirement completely.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pytest

from src.application.ontology_views import (
    classification_levels_payload,
    element_appearance_payload,
)
from src.domain.ontology_representation.classification_levels import ClassificationLevel
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry


@dataclass(frozen=True)
class _FixtureCatalog:
    """An ontology catalog answering for a meta-ontology that is not ArchiMate.

    Its ladder has a different length, different ids and different labels, and it keys attributes
    at a different rung — so anything that hard-codes the shipped chain fails here.
    """

    levels: Mapping[str, Sequence[ClassificationLevel]]
    appearance: Mapping[str, Mapping[str, str]]
    corners: Mapping[str, str]
    rule: Mapping[str, str]

    def classification_levels(self) -> Mapping[str, Sequence[ClassificationLevel]]:
        return self.levels

    def domain_appearance(self) -> Mapping[str, Mapping[str, str]]:
        return self.appearance

    def corner_by_entity_type(self) -> Mapping[str, str]:
        return self.corners

    def de_emphasis_rule(self) -> Mapping[str, str]:
        return self.rule


def _other_meta_ontology() -> _FixtureCatalog:
    return _FixtureCatalog(
        levels={
            "flow-modelling-1": (
                ClassificationLevel(id="realm", label="Realm", source="hierarchy", required=True),
                ClassificationLevel(
                    id="stratum", label="Stratum", source="hierarchy", required=True,
                ),
                ClassificationLevel(
                    id="kind", label="Kind", source="type", required=True,
                    keys_relationships=True, carries_attributes=True,
                ),
            ),
        },
        appearance={"flux": {"fill": "#112233", "border": "#000000", "container": "#889099"}},
        corners={"eddy": "rounded"},
        rule={"toward": "#101010", "amount": "0.3"},
    )


def _shipped_catalog():
    return build_runtime_catalogs(get_module_registry()).ontology


class TestADifferentMetaOntologyNeedsNoCodeChange:
    def test_its_own_ladder_is_served_whole(self) -> None:
        payload = classification_levels_payload(
            _other_meta_ontology(), meta_ontology="flow-modelling-1"
        )

        assert [level["id"] for level in payload["entity"]] == ["realm", "stratum", "kind"]
        assert payload["meta_ontology"] == "flow-modelling-1"

    def test_naming_no_module_still_answers_without_this_view_knowing_any(self) -> None:
        """A caller that names none gets the first registered module. The view spells no
        meta-ontology's name: one that did could not serve a second."""
        payload = classification_levels_payload(_other_meta_ontology())

        assert payload["meta_ontology"] == "flow-modelling-1"

    def test_a_level_crosses_as_data_rather_than_as_a_type(self) -> None:
        """Every field a consumer needs is a value on the row: nothing requires knowing the id."""
        payload = classification_levels_payload(
            _other_meta_ontology(), meta_ontology="flow-modelling-1"
        )

        for level in payload["entity"]:
            assert set(level) == {
                "id", "label", "source", "required",
                "keys_relationships", "narrows_relationships", "carries_attributes",
            }
            assert isinstance(level["id"], str)

    def test_its_own_palette_is_served_whole(self) -> None:
        payload = element_appearance_payload(
            _other_meta_ontology(), meta_ontology="flow-modelling-1"
        )

        assert payload["domain_colors"] == {"flux": "#112233"}
        assert payload["corners"] == {"eddy": "rounded"}
        assert payload["de_emphasis"] == {"toward": "#101010", "amount": "0.3"}


class TestTheShippedOntologyAnswers:
    def test_the_entity_ladder_is_the_declared_one(self) -> None:
        payload = classification_levels_payload(_shipped_catalog())

        assert [level["id"] for level in payload["entity"]] == [
            "domain", "entity_type", "specialization",
        ]

    def test_the_relation_side_is_answered_too(self) -> None:
        """A client faceting a graph needs both, and a bare list would have to change shape when
        the relation chain becomes declared rather than derived."""
        payload = classification_levels_payload(_shipped_catalog())

        assert [level["id"] for level in payload["relation"]] == [
            "connection_type", "connection_specialization",
        ]

    @pytest.mark.parametrize("domain", ["motivation", "business", "application", "implementation"])
    def test_every_domain_carries_a_fill_a_border_and_a_container(self, domain: str) -> None:
        """All three from the one declared colour, so a consumer cannot take a fill from here and
        a border from a table of its own — which is what the three palettes let it do."""
        payload = element_appearance_payload(_shipped_catalog())

        for key in ("domain_colors", "domain_borders", "domain_containers"):
            assert payload[key].get(domain), f"{domain} has no {key}"

    def test_a_corner_is_answered_per_entity_type_not_per_class(self) -> None:
        """The class vocabulary stays inside the ontology; a renderer gets something drawable."""
        corners = element_appearance_payload(_shipped_catalog())["corners"]

        assert corners["driver"] == "diagonal"
        structural = next(name for name in ("application-component", "application_component") if name in corners)
        assert corners[structural] == "square"
        assert set(corners.values()) <= {"square", "rounded", "diagonal"}
