"""The facade delegates the reverse-reference lookup its store already answers.

A regression test in the shape `CLAUDE.md` asks for: the facade was missing this method, and the only
other way to the answer was to list every diagram and read each one's recorded references — a
different, less efficient call returning equivalent data, which is the workaround the rule names. The
verifier's registry has delegated it all along, which is how the delete path can say which diagrams
block a deletion; the entity page could not say the same thing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.application.artifacts.repository import ArtifactRepository
from src.domain.ontology_representation.artifact_types import DiagramRecord


class _Store:
    def __init__(self) -> None:
        self.asked: list[str] = []

    def diagrams_referencing_artifact(self, artifact_id: str) -> list[DiagramRecord]:
        self.asked.append(artifact_id)
        return [
            DiagramRecord(
                artifact_id="ARC@1.x.map",
                artifact_type="diagram",
                name="Map",
                version="0.1.0",
                status="active",
                diagram_type="archimate-layered",
                path=Path("map.puml"),
                extra={},
            )
        ]

    def __getattr__(self, name: str) -> Any:  # pragma: no cover - the facade asks nothing else here
        raise AttributeError(name)


def test_the_facade_passes_the_question_straight_through() -> None:
    store = _Store()

    found = ArtifactRepository(store).diagrams_referencing_artifact("APP@1")  # type: ignore[arg-type]

    assert store.asked == ["APP@1"]
    assert [record.artifact_id for record in found] == ["ARC@1.x.map"]


def test_the_facade_does_not_reach_for_the_diagram_list_instead() -> None:
    """The store's own `list_diagrams` is never touched: the reverse index is the answer, and reading
    every diagram's references to rebuild it is the shape of workaround this delegation replaced."""
    store = _Store()

    ArtifactRepository(store).diagrams_referencing_artifact("APP@1")  # type: ignore[arg-type]

    assert not hasattr(store, "listed")
