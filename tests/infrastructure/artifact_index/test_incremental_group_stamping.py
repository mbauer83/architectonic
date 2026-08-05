"""Regression coverage: incremental index updates must stamp `.group` from the
file's actual path, exactly like the full-scan path does.

Root cause this guards against: `_scan_model_records`/`_scan_diagram_records`/
`_scan_document_records` (the full `refresh()` path) explicitly compute
`group_fn_*(path, mount.root)` and stamp it onto the parsed record, but the
incremental `parse_*_for_path` functions (used by `ArtifactIndex.apply_file_changes`,
which every entity/diagram/document edit — including a bare `artifact_group` move —
goes through) used to skip that step entirely, leaving every incrementally
indexed record at `EntityRecord.group`'s dataclass default of "uncategorized"
regardless of where the file actually lives. Symptom: `artifact_bulk_write`/
`artifact_edit_entity`/`artifact_edit_diagram`/`artifact_edit_document` group
re-homing reported `wrote: true` and moved the file correctly on disk, but
`artifact_query_stats`/`artifact_query_list_artifacts` kept reporting the old
group until an explicit `artifact_admin_reindex` forced a full rescan.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from src.domain.ontology_representation.artifact_types import infer_mount
from src.infrastructure.artifact_index._service_incremental import (
    parse_diagram_for_path,
    parse_document_for_path,
    parse_entity_for_path,
    parse_outgoing_for_path,
)
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp import context as ctx


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    (root / ".arch-repo" / "documents").mkdir(parents=True)
    (root / ".arch-repo" / "documents" / "adr.json").write_text(
        '{"abbreviation": "ADR", "required_sections": ["Context", "Decision", "Consequences"]}',
        encoding="utf-8",
    )
    return root


# ---------------------------------------------------------------------------
# Unit: parse_*_for_path stamp group from the path, matching full-scan
# ---------------------------------------------------------------------------


def test_parse_entity_for_path_stamps_group_from_projects_layout(repo: Path) -> None:
    eid = "REQ@1.a.probe"
    path = repo / "projects" / "my-group" / "model" / "motivation" / "requirement" / f"{eid}.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\nartifact-id: REQ@1.a.probe\nartifact-type: requirement\nname: Probe\n"
        "version: 0.1.0\nstatus: draft\nlast-updated: '2026-01-01'\n---\n\n## Probe\n",
        encoding="utf-8",
    )
    record = parse_entity_for_path(path, [infer_mount(repo)], domain_names=frozenset({"motivation"}))
    assert record is not None
    assert record.group == "my-group"


def test_parse_outgoing_for_path_stamps_group_from_projects_layout(repo: Path) -> None:
    eid = "REQ@1.a.probe"
    entity_dir = repo / "projects" / "my-group" / "model" / "motivation" / "requirement"
    entity_dir.mkdir(parents=True)
    outgoing = entity_dir / f"{eid}.outgoing.md"
    outgoing.write_text(
        "---\nsource-entity: REQ@1.a.probe\nversion: 0.1.0\nstatus: draft\n---\n\n"
        "### archimate-association → REQ@2.b.other\n",
        encoding="utf-8",
    )
    records = parse_outgoing_for_path(outgoing, [infer_mount(repo)])
    assert records
    assert all(r.group == "my-group" for r in records)


def test_parse_diagram_for_path_stamps_group_from_collection(repo: Path) -> None:
    did = "DIA@1.a.probe"
    path = repo / "diagram-catalog" / "diagrams" / "my-collection" / f"{did}.puml"
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\nartifact-id: DIA@1.a.probe\nartifact-type: diagram\ndiagram-type: c4-container\n"
        "name: Probe\nversion: 0.1.0\nstatus: draft\nlast-updated: '2026-01-01'\n"
        "entity-ids-used: []\nconnection-ids-used: []\n---\n@startuml probe\n@enduml\n",
        encoding="utf-8",
    )
    record = parse_diagram_for_path(path, [infer_mount(repo)])
    assert record is not None
    assert record.group == "my-collection"


def test_parse_document_for_path_stamps_group_from_collection(repo: Path) -> None:
    docid = "ADR@1.a.probe"
    path = repo / "docs" / "adr" / "my-collection" / f"{docid}.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\nartifact-id: ADR@1.a.probe\nartifact-type: document\ndoc-type: adr\n"
        "title: Probe\nstatus: draft\nversion: 0.1.0\nlast-updated: '2026-01-01'\n---\n\n"
        "## Context\n\nX\n\n## Decision\n\nY\n\n## Consequences\n\nZ\n",
        encoding="utf-8",
    )
    record = parse_document_for_path(path, [infer_mount(repo)])
    assert record is not None
    assert record.group == "my-collection"


# ---------------------------------------------------------------------------
# End-to-end: group re-homing is visible immediately, no explicit reindex
# ---------------------------------------------------------------------------


def test_bulk_write_group_move_visible_without_explicit_reindex(repo: Path) -> None:
    from src.infrastructure.mcp.artifact_mcp.bulk_tools import artifact_bulk_write

    r = mcp.artifact_create_entity(artifact_type="requirement", name="Probe", dry_run=False, repo_root=str(repo))
    eid = r["artifact_id"]

    roots = ctx.resolve_repo_roots(repo_scope="engagement", repo_root=str(repo), repo_preset=None, enterprise_root=None)
    key = ctx.roots_key(roots)
    before = ctx.repo_cached(key).stats()["entities_by_group"]
    assert before == {"uncategorized": 1}

    result = artifact_bulk_write(
        items=[{"op": "edit_entity", "artifact_id": eid, "group": "my-group"}],
        dry_run=False,
        repo_root=str(repo),
        return_mode="full",
    )
    assert cast(list[dict[str, Any]], result["items"])[0]["wrote"]

    after = ctx.repo_cached(key).stats()["entities_by_group"]
    assert after == {"my-group": 1}


def test_single_edit_diagram_group_move_visible_without_explicit_reindex(repo: Path) -> None:
    d = mcp.artifact_create_diagram(
        diagram_type="c4-container",
        name="Diag Probe",
        diagram_entities={"software-system": [{"id": "sys", "label": "Sys"}]},
        dry_run=False,
        repo_root=str(repo),
    )
    did = d["artifact_id"]

    result = mcp.artifact_edit_diagram(artifact_id=did, group="diag-group", dry_run=False, repo_root=str(repo))
    assert result["wrote"]

    roots = ctx.resolve_repo_roots(repo_scope="engagement", repo_root=str(repo), repo_preset=None, enterprise_root=None)
    key = ctx.roots_key(roots)
    assert ctx.repo_cached(key).stats()["diagrams_by_group"] == {"diag-group": 1}


def test_single_edit_document_group_move_visible_without_explicit_reindex(repo: Path) -> None:
    doc = mcp.artifact_create_document(doc_type="adr", title="Doc Probe", dry_run=False, repo_root=str(repo))
    docid = doc["artifact_id"]

    result = mcp.artifact_edit_document(artifact_id=docid, group="doc-group", dry_run=False, repo_root=str(repo))
    assert result["wrote"]

    roots = ctx.resolve_repo_roots(repo_scope="engagement", repo_root=str(repo), repo_preset=None, enterprise_root=None)
    key = ctx.roots_key(roots)
    assert ctx.repo_cached(key).stats()["documents_by_group"] == {"doc-group": 1}
