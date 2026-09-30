"""An editor is told the icon each instance shows, classified by its entity or by the list hosting it."""

from __future__ import annotations

from pathlib import Path

from src.application.icons.shown_icons import EditedInstance, shown_icons
from src.domain.icons.applicability import applicability_from
from src.domain.icons.icon_ref import IconTarget, SharedIcon
from src.domain.icons.resolved_icon import ResolvedIcon
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.ontology_representation.specializations import (
    SpecializationCatalog,
    SpecializationInfo,
    SpecializationNotation,
)

CLUSTER = "NOD@1790000002.clu001.cluster"
OCCURRENCE = "OCC@1790000004.occ001"
MARK, DEFAULT = "ICO@1.mark01", "ICO@1.dflt01"


def _entity(artifact_id: str) -> EntityRecord | None:
    if artifact_id != CLUSTER:
        return None
    return EntityRecord(
        artifact_id=CLUSTER, artifact_type="technology-node", name="Cluster", version="0.1.0", status="draft",
        domain="technology", subdomain="", path=Path("c.md"), keywords=(), extra={}, content_text="",
        display_blocks={}, display_label="Cluster", display_alias="NOD_clu001", specializations=("kubernetes-cluster",),
    )


def _source(target: IconTarget) -> ResolvedIcon | None:
    if not isinstance(target, SharedIcon):
        return None
    return ResolvedIcon(b"png", target.icon_id, 64, 64, applicability_from(()), "badge")


SPECS = SpecializationCatalog((SpecializationInfo(
    slug="kubernetes-cluster", name="Kubernetes cluster", concept_kind="entity", parent_type="technology-node",
    module_alias="archimate-4", notation=SpecializationNotation(icon=DEFAULT),
),))


def test_an_occurrence_is_classified_by_the_entity_it_draws() -> None:
    entities = {"type_icons": {"kubernetes-cluster": MARK}}

    shown = shown_icons(entities, [EditedInstance(OCCURRENCE, CLUSTER)], _entity, _source, SPECS)

    assert shown[OCCURRENCE].target == SharedIcon(MARK) and shown[OCCURRENCE].level == "type"


def test_with_no_statement_the_specialization_default_is_shown() -> None:
    shown = shown_icons({}, [EditedInstance(CLUSTER)], _entity, _source, SPECS)

    assert shown[CLUSTER].target == SharedIcon(DEFAULT) and shown[CLUSTER].level == "specialization-default"


def test_an_instance_nothing_classifies_shows_its_glyph() -> None:
    assert shown_icons({"type_icons": {"node": MARK}}, [EditedInstance("x")], _entity, _source, SPECS) == {}


def test_an_instance_drawn_as_a_type_of_the_diagrams_own_is_reached_by_that_type() -> None:
    """A C4 container drawn for a model entity: a statement keyed `container` reaches it, as the renderer's does."""
    shown = shown_icons(
        {"type_icons": {"container": MARK}}, [EditedInstance(CLUSTER)], _entity, _source, SPECS,
        drawn_as={CLUSTER: "container"},
    )

    assert shown[CLUSTER].target == SharedIcon(MARK) and shown[CLUSTER].level == "type"
