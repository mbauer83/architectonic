"""A candidate is drawn only on a diagram whose type hosts candidates, and the catalogue serves which do.

Which diagrams a candidate may be drawn on was a `startsWith('archimate')` filter spelled in four GUI views,
and the server accepted any stored diagram, so an MCP caller could draw a candidate on a matrix or a C4
view. The diagram-type catalogue now says it (`hosts_candidates`), the candidate service refuses a diagram
whose type says no — however the candidate comes to be drawn on it — and `/api/diagram-types` serves the
answer the GUI filters by, beside whether a type draws an element again (`draws_occurrences`).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.candidates import service as candidate_service
from src.infrastructure.candidates.hosting import hosts_candidates
from src.infrastructure.rest.routers.diagrams.types import list_diagram_types
from tests.support.typed_table_documents import repository_in

_DIAGRAM = "ARC@1000000003.diagra.diagram"


def _service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, diagram_type: str) -> candidate_service.CandidateService:
    service = candidate_service.CandidateService(repository_in(tmp_path))
    monkeypatch.setattr(
        service.index, "get_diagram",
        lambda ref: SimpleNamespace(artifact_id=ref, extra={}, diagram_type=diagram_type),
    )
    monkeypatch.setattr(candidate_service, "resolve_placed_entities", lambda *_: [])
    return service


def test_the_catalogue_says_which_types_host_candidates() -> None:
    assert hosts_candidates("archimate-layered")
    assert hosts_candidates("archimate-application")
    assert not hosts_candidates("c4-container")
    assert not hosts_candidates("matrix")
    assert not hosts_candidates("no-such-type")


def test_a_candidate_is_created_on_a_diagram_whose_type_hosts_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = _service(tmp_path, monkeypatch, "archimate-layered").create({"name": "Lean", "diagram": _DIAGRAM})
    assert created["record"]["diagram"] == _DIAGRAM


def test_creating_one_on_another_type_is_refused_with_the_types_that_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match=r"c4-container diagram, which a candidate cannot be drawn on.*archimate-"):
        _service(tmp_path, monkeypatch, "c4-container").create({"name": "Lean", "diagram": _DIAGRAM})


def test_editing_one_onto_another_type_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service(tmp_path, monkeypatch, "archimate-layered")
    created = service.create({"name": "Lean"})
    monkeypatch.setattr(
        service.index, "get_diagram", lambda ref: SimpleNamespace(artifact_id=ref, extra={}, diagram_type="matrix"),
    )
    with pytest.raises(ValueError, match="matrix diagram"):
        service.edit(created["record"]["id"], created["version"], {"diagram": _DIAGRAM})


def test_comparing_one_on_another_type_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service(tmp_path, monkeypatch, "c4-container")
    created = service.create({"name": "Lean"})
    with pytest.raises(ValueError, match="c4-container diagram"):
        service.compare(created["record"]["id"], "model", None, _DIAGRAM, process_runtime_catalogs().ontology)


def test_the_type_list_serves_both_capabilities() -> None:
    listed = {row["key"]: row for row in list_diagram_types(process_runtime_catalogs())}
    assert listed["archimate-layered"]["hosts_candidates"] is True
    assert listed["archimate-layered"]["draws_occurrences"] is True
    assert listed["c4-container"]["hosts_candidates"] is False
    assert listed["c4-container"]["draws_occurrences"] is False
