"""A naive candidate scoped by a diagram reads over the entities that diagram draws, each once."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.domain.artifact_id import stable_id
from src.infrastructure.candidates import service as candidate_service
from tests.support.typed_table_documents import repository_in

ENTITY = "ROL@1000000001.archit.architect"
OTHER = "ROL@1000000002.develo.developer"


def test_an_entity_drawn_twice_is_scoped_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: a diagram drawing one role in two teams refused the candidate as naming it twice."""
    root = repository_in(tmp_path)
    service = candidate_service.CandidateService(root)
    monkeypatch.setattr(
        service.index, "get_diagram",
        lambda ref: SimpleNamespace(artifact_id=ref, extra={}, diagram_type="archimate-layered"),
    )
    occurrences = [SimpleNamespace(artifact_id=ref) for ref in (ENTITY, OTHER, ENTITY)]
    monkeypatch.setattr(candidate_service, "resolve_placed_entities", lambda *_: occurrences)

    created = service.create({"name": "Naive architecture", "diagram": "ARC@1000000003.diagra.diagram"})

    # Held by the stable id, as every operation names an entity (ADR: emitted ids use the short form).
    assert created["record"]["scope"] == [stable_id(ENTITY), stable_id(OTHER)]
