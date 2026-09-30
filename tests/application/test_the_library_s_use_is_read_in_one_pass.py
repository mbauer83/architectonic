"""Who uses each library icon, and what each element is shown with, from one reading of the diagrams."""

from __future__ import annotations

from pathlib import Path

from src.application.icons.icon_usage import icon_users, library_usage
from src.domain.ontology_representation.artifact_types import DiagramRecord
from src.domain.ontology_representation.specializations import SpecializationCatalog

MARK = "ICO@1790000000.mark01.mark"
OTHER = "ICO@1790000001.oth001.other"
NODE = "NOD@1790000002.node01.cluster"


def _diagram(artifact_id: str, name: str, entities: dict[str, object]) -> DiagramRecord:
    return DiagramRecord(
        artifact_id=artifact_id, artifact_type="diagram", name=name, diagram_type="archimate-technology",
        version="0.1.0", status="draft", path=Path(f"{artifact_id}.puml"), extra={"diagram-entities": entities},
    )


DIAGRAMS = (
    _diagram("ARC@2.b.second", "Second", {"type_icons": {"technology-node": MARK}}),
    _diagram("ARC@1.a.first", "First", {"display_icons": {NODE: MARK, "OCC-1": "local:logo"}}),
    _diagram("ARC@3.c.third", "Third", {"display_icons": {"NOD@1790000002.node01.renamed": OTHER}}),
)


def test_every_diagram_naming_an_icon_is_a_user_at_either_level() -> None:
    users = library_usage(DIAGRAMS, SpecializationCatalog.empty()).users_of(MARK)

    assert users.diagrams == ("ARC@1.a.first", "ARC@2.b.second")
    assert [d.name for d in users.named_diagrams] == ["First", "Second"]


def test_the_single_icon_question_is_the_same_reading() -> None:
    assert icon_users(MARK, DIAGRAMS, SpecializationCatalog.empty()) == library_usage(
        DIAGRAMS, SpecializationCatalog.empty()
    ).users_of(MARK)


def test_an_element_is_shown_with_what_any_diagram_states_for_it_under_any_of_its_names() -> None:
    usage = library_usage(DIAGRAMS, SpecializationCatalog.empty())

    assert usage.shown_for(NODE) == {"ICO@1790000000.mark01", "ICO@1790000001.oth001"}
    assert usage.shown_for("technology-node") == frozenset()


def test_a_diagram_s_own_icon_is_no_one_s_library_use() -> None:
    usage = library_usage(DIAGRAMS, SpecializationCatalog.empty())

    assert usage.shown_for("OCC-1") == frozenset()
