"""Canonical-equality consumer tests (WS6 acceptance).

Verifies that every consumer of entity/connection identity treats
stale-slug and current-slug forms as the same artifact, with no
duplicate edges or spurious rejections.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.artifact_id import stable_conn_id, stable_id

# ── helpers ──────────────────────────────────────────────────────────────────

_SRC_OLD = "SRC@1000000000.SrcAaa.old-slug"
_SRC_NEW = "SRC@1000000000.SrcAaa.new-slug"
_TGT_OLD = "TGT@1000000001.TgtBbb.old-name"
_TGT_NEW = "TGT@1000000001.TgtBbb.current-name"
_TYPE = "archimate-serving"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _entity_md(artifact_id: str, name: str, artifact_type: str = "application-component") -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: {artifact_type}
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
---

<!-- §content -->

## {name}
"""


def _outgoing_md(source: str, connections: list[tuple[str, str]]) -> str:
    lines = [
        "---",
        f"source-entity: {source}",
        "status: draft",
        "last-updated: '2026-01-01'",
        "---",
        "",
        "<!-- §connections -->",
        "",
    ]
    for conn_type, target in connections:
        lines.append(f"### {conn_type} → {target}")
        lines.append("")
    return "\n".join(lines)


def _diagram_md(artifact_id: str, entity_ids: list[str], conn_ids: list[str]) -> str:
    eid_yaml = "\n".join(f"  - {e}" for e in entity_ids)
    cid_yaml = "\n".join(f"  - {c}" for c in conn_ids)
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: diagram
diagram-type: archimate-application
name: "Test Diagram"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
entity-ids-used:
{eid_yaml}
connection-ids-used:
{cid_yaml}
---
@startuml {artifact_id}
!include ../_archimate-stereotypes.puml
title Test Diagram
rectangle "Src" as SRC_SrcAaa
rectangle "Tgt" as TGT_TgtBbb
@enduml
"""


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    src_dir = root / "model" / "application" / "component"
    src_dir.mkdir(parents=True)
    diag_dir = root / "diagram-catalog" / "diagrams"
    diag_dir.mkdir(parents=True)
    return root


# ── 1. Domain identity functions ──────────────────────────────────────────────

class TestStableIdFunctions:
    def test_stable_id_strips_slug(self) -> None:
        assert stable_id(_SRC_OLD) == "SRC@1000000000.SrcAaa"
        assert stable_id(_SRC_NEW) == "SRC@1000000000.SrcAaa"

    def test_stable_id_already_short_unchanged(self) -> None:
        short = "SRC@1000000000.SrcAaa"
        assert stable_id(short) == short

    def test_stable_id_stale_eq_current(self) -> None:
        assert stable_id(_SRC_OLD) == stable_id(_SRC_NEW)
        assert stable_id(_TGT_OLD) == stable_id(_TGT_NEW)

    def test_stable_conn_id_stale_slug_eq_current_slug(self) -> None:
        stale = f"{_SRC_OLD}---{_TGT_OLD}@@{_TYPE}"
        current = f"{_SRC_NEW}---{_TGT_NEW}@@{_TYPE}"
        stable_form = f"SRC@1000000000.SrcAaa---TGT@1000000001.TgtBbb@@{_TYPE}"
        assert stable_conn_id(stale) == stable_form
        assert stable_conn_id(current) == stable_form
        assert stable_conn_id(stable_form) == stable_form

    def test_stable_conn_id_malformed_returns_input(self) -> None:
        bad = "not-a-connection-id"
        assert stable_conn_id(bad) == bad


# ── 2. Artifact parsing: connection artifact_id is stable ─────────────────────

class TestConnectionArtifactIdIsStable:
    def test_connection_artifact_id_strips_slugs(self, repo_root: Path) -> None:
        from src.application.artifact_parsing import parse_outgoing_file

        src_dir = repo_root / "model" / "application" / "component"
        out_path = src_dir / f"{_SRC_NEW}.outgoing.md"
        _write(out_path, _outgoing_md(_SRC_NEW, [(_TYPE, _TGT_NEW)]))

        records = parse_outgoing_file(out_path)
        assert len(records) == 1
        expected_stable_id = f"SRC@1000000000.SrcAaa---TGT@1000000001.TgtBbb@@{_TYPE}"
        assert records[0].artifact_id == expected_stable_id

    def test_stale_slug_source_produces_same_artifact_id(self, repo_root: Path) -> None:
        from src.application.artifact_parsing import parse_outgoing_file

        src_dir = repo_root / "model" / "application" / "component"
        out_new = src_dir / f"{_SRC_NEW}.outgoing.md"
        out_old = src_dir / f"{_SRC_OLD}.outgoing.md"
        _write(out_new, _outgoing_md(_SRC_NEW, [(_TYPE, _TGT_NEW)]))
        _write(out_old, _outgoing_md(_SRC_OLD, [(_TYPE, _TGT_OLD)]))

        ids_new = {r.artifact_id for r in parse_outgoing_file(out_new)}
        ids_old = {r.artifact_id for r in parse_outgoing_file(out_old)}
        assert ids_new == ids_old


# ── 3. Verifier E301/E302 accepts stale-slug references ──────────────────────

class TestVerifierStaleSlugAcceptance:
    def test_e302_accepts_stale_slug_connection_in_diagram(self, repo_root: Path) -> None:
        from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
        from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs
        from src.infrastructure.artifact_index import shared_artifact_index

        src_dir = repo_root / "model" / "application" / "component"
        _write(src_dir / f"{_SRC_NEW}.md", _entity_md(_SRC_NEW, "Source"))
        _write(src_dir / f"{_TGT_NEW}.md", _entity_md(_TGT_NEW, "Target"))
        _write(src_dir / f"{_SRC_NEW}.outgoing.md", _outgoing_md(_SRC_NEW, [(_TYPE, _TGT_NEW)]))

        stable_cid = f"SRC@1000000000.SrcAaa---TGT@1000000001.TgtBbb@@{_TYPE}"
        stale_cid = f"{_SRC_OLD}---{_TGT_OLD}@@{_TYPE}"

        diag_dir = repo_root / "diagram-catalog" / "diagrams"
        diag_path = diag_dir / "ARC@1000000002.DiagAb.test.puml"
        _write(diag_path, _diagram_md(
            "ARC@1000000002.DiagAb.test",
            [_SRC_NEW, _TGT_NEW],
            [stale_cid],
        ))

        registry = ArtifactRegistry(shared_artifact_index([repo_root]))
        assert stable_cid in registry.connection_ids(), "index should expose stable connection ID"

        catalogs = build_runtime_catalogs(build_module_registry())
        verifier = ArtifactVerifier(registry, check_puml_syntax=False, catalogs=catalogs)
        result = verifier.verify_diagram_file(diag_path)
        e302_issues = [i for i in result.issues if i.code == "E302"]
        assert not e302_issues, f"E302 should not fire for stale-slug connection ref: {e302_issues}"

    def test_e301_accepts_stale_slug_entity_in_diagram(self, repo_root: Path) -> None:
        from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
        from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs
        from src.infrastructure.artifact_index import shared_artifact_index

        src_dir = repo_root / "model" / "application" / "component"
        _write(src_dir / f"{_SRC_NEW}.md", _entity_md(_SRC_NEW, "Source"))

        diag_dir = repo_root / "diagram-catalog" / "diagrams"
        diag_path = diag_dir / "ARC@1000000003.DiagCc.stale.puml"
        _write(diag_path, _diagram_md(
            "ARC@1000000003.DiagCc.stale",
            [_SRC_OLD],
            [],
        ))

        registry = ArtifactRegistry(shared_artifact_index([repo_root]))
        catalogs = build_runtime_catalogs(build_module_registry())
        verifier = ArtifactVerifier(registry, check_puml_syntax=False, catalogs=catalogs)
        result = verifier.verify_diagram_file(diag_path)
        e301_issues = [i for i in result.issues if i.code == "E301"]
        assert not e301_issues, f"E301 should not fire for stale-slug entity ref: {e301_issues}"


# ── 4. Connection dedup: stale-slug target not treated as a new edge ──────────

class TestConnectionDedup:
    def test_no_duplicate_edge_stale_vs_current_slug(self, repo_root: Path) -> None:
        from src.infrastructure.mcp import mcp_artifact_server as mcp

        src_dir = repo_root / "model" / "application" / "component"
        _write(src_dir / f"{_SRC_NEW}.md", _entity_md(_SRC_NEW, "Source"))
        _write(src_dir / f"{_TGT_NEW}.md", _entity_md(_TGT_NEW, "Target"))

        r1 = mcp.artifact_add_connection(
            connection_type=_TYPE,
            source_entity=_SRC_NEW,
            target_entity=_TGT_NEW,
            dry_run=False,
            repo_root=str(repo_root),
        )
        assert r1["wrote"] is True

        with pytest.raises(ValueError, match="already exists"):
            mcp.artifact_add_connection(
                connection_type=_TYPE,
                source_entity=_SRC_NEW,
                target_entity=_TGT_OLD,
                dry_run=False,
                repo_root=str(repo_root),
            )


# ── 5. Connection edit/remove with stale-slug target ─────────────────────────

class TestConnectionEditRemoveStaleSlug:
    def test_edit_connection_accepts_stale_slug_target(self, repo_root: Path) -> None:
        from src.infrastructure.mcp import mcp_artifact_server as mcp

        src_dir = repo_root / "model" / "application" / "component"
        _write(src_dir / f"{_SRC_NEW}.md", _entity_md(_SRC_NEW, "Source"))
        _write(src_dir / f"{_TGT_NEW}.md", _entity_md(_TGT_NEW, "Target"))

        add = mcp.artifact_add_connection(
            connection_type=_TYPE,
            source_entity=_SRC_NEW,
            target_entity=_TGT_NEW,
            dry_run=False,
            repo_root=str(repo_root),
        )
        assert add["wrote"] is True

        result = mcp.artifact_edit_connection(
            source_entity=_SRC_NEW,
            connection_type=_TYPE,
            target_entity=_TGT_OLD,
            description="Updated description",
            dry_run=False,
            repo_root=str(repo_root),
        )
        assert result.get("wrote") is True, f"Edit with stale target slug failed: {result}"

    def test_remove_connection_accepts_stale_slug_target(self, repo_root: Path) -> None:
        from src.infrastructure.mcp import mcp_artifact_server as mcp

        src_dir = repo_root / "model" / "application" / "component"
        _write(src_dir / f"{_SRC_NEW}.md", _entity_md(_SRC_NEW, "Source"))
        _write(src_dir / f"{_TGT_NEW}.md", _entity_md(_TGT_NEW, "Target"))

        add = mcp.artifact_add_connection(
            connection_type=_TYPE,
            source_entity=_SRC_NEW,
            target_entity=_TGT_NEW,
            dry_run=False,
            repo_root=str(repo_root),
        )
        assert add["wrote"] is True

        result = mcp.artifact_edit_connection(
            source_entity=_SRC_NEW,
            connection_type=_TYPE,
            target_entity=_TGT_OLD,
            operation="remove",
            dry_run=False,
            repo_root=str(repo_root),
        )
        assert result.get("wrote") is True, f"Remove with stale target slug failed: {result}"
