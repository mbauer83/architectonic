"""A changed `applies-to` is judged by asking each use of the icon, not by comparing name sets (D12)."""

from __future__ import annotations

from pathlib import Path

from src.application.icons.icon_usage import uses_outside
from src.domain.icons.applicability import applicability_from
from src.domain.ontology_representation.artifact_types import DiagramRecord, EntityRecord
from src.domain.ontology_representation.specializations import (
    SpecializationCatalog,
    SpecializationInfo,
    SpecializationNotation,
)

ICON = "ICO@1790000001.mark01.mark"
CLUSTER = "NOD@1790000002.clu001.cluster"


def _diagram(entities: dict) -> DiagramRecord:
    return DiagramRecord(
        "ARC@1790000003.dia001.view", "diagram", "View", "archimate-technology", "0.1.0", "draft",
        Path("view.puml"), {"diagram-entities": entities},
    )


def _entity(artifact_id: str) -> EntityRecord | None:
    if artifact_id != CLUSTER:
        return None
    return EntityRecord(
        artifact_id=CLUSTER, artifact_type="technology-node", name="Cluster", version="0.1.0", status="draft",
        domain="technology", subdomain="", path=Path("c.md"), keywords=(), extra={}, content_text="",
        display_blocks={}, display_label="Cluster", display_alias="NOD_clu001",
        specializations=("kubernetes-cluster",),
    )


def _lost(applies_to: tuple[str, ...], entities: dict, specs: SpecializationCatalog | None = None) -> list[str]:
    catalog = specs or SpecializationCatalog.empty()
    return uses_outside(ICON, applicability_from(applies_to), [_diagram(entities)], catalog, _entity)


def test_a_type_covers_an_element_that_carries_one_of_its_specializations() -> None:
    assert _lost(("technology-node",), {"display_icons": {CLUSTER: ICON}}) == []
    assert _lost(("kubernetes-cluster",), {"display_icons": {CLUSTER: ICON}}) == []


def test_an_element_the_new_set_does_not_name_is_lost() -> None:
    assert _lost(("application-component",), {"display_icons": {CLUSTER: ICON}}) == [
        f"ARC@1790000003.dia001.view display_icons {CLUSTER}"
    ]


def test_a_type_key_is_judged_by_its_own_name() -> None:
    assert _lost(("kubernetes-cluster",), {"type_icons": {"technology-node": ICON}}) == [
        "ARC@1790000003.dia001.view type_icons technology-node"
    ]


def test_a_specialization_default_is_judged_by_the_specialization_and_its_type() -> None:
    spec = SpecializationInfo(
        slug="kubernetes-cluster", name="Kubernetes cluster", concept_kind="entity",
        parent_type="technology-node", module_alias="archimate-4", notation=SpecializationNotation(icon=ICON),
    )
    catalog = SpecializationCatalog((spec,))

    assert _lost(("technology-node",), {}, catalog) == []
    assert _lost(("application-component",), {}, catalog) == ["specialization default kubernetes-cluster"]
