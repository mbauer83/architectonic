"""Regression tests for GUI entity listing across engagement and enterprise repos."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request

from src.application.artifact_query import ArtifactRepository
from src.domain.artifact_id import stable_id
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.routers import state as gui_state
from src.infrastructure.gui.routers.documents import read_document
from src.infrastructure.gui.routers.entity_listing import build_entity_list_rows


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _entity_md(artifact_id: str, name: str) -> str:
    rand = artifact_id.split(".")[1] if "." in artifact_id else "TEST"
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: requirement
name: "{name}"
version: 0.1.0
status: active
last-updated: '2026-04-20'
---

<!-- §content -->

## {name}

Test entity.

## Properties

| Attribute | Value |
|---|---|
| (none) | (none) |

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Requirement
label: "{name}"
alias: REQ_{rand}
```
"""


def _outgoing_md(source_entity: str, connections: list[tuple[str, str]]) -> str:
    sections = "\n".join(f"### {conn_type} → {target}\n" for conn_type, target in connections)
    return f"""\
---
source-entity: {source_entity}
version: 0.1.0
status: active
last-updated: '2026-04-20'
---

<!-- §connections -->

{sections}
"""


def _document_md(artifact_id: str, title: str) -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: document
doc-type: adr
title: "{title}"
version: 0.1.0
status: draft
last-updated: '2026-04-25'
---

# {title}

Document body.
"""


@pytest.fixture()
def engagement_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-TEST" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    return root


@pytest.fixture()
def enterprise_root(tmp_path: Path) -> Path:
    root = tmp_path / "enterprise-repository"
    (root / "model").mkdir(parents=True)
    return root


def _activity_diagram_md(diagram_id: str) -> str:
    return f"""\
---
artifact-id: {diagram_id}
artifact-type: diagram
name: "My Process"
diagram-type: activity
version: 0.1.0
status: draft
last-updated: '2026-05-09'
diagram-entities:
  swimlane:
    - id: sw-1
      label: Author
  action:
    - id: a1
      label: Submit Form
      lane_id: sw-1
