"""A naive candidate scoped by a diagram reads over the entities that diagram draws, each once."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.infrastructure.candidates import service as candidate_service
from tests.support.typed_table_documents import repository_in

ENTITY = "ROL@1000000001.archit.architect"
OTHER = "ROL@1000000002.develo.developer"


def test_an_entity_drawn_twice_is_scoped_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: a diagram drawing one role in two teams refused the candidate as naming it twice."""
    root = repository_in(tmp_path)
    service = candidate_service.CandidateService(root)
    monkeypatch.setattr(service.index, "get_diagram", lambda _: SimpleNamespace(extra={}))
    occurrences = [SimpleNamespace(artifact_id=ref) for ref in (ENTITY, OTHER, ENTITY)]
    monkeypatch.setattr(candidate_service, "resolve_placed_entities", lambda *_: occurrences)

    created = service.create({"name": "Naive architecture"}, diagram="ARC@1000000003.diagra.diagram")

    assert created["record"]["scope"] == [ENTITY, OTHER]
