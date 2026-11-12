"""A diagram whose type no module here describes is refreshed from its stored state, never reconciled.

A repository outlives a deployment's module set: without the confidential store the assurance family
(bow-tie, control structure, …) is not registered, yet its diagrams are still in the repository. Since
0.11.1 the refresh asked "is this diagram rendered from its records?" of the diagram's type; an
unregistered type could not answer, so its diagrams fell through to the ArchiMate model reconcile,
which asked for the type strictly and raised — 104 errors in CI, where the pytest job has no store.

The refresh now asks the verifier's question, `diagram_body_is_reconcile_owned`, of the same owner: only
a type the catalog knows to be reconciled from the model is reconciled. The type below is one no module
will ever register, so this holds whatever order the tests build the module registry in.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.verification._verifier_rules_puml_completeness import diagram_body_is_reconcile_owned
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.mcp import mcp_artifact_server as mcp

DIAGRAM_ID = "BOW@1700000000.UnrAbc.drawn-elsewhere"
DIAGRAM = """\
---
artifact-id: {diagram_id}
artifact-type: diagram
name: "Drawn elsewhere"
diagram-type: a-type-no-module-provides
version: 0.1.0
status: draft
last-updated: '2026-11-12'
entity-ids-used: [{member}]
connection-ids-used: []
diagram-entities:
  nodes:
    - node_id: t1
      name: A threat
---
@startuml drawn-elsewhere
rectangle "A threat" as t1
@enduml
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-UNREG" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    diagram = root / "diagram-catalog" / "diagrams" / f"{DIAGRAM_ID}.puml"
    diagram.parent.mkdir(parents=True)
    # A member the model resolves: with none, the reconcile preserves the diagram before it renders,
    # and the failure this guards against happens only once it renders.
    member = mcp.artifact_create_entity(
        artifact_type="goal", name="A goal", summary="Summary", dry_run=False, repo_root=str(root),
    )["artifact_id"]
    diagram.write_text(DIAGRAM.format(diagram_id=DIAGRAM_ID, member=member), encoding="utf-8")
    return root


def test_an_unregistered_type_is_not_reconcile_owned() -> None:
    fm = {"diagram-type": "a-type-no-module-provides", "diagram-entities": {}}
    assert diagram_body_is_reconcile_owned(fm, process_runtime_catalogs().diagram_types) is False


def test_refreshing_it_keeps_its_stored_state_instead_of_raising(repo: Path) -> None:
    refreshed = mcp.artifact_edit_diagram(
        artifact_id=DIAGRAM_ID, puml="auto-sync", dry_run=True, repo_root=str(repo),
    )

    assert refreshed["deleted_diagram"] is False
    assert refreshed["removed_entity_ids"] == [] and refreshed["removed_connection_ids"] == []
