"""Where an entity appears: the documents that link to it, and the diagrams that draw it.

The document half was served all along; the diagram half was not, although the index has kept the
reverse mapping for as long as the delete path has needed it to say which diagrams block a deletion.
So the gap was never in the model or the index — it was a facade with no way through to a question its
store already answers, and a page that therefore told half the story.

Two things are asserted here that the feature would otherwise be free to get wrong:

* **The delegation is the indexed lookup**, not a scan of every diagram reading each one's references.
  `CLAUDE.md` names this case exactly: a facade missing a method is filled in at the facade, never
  routed around with a less efficient call that happens to return equivalent data.
* **Both halves come from one place.** They were assembled at two call sites in two copies, and a
  second field would have made four. A reader wants "where does this appear", not two lists that can
  drift into disagreeing about the same entity.
"""

from __future__ import annotations

from pathlib import Path

from src.application.artifacts.entity_references import diagram_reference_dicts, references_to
from src.domain.ontology_representation.artifact_types import DiagramRecord, EntityRecord


def _entity(artifact_id: str = "APP@1") -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type="application-component",
        name="Alpha",
        version="0.1.0",
        status="active",
        domain="application",
        subdomain="",
        path=Path("e.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label="Alpha",
        display_alias="APP1",
        specializations=(),
        attributes={},
    )


def _diagram(slug: str, name: str, *, status: str = "active") -> DiagramRecord:
    return DiagramRecord(
        artifact_id=f"ARC@1.x.{slug}",
        artifact_type="diagram",
        name=name,
        version="0.1.0",
        status=status,
        diagram_type="archimate-layered",
        path=Path(f"{slug}.puml"),
        extra={},
    )


class _Source:
    """A source that records how it was asked, so the *manner* of the answer can be asserted."""

    def __init__(self, diagrams: list[DiagramRecord]) -> None:
        self._diagrams = diagrams
        self.asked_for: list[str] = []
        self.listed_diagrams = 0

    def list_documents(self, **_kwargs: object) -> list:
        return []

    def list_diagrams(self, **_kwargs: object) -> list[DiagramRecord]:
        self.listed_diagrams += 1
        return self._diagrams

    def diagrams_referencing_artifact(self, artifact_id: str) -> list[DiagramRecord]:
        self.asked_for.append(artifact_id)
        return self._diagrams


class TestHowTheQuestionIsAsked:
    def test_the_diagrams_are_looked_up_by_the_entity_rather_than_scanned_for(self) -> None:
        """The reverse index answers this directly. Listing every diagram and reading each one's
        recorded references would return the same rows and get slower with the repository."""
        source = _Source([_diagram("a", "A Map")])

        references_to(_entity("APP@7"), source)

        assert source.asked_for == ["APP@7"]
        assert source.listed_diagrams == 0

    def test_both_halves_come_back_from_the_one_call(self) -> None:
        found = references_to(_entity(), _Source([_diagram("a", "A Map")]))

        assert set(found) == {"referenced_in_documents", "referenced_in_diagrams"}


class TestWhatADiagramRowCarries:
    def test_a_row_names_the_diagram_rather_than_only_identifying_it(self) -> None:
        """A reader choosing between two diagrams chooses by name; a list of ids would make them open
        both to find out which they meant."""
        rows = diagram_reference_dicts([_diagram("investment", "Resource Investment Map")])

        assert rows == [{
            "artifact_id": "ARC@1.x.investment",
            "name": "Resource Investment Map",
            "diagram_type": "archimate-layered",
            "status": "active",
        }]

    def test_a_draft_diagram_says_so(self) -> None:
        """A draft drawing an entity is a weaker statement than an active one, and a reader weighing
        "where is this used" needs to be able to tell."""
        rows = diagram_reference_dicts([_diagram("d", "Draft Map", status="draft")])

        assert rows[0]["status"] == "draft"

    def test_the_rows_are_ordered_by_name(self) -> None:
        """A list that reorders between reads is a list a reader cannot scan twice."""
        rows = diagram_reference_dicts([
            _diagram("z", "zebra map"), _diagram("a", "Alpha map"), _diagram("m", "middle map"),
        ])

        assert [row["name"] for row in rows] == ["Alpha map", "middle map", "zebra map"]

    def test_drawing_nothing_is_an_empty_list_rather_than_an_absence(self) -> None:
        assert diagram_reference_dicts([]) == []