---
@startuml my-process
title My Process
@enduml
"""


def test_entity_catalog_excludes_diagram_owned_entities(
    engagement_root: Path,
    enterprise_root: Path,
) -> None:
    """Diagram-owned entities (swimlane/action/…) must not surface in the /api/entities catalog.

    Regression: activity/sequence diagram-owned entities are indexed with a host_diagram_id
    so they are queryable in-diagram, but they are not standalone model entities. They had
    been leaking into the model-entity listing, whose types the frontend union rightly
    rejects (e.g. "action" is not a model entity type).
    """
    from typing import cast

    from src.infrastructure.app_bootstrap import install_module_registry
    from src.infrastructure.gui.routers.entities import list_entities
    from src.infrastructure.gui.routers.entity_search import get_entity_taxonomy

    model_req = "REQ@1000000000.EngAAA.eng-req"
    diagram_id = "ACT@1234567890.aBcDeF.my-process"
    _write(
        engagement_root / "model" / "motivation" / "requirement" / f"{model_req}.md",
        _entity_md(model_req, "Engagement Req"),
    )
    _write(
        engagement_root / "diagram-catalog" / "diagrams" / f"{diagram_id}.md",
        _activity_diagram_md(diagram_id),
    )

    repo = ArtifactRepository(shared_artifact_index([engagement_root, enterprise_root]))
    gui_state.init_state(repo, engagement_root, enterprise_root)

    # Sanity: the diagram-owned entities are indexed (queryable in-diagram) ...
    all_types = {e.artifact_type for e in repo.list_entities()}
    assert {"action", "swimlane"} <= all_types

    # ... but the catalog endpoint omits them.
    payload = list_entities(request=cast("Request", None), limit=2000, offset=0)
    catalog_types = {row["artifact_type"] for row in payload["items"]}
    catalog_ids = {row["artifact_id"] for row in payload["items"]}

    assert "requirement" in catalog_types
    assert "action" not in catalog_types
    assert "swimlane" not in catalog_types
    assert all("#action/" not in i and "#swimlane/" not in i for i in catalog_ids)

    app = FastAPI()
    install_module_registry(app)
    taxonomy = get_entity_taxonomy(request=cast("Request", SimpleNamespace(app=app)))
    taxonomy_types = {
        entry["name"]
        for domain in taxonomy["domains"]
        for entry in domain["types"]
    }
    assert "requirement" in taxonomy_types
    assert "action" not in taxonomy_types
    assert "swimlane" not in taxonomy_types


def test_global_scope_listing_survives_root_entities_without_specialization_parent(
    engagement_root: Path,
    enterprise_root: Path,
) -> None:
    global_req = "REQ@2000000000.GloAAA.global-req"
    engagement_req = "REQ@1000000000.EngAAA.eng-req"

    _write(
        enterprise_root / "model" / "motivation" / "requirement" / f"{global_req}.md",
        _entity_md(global_req, "Global Req"),
    )
    _write(
        engagement_root / "model" / "motivation" / "requirement" / f"{engagement_req}.md",
        _entity_md(engagement_req, "Engagement Req"),
    )

    gui_state.init_state(
        ArtifactRepository(shared_artifact_index([engagement_root, enterprise_root])),
        engagement_root,
        enterprise_root,
    )

    repo = ArtifactRepository(shared_artifact_index([engagement_root, enterprise_root]))
    gui_state.init_state(repo, engagement_root, enterprise_root)

    global_entities = [entity for entity in repo.list_entities() if gui_state.is_global(entity.path)]
    rows = build_entity_list_rows(global_entities[:1], repo)

    assert len(global_entities) == 1
    assert len(rows) == 1
    row = rows[0]
    assert row["artifact_id"] == global_req
    assert row["is_global"] is True
    assert "parent_entity_id" not in row
    assert "hierarchy_relation_type" not in row
    assert "hierarchy_depth" not in row
    assert "parent_specialization_id" not in row
    assert "specialization_depth" not in row


def test_connection_to_dict_resolves_live_endpoint_names(engagement_root: Path, enterprise_root: Path) -> None:
    src_id = "REQ@1000000000.SrcAAA.source-name"
    tgt_id = "REQ@1000000001.TgtAAA.target-name"
    _write(
        engagement_root / "model" / "motivation" / "requirement" / f"{src_id}.md",
        _entity_md(src_id, "Source Display Name"),
    )
    _write(
        engagement_root / "model" / "motivation" / "requirement" / f"{tgt_id}.md",
        _entity_md(tgt_id, "Target Display Name"),
    )
    _write(
        engagement_root / "model" / "motivation" / "requirement" / f"{src_id}.outgoing.md",
        _outgoing_md(src_id, [("archimate-association", tgt_id)]),
    )

    repo = ArtifactRepository(shared_artifact_index([engagement_root, enterprise_root]))
    gui_state.init_state(repo, engagement_root, enterprise_root)

    conn = repo.find_connections_for(src_id)[0]
    payload = gui_state.connection_to_dict(conn)

    assert payload["source_name"] == "Source Display Name"
    assert payload["target_name"] == "Target Display Name"


def test_entity_context_read_model_groups_connections_and_counts(
    engagement_root: Path,
    enterprise_root: Path,
) -> None:
    src_id = "REQ@1000000000.SrcAAA.source"
    tgt_id = "REQ@1000000001.TgtAAA.target"
    peer_id = "REQ@1000000002.PeerAA.peer"
    _write(engagement_root / "model" / "motivation" / "requirement" / f"{src_id}.md", _entity_md(src_id, "Source"))
    _write(engagement_root / "model" / "motivation" / "requirement" / f"{tgt_id}.md", _entity_md(tgt_id, "Target"))
    _write(engagement_root / "model" / "motivation" / "requirement" / f"{peer_id}.md", _entity_md(peer_id, "Peer"))
    _write(
        engagement_root / "model" / "motivation" / "requirement" / f"{src_id}.outgoing.md",
        _outgoing_md(src_id, [("archimate-association", tgt_id), ("archimate-flow", peer_id)]),
    )
    _write(
        engagement_root / "model" / "motivation" / "requirement" / f"{peer_id}.outgoing.md",
        _outgoing_md(peer_id, [("archimate-association", src_id)]),
    )

    repo = ArtifactRepository(shared_artifact_index([engagement_root, enterprise_root]))
    gui_state.init_state(repo, engagement_root, enterprise_root)

    payload = repo.read_entity_context(src_id)
    assert payload is not None

    assert payload["entity"]["artifact_id"] == src_id
    assert payload["counts"] == {"conn_in": 0, "conn_out": 1, "conn_sym": 2}
    assert [conn["artifact_id"] for conn in payload["connections"]["outbound"]] == [
        f"{stable_id(src_id)}---{stable_id(peer_id)}@@archimate-flow"
    ]
    assert payload["connections"]["inbound"] == []
    assert {conn["artifact_id"] for conn in payload["connections"]["symmetric"]} == {
        f"{stable_id(src_id)}---{stable_id(tgt_id)}@@archimate-association",
        f"{stable_id(peer_id)}---{stable_id(src_id)}@@archimate-association",
    }
    assert payload["generation"] >= 1
    assert payload["entity"]["specialization"] == ""
    assert all(conn["specialization"] == "" for conn in payload["connections"]["outbound"])


def test_clear_caches_applies_incremental_outgoing_changes(
    engagement_root: Path,
    enterprise_root: Path,
) -> None:
    src_id = "REQ@1000000000.SrcAAA.source"
    tgt_a = "REQ@1000000001.TgtAAA.target-a"
    tgt_b = "REQ@1000000002.TgtBBB.target-b"
    for artifact_id, name in ((src_id, "Source"), (tgt_a, "Target A"), (tgt_b, "Target B")):
        _write(
            engagement_root / "model" / "motivation" / "requirement" / f"{artifact_id}.md",
            _entity_md(artifact_id, name),
        )
    outgoing_path = engagement_root / "model" / "motivation" / "requirement" / f"{src_id}.outgoing.md"
    _write(outgoing_path, _outgoing_md(src_id, [("archimate-flow", tgt_a)]))

    repo = ArtifactRepository(shared_artifact_index([engagement_root, enterprise_root]))
    gui_state.init_state(repo, engagement_root, enterprise_root)

    before = repo.read_entity_context(src_id)
    assert before is not None
    assert before["counts"] == {"conn_in": 0, "conn_out": 1, "conn_sym": 0}

    _write(outgoing_path, _outgoing_md(src_id, [("archimate-flow", tgt_a), ("archimate-serving", tgt_b)]))
    gui_state.clear_caches(outgoing_path)

    after = repo.read_entity_context(src_id)
    assert after is not None
    assert after["counts"] == {"conn_in": 0, "conn_out": 2, "conn_sym": 0}
    assert after["generation"] > before["generation"]
    assert {conn["artifact_id"] for conn in after["connections"]["outbound"]} == {
        f"{stable_id(src_id)}---{stable_id(tgt_a)}@@archimate-flow",
        f"{stable_id(src_id)}---{stable_id(tgt_b)}@@archimate-serving",
    }


def test_entity_detail_view_uses_entity_context_request() -> None:
    view_path = Path("tools/gui/src/ui/views/EntityDetailView.vue")
    content = view_path.read_text(encoding="utf-8")

    assert "svc.getEntityContext(entityId.value)" in content
    assert "svc.getConnections(" not in content
    assert 'direction="symmetric"' in content
    assert 'v-if="hasSymmetric"' not in content
    assert ":class=\"{ 'has-symmetric': hasSymmetric }\"" not in content


def test_document_router_marks_global_documents(tmp_path: Path) -> None:
    engagement_root = tmp_path / "engagements" / "ENG-DOC" / "architecture-repository"
    enterprise_root = tmp_path / "enterprise-repository"
    (engagement_root / "model").mkdir(parents=True)
    _write(
        enterprise_root / "docs" / "adrs" / "ADR@2000000000.DocAAA.global-doc.md",
        _document_md("ADR@2000000000.DocAAA.global-doc", "Global Doc"),
    )

    repo = ArtifactRepository(shared_artifact_index([engagement_root, enterprise_root]))
    gui_state.init_state(repo, engagement_root, enterprise_root)

    payload = read_document("ADR@2000000000.DocAAA.global-doc")

    assert payload["artifact_id"] == "ADR@2000000000.DocAAA.global-doc"
    assert payload["is_global"] is True


def test_entity_detail_view_supports_reference_picker_for_summary_and_notes() -> None:
    view_content = Path("tools/gui/src/ui/views/EntityDetailView.vue").read_text(encoding="utf-8")
    edit_form_content = Path("tools/gui/src/ui/components/EntityEditFormCard.vue").read_text(encoding="utf-8")

    assert "ArtifactReferenceInput" in view_content
    assert "addToast('Entity saved')" in view_content
    assert "open-reference-picker', 'summary'" in edit_form_content
    assert "open-reference-picker', 'notes'" in edit_form_content


def test_document_detail_view_keeps_reference_insert_near_editor_and_confirms_save() -> None:
    view_path = Path("tools/gui/src/ui/views/DocumentDetailView.vue")
    content = view_path.read_text(encoding="utf-8")

    assert content.count("Insert Reference") == 1
    assert 'class="bottom-actions"' in content
    assert "addToast('Document saved')" in content


def test_edit_diagram_view_shows_header_save_actions_and_confirms_save() -> None:
    view_content = Path("tools/gui/src/ui/views/EditDiagramView.vue").read_text(encoding="utf-8")
    header_content = Path("tools/gui/src/ui/components/DiagramEditHeader.vue").read_text(encoding="utf-8")

    assert 'class="hdr-actions"' in header_content
    assert "addToast('Diagram saved')" in view_content


def test_promote_view_supports_document_and_diagram_promotion() -> None:
    view_content = Path("tools/gui/src/ui/views/PromoteView.vue").read_text(encoding="utf-8")
    workflow_content = Path("tools/gui/src/ui/composables/usePromotionWorkflow.ts").read_text(encoding="utf-8")

    assert "initializeFromRoute" in view_content
    assert "document_ids:" in workflow_content
    assert "diagram_ids:" in workflow_content
    assert "routeQuery.value.document_id" in workflow_content
    assert "routeQuery.value.diagram_id" in workflow_content


def test_diagram_detail_view_queues_connection_matches_and_promote_button() -> None:
    selection_content = Path("tools/gui/src/ui/composables/useDiagramSvgSelection.ts").read_text(encoding="utf-8")
    header_content = Path("tools/gui/src/ui/components/DiagramDetailHeader.vue").read_text(encoding="utf-8")

    # Connection matching is delegated to the viewer-extension contract (mapElements), which
    # itself calls buildConnectionAliasMap/resolveConnection — see graphvizElementMapping.ts.
    assert "resolveElementMap" in selection_content
    assert "selectedConnectionGroup" in selection_content
    assert "query: { diagram_id: diagramId }" in header_content


def test_graphviz_element_mapping_matches_connections_via_alias_helpers() -> None:
    content = Path("tools/gui/src/ui/lib/graphvizElementMapping.ts").read_text(encoding="utf-8")

    assert "buildConnectionAliasMap" in content
    assert "resolveConnection" in content
