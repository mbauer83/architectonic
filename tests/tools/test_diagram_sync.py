"""Tests for diagram-to-model sync.

Covers:
- Stale entity IDs are returned in removed_entity_ids
- Stale connection IDs are returned in removed_connection_ids
- Surviving entities/connections stay in entity-ids-used frontmatter
- dry_run=True returns content without writing
- MCP artifact_edit_diagram dispatches to sync when puml="auto-sync"
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------
import pytest
import yaml

from src.application.artifacts.repository import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.write.artifact_write.diagram_sync import sync_diagram_to_model


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _make_entity(repo: Path, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type="requirement",
        name=name,
        summary=f"Summary for {name}",
        dry_run=False,
        repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _make_diagram(repo: Path, name: str, entity_ids: list[str]) -> str:
    """Write a diagram file directly so we can control entity-ids-used frontmatter.

    Entity IDs may be stale (already deleted) — that is intentional for sync tests.
    """
    import yaml as _yaml

    slug = name.lower().replace(" ", "-")
    artifact_id = f"DIA@1777000000.tstXX.{slug}"
    entity_ids_yaml = cast(str, _yaml.dump(entity_ids, default_flow_style=True)).strip()
    content = f"""\
---
artifact-id: {artifact_id}
artifact-type: diagram
diagram-type: archimate-motivation
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
entity-ids-used: {entity_ids_yaml}
connection-ids-used: []
---
@startuml {slug}
top to bottom direction
@enduml
"""
    path = repo / "diagram-catalog" / "diagrams" / f"{artifact_id}.puml"
    path.write_text(content, encoding="utf-8")
    return artifact_id


def _std_alias(artifact_id: str) -> str:
    prefix_part, random_part, *_ = artifact_id.split(".")
    prefix = prefix_part.split("@", 1)[0]
    return f"{prefix}_{random_part}"


def _delete_entity(repo: Path, artifact_id: str) -> None:
    """Delete an entity that is NOT referenced by any diagram (no dependency conflict)."""
    result = mcp.artifact_bulk_delete(
        items=[{"op": "delete_entity", "artifact_id": artifact_id}],
        dry_run=False,
        repo_root=str(repo),
    )
    results = result.get("results", [])
    assert results and results[0].get("wrote"), result


def _fresh_store(repo: Path) -> ArtifactRepository:
    return ArtifactRepository(shared_artifact_index(repo))


def _read_entity_ids_used(repo: Path, diagram_id: str) -> list[str]:
    path = repo / "diagram-catalog" / "diagrams" / f"{diagram_id}.puml"
    text = path.read_text()
    fm_text = text.split("---")[1]
    fm = yaml.safe_load(fm_text)
    return list(fm.get("entity-ids-used") or [])


def _make_context(repo: Path):  # type: ignore[return]
    from src.infrastructure.mcp.artifact_mcp.context import (
        clear_caches_for_repo,
        resolve_repo_roots,
        roots_key,
        verifier_for,
    )

    roots = resolve_repo_roots(
        repo_scope="engagement",
        repo_root=str(repo),
        repo_preset=None,
        enterprise_root=None,
    )
    verifier = verifier_for(roots_key(roots), include_registry=False)
    return verifier, clear_caches_for_repo


# ---------------------------------------------------------------------------
# sync_diagram_to_model (write-layer)
# ---------------------------------------------------------------------------


class TestSyncDiagramToModel:
    def test_stale_entity_reported_in_removed_ids(self, repo: Path) -> None:
        # Create both, delete e2 BEFORE the diagram is written so no dependency
        # conflict blocks the delete; diagram then has a stale reference to e2.
        e1 = _make_entity(repo, "Keep Me")
        e2 = _make_entity(repo, "Delete Me")
        _delete_entity(repo, e2)
        diag_id = _make_diagram(repo, "Sync Test Diagram", [e1, e2])

        store = _fresh_store(repo)
        verifier, clear_caches = _make_context(repo)

        result = sync_diagram_to_model(
            repo_root=repo,
            store=store,
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=True,
        )

        assert e2 in result.removed_entity_ids
        assert e1 not in result.removed_entity_ids
        assert result.removed_connection_ids == []

    def test_surviving_entity_kept_in_frontmatter(self, repo: Path) -> None:
        e1 = _make_entity(repo, "Survivor")
        e2 = _make_entity(repo, "Gone")
        _delete_entity(repo, e2)
        diag_id = _make_diagram(repo, "Survivor Diagram", [e1, e2])

        store = _fresh_store(repo)
        verifier, clear_caches = _make_context(repo)

        result = sync_diagram_to_model(
            repo_root=repo,
            store=store,
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=False,
        )

        assert result.wrote is True
        ids_in_fm = _read_entity_ids_used(repo, diag_id)
        assert e1 in ids_in_fm
        assert e2 not in ids_in_fm

    def test_dry_run_does_not_modify_file(self, repo: Path) -> None:
        e1 = _make_entity(repo, "Only Entity")
        _delete_entity(repo, e1)
        diag_id = _make_diagram(repo, "Dry Run Sync", [e1])

        store = _fresh_store(repo)
        verifier, clear_caches = _make_context(repo)

        before = (repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml").read_text()

        result = sync_diagram_to_model(
            repo_root=repo,
            store=store,
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=True,
        )

        after = (repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml").read_text()
        assert result.wrote is False
        assert before == after
        assert result.removed_entity_ids == [e1]

    def test_no_stale_ids_means_empty_removed_lists(self, repo: Path) -> None:
        e1 = _make_entity(repo, "Still Here")
        diag_id = _make_diagram(repo, "Clean Diagram", [e1])

        store = _fresh_store(repo)
        verifier, clear_caches = _make_context(repo)

        result = sync_diagram_to_model(
            repo_root=repo,
            store=store,
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=True,
        )

        assert result.removed_entity_ids == []
        assert result.removed_connection_ids == []

    def test_renamed_entity_is_updated_not_removed(self, repo: Path) -> None:
        # e1 gets created, its old ID goes into a diagram, then it is renamed.
        # Sync should follow the stable prefix and keep the entity (with the new ID),
        # not treat it as deleted.
        e1_old = _make_entity(repo, "Original Name")
        diag_id = _make_diagram(repo, "Rename Test Diagram", [e1_old])

        # Rename via MCP — produces a new artifact_id with a different slug
        rename_result = mcp.artifact_edit_entity(
            artifact_id=e1_old,
            name="New Name",
            dry_run=False,
            repo_root=str(repo),
        )
        assert rename_result["wrote"], rename_result
        e1_new = str(rename_result["artifact_id"])
        assert e1_new != e1_old, "rename must produce a new artifact_id"

        store = _fresh_store(repo)
        verifier, clear_caches = _make_context(repo)

        result = sync_diagram_to_model(
            repo_root=repo,
            store=store,
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=False,
        )

        # The entity must NOT appear in removed_entity_ids
        assert e1_old not in result.removed_entity_ids
        assert e1_new not in result.removed_entity_ids
        # The diagram frontmatter must reference the NEW id
        ids_in_fm = _read_entity_ids_used(repo, diag_id)
        assert e1_new in ids_in_fm
        assert e1_old not in ids_in_fm

    def test_visible_stale_relation_is_removed_even_without_frontmatter_connection_id(self, repo: Path) -> None:
        src = _make_entity(repo, "Source")
        tgt = _make_entity(repo, "Target")
        _ = mcp.artifact_add_connection(
            source_entity=src,
            connection_type="archimate-influence",
            target_entity=tgt,
            dry_run=False,
            repo_root=str(repo),
        )
        result = mcp.artifact_bulk_delete(
            items=[
                {
                    "op": "delete_connection",
                    "source_entity": src,
                    "connection_type": "archimate-influence",
                    "target_entity": tgt,
                }
            ],
            dry_run=False,
            repo_root=str(repo),
        )
        assert result.get("results"), result

        src_alias = _std_alias(src)
        tgt_alias = _std_alias(tgt)
        diag_id = "DIA@1777000000.tstXX.visible-stale-relation"
        path = repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml"
        path.write_text(
            f"""\
---
artifact-id: {diag_id}
artifact-type: diagram
diagram-type: archimate-motivation
name: "Visible Stale Relation"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
entity-ids-used: [{src}, {tgt}]
connection-ids-used: []
---
@startuml {diag_id}
rectangle "Source" <<Requirement>> as {src_alias}
rectangle "Target" <<Requirement>> as {tgt_alias}
Rel_Influence({src_alias}, {tgt_alias}, "")
@enduml
""",
            encoding="utf-8",
        )

        store = _fresh_store(repo)
        verifier, clear_caches = _make_context(repo)
        sync_result = sync_diagram_to_model(
            repo_root=repo,
            store=store,
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=False,
        )

        assert sync_result.deleted_diagram is False
        assert f"{src}---{tgt}@@archimate-influence" in sync_result.removed_connection_ids
        text = path.read_text(encoding="utf-8")
        assert "Rel_Influence(" not in text

    def test_sync_does_not_delete_diagram_when_puml_entities_still_exist(self, repo: Path) -> None:
        src = _make_entity(repo, "Alive Source")
        tgt = _make_entity(repo, "Alive Target")
        src_alias = _std_alias(src)
        tgt_alias = _std_alias(tgt)
        diag_id = "DIA@1777000000.tstXX.puml-entities-survive"
        path = repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml"
        path.write_text(
            f"""\
---
artifact-id: {diag_id}
artifact-type: diagram
diagram-type: archimate-motivation
name: "PUML Entities Survive"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
entity-ids-used: []
connection-ids-used: []
---
@startuml {diag_id}
rectangle "Source" <<Requirement>> as {src_alias}
rectangle "Target" <<Requirement>> as {tgt_alias}
Rel_Influence({src_alias}, {tgt_alias}, "")
@enduml
""",
            encoding="utf-8",
        )

        store = _fresh_store(repo)
        verifier, clear_caches = _make_context(repo)
        sync_result = sync_diagram_to_model(
            repo_root=repo,
            store=store,
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=False,
        )

        assert sync_result.deleted_diagram is False
        assert path.exists()
        assert sync_result.removed_connection_ids == [f"{src}---{tgt}@@archimate-influence"]


# ---------------------------------------------------------------------------
# MCP artifact_edit_diagram with puml="auto-sync"
# ---------------------------------------------------------------------------


class TestMcpAutoSyncDispatch:
    def test_auto_sync_removes_stale_entity_via_mcp(self, repo: Path) -> None:
        e1 = _make_entity(repo, "Present")
        e2 = _make_entity(repo, "Absent")
        _delete_entity(repo, e2)
        diag_id = _make_diagram(repo, "MCP Sync Diagram", [e1, e2])

        result = mcp.artifact_edit_diagram(
            artifact_id=diag_id,
            puml="auto-sync",
            dry_run=False,
            repo_root=str(repo),
        )

        assert result["wrote"] is True
        removed = cast(list[str], result.get("removed_entity_ids", []))
        assert e2 in removed
        assert e1 not in removed

    def test_auto_sync_dry_run_does_not_write(self, repo: Path) -> None:
        e1 = _make_entity(repo, "Kept")
        e2 = _make_entity(repo, "Removed")
        _delete_entity(repo, e2)
        diag_id = _make_diagram(repo, "Dry Sync Via MCP", [e1, e2])

        before = (repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml").read_text()

        result = mcp.artifact_edit_diagram(
            artifact_id=diag_id,
            puml="auto-sync",
            dry_run=True,
            repo_root=str(repo),
        )

        after = (repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml").read_text()
        assert result["wrote"] is False
        assert before == after
        assert "removed_entity_ids" in result

    def test_auto_sync_result_includes_removed_keys(self, repo: Path) -> None:
        e1 = _make_entity(repo, "Alpha")
        diag_id = _make_diagram(repo, "Keys Check", [e1])

        result = mcp.artifact_edit_diagram(
            artifact_id=diag_id,
            puml="auto-sync",
            dry_run=True,
            repo_root=str(repo),
        )

        assert "removed_entity_ids" in result
        assert "removed_connection_ids" in result


class TestAReconcileSaysWhatItIsNotDrawing:
    """A relation added between two elements already on a diagram leaves it out of date.

    Reconciling converges in one direction: it drops what the model no longer has, and never
    adopts what the model has gained — the entity set is the authored thing, and a bulk delete
    auto-syncs every dependent diagram, so adopting would redraw curated views as a side effect of
    unrelated maintenance. What was wrong is that the other direction was *silent*: a sync answered
    `wrote: true` over a picture that no longer said what the model said, and the only way to find
    out was to look. Reported now, with the edit that adopts it.
    """

    @staticmethod
    def _diagram_missing_one_relation(repo: Path) -> tuple[str, str]:
        """Two entities on a diagram, and a model connection between them it does not draw."""
        src = _make_entity(repo, "Reporter")
        tgt = _make_entity(repo, "Reported On")
        added = mcp.artifact_add_connection(
            source_entity=src,
            connection_type="archimate-influence",
            target_entity=tgt,
            dry_run=False,
            repo_root=str(repo),
        )
        assert added["wrote"], added
        return _make_diagram(repo, "Undrawn Relation Diagram", [src, tgt]), str(added["artifact_id"])

    def _sync(self, repo: Path, diagram_id: str):  # type: ignore[no-untyped-def]
        verifier, clear_caches = _make_context(repo)
        return sync_diagram_to_model(
            repo_root=repo,
            store=_fresh_store(repo),
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diagram_id,
            dry_run=True,
        )

    def test_the_undrawn_connection_is_named(self, repo: Path) -> None:
        diagram_id, connection_id = self._diagram_missing_one_relation(repo)

        result = self._sync(repo, diagram_id)

        reported = [w for w in result.warnings if "does not draw" in w]
        assert reported, result.warnings
        assert connection_id in reported[0]

    def test_the_report_says_how_to_adopt_it(self, repo: Path) -> None:
        diagram_id, _ = self._diagram_missing_one_relation(repo)

        result = self._sync(repo, diagram_id)

        assert any("entity_ids" in w for w in result.warnings), result.warnings

    def test_a_diagram_drawing_everything_is_not_warned_about(self, repo: Path) -> None:
        e1 = _make_entity(repo, "Alone")
        e2 = _make_entity(repo, "Also Alone")
        diagram_id = _make_diagram(repo, "Nothing Undrawn", [e1, e2])

        result = self._sync(repo, diagram_id)

        assert [w for w in result.warnings if "does not draw" in w] == []


class TestNestedGroupingsSurviveReconciliation:
    """Boxes nest to any depth — the served contract says so — and the reconcile discarded the nesting.

    Measured before the fix: `Outer[alpha] > Inner[beta, gamma]` came back from `auto-sync` as
    `Outer[alpha]` alone, with no warning, so two members lost their grouping silently. Each group
    was rebuilt from three keys, and `groups` was not one of them.
    """

    def _reconcile(self, fm: dict, records: list) -> tuple[list[dict], list[str]]:
        from src.infrastructure.write.artifact_write.diagram_sync import (
            _reconciled_authored_groupings,
        )

        return _reconciled_authored_groupings(fm, "@startuml\n@enduml\n", records)

    def _record(self, artifact_id: str):
        from dataclasses import make_dataclass

        return make_dataclass("R", ["artifact_id", "display_alias"])(artifact_id, artifact_id)

    def test_a_nested_box_keeps_its_members(self) -> None:
        records = [self._record(f"APP@1.{n}") for n in ("alpha", "beta", "gamma")]
        fm = {"authored-groupings": [{
            "label": "Outer", "entity-ids": ["APP@1.alpha"],
            "groups": [{"label": "Inner", "entity-ids": ["APP@1.beta", "APP@1.gamma"]}],
        }]}

        reconciled, warnings = self._reconcile(fm, records)

        assert reconciled == [{
            "label": "Outer", "entity-ids": ["APP@1.alpha"],
            "groups": [{"label": "Inner", "entity-ids": ["APP@1.beta", "APP@1.gamma"]}],
        }]
        assert warnings == []

    def test_a_box_that_only_nests_others_is_kept(self) -> None:
        """A box holds members, or holds boxes, or both — so having no members of its own is not
        the same as being empty."""
        records = [self._record("APP@1.beta")]
        fm = {"authored-groupings": [{
            "label": "Outer", "groups": [{"label": "Inner", "entity-ids": ["APP@1.beta"]}],
        }]}

        reconciled, _warnings = self._reconcile(fm, records)

        assert reconciled == [{
            "label": "Outer", "groups": [{"label": "Inner", "entity-ids": ["APP@1.beta"]}],
        }]

    def test_a_member_that_left_the_diagram_is_still_dropped_with_a_warning(self) -> None:
        records = [self._record("APP@1.alpha")]
        fm = {"authored-groupings": [{
            "label": "Outer", "entity-ids": ["APP@1.alpha"],
            "groups": [{"label": "Inner", "entity-ids": ["APP@1.gone"]}],
        }]}

        reconciled, warnings = self._reconcile(fm, records)

        assert reconciled == [{"label": "Outer", "entity-ids": ["APP@1.alpha"]}]
        assert any("APP@1.gone" in warning for warning in warnings)


class TestAStaleSlugIsCorrectedByASync:
    """A reference that resolves but names its target by a slug it no longer has.

    W305 reports it and tells the author to rewrite it, and the write-up on file says nothing does —
    that no operation clears it short of resending a manual-layout diagram's whole body. Re-measured
    here: `auto-sync` corrects it, on a manual-layout diagram, without touching the body. The
    diagnosis was true of an earlier release and is kept as a test rather than a claim, because that
    is the difference between the two.
    """

    def test_auto_sync_rewrites_a_stale_but_resolvable_slug(self, repo: Path) -> None:
        from src.domain.repository.frontmatter import parse_frontmatter
        from src.infrastructure.mcp import mcp_artifact_server as mcp
        from src.infrastructure.workspace.engagement_repo_template import ensure_arch_repo_defaults

        ensure_arch_repo_defaults(repo)
        made = [
            str(mcp.artifact_create_entity(
                artifact_type="application-component", name=name, summary=f"Summary for {name}",
                dry_run=False, repo_root=str(repo),
            )["artifact_id"])
            for name in ("Planning Runs", "Keeper")
        ]
        created = mcp.artifact_create_diagram(
            name="Hand laid", diagram_type="archimate-application", entity_ids=made,
            dry_run=False, repo_root=str(repo),
        )
        diagram_id, path = str(created["artifact_id"]), Path(str(created["path"]))
        body = "@startuml" + path.read_text(encoding="utf-8").split("@startuml", 1)[1]
        mcp.artifact_edit_diagram(artifact_id=diagram_id, puml=body, manual_layout=True,
                                 dry_run=False, repo_root=str(repo))

        # The state the report found: a slug the artifact has dropped, still resolvable by short id.
        stale = made[0].rsplit(".", 1)[0] + ".a-slug-it-no-longer-has"
        path.write_text(path.read_text(encoding="utf-8").replace(made[0], stale, 1), encoding="utf-8")
        assert stale in (parse_frontmatter(path.read_text(encoding="utf-8")).get("entity-ids-used") or [])

        mcp.artifact_edit_diagram(artifact_id=diagram_id, puml="auto-sync",
                                  dry_run=False, repo_root=str(repo))

        recorded = parse_frontmatter(path.read_text(encoding="utf-8")).get("entity-ids-used") or []
        assert stale not in recorded, "auto-sync left the stale slug in place"
        assert sorted(recorded) == sorted(made)


class TestAStatedReferenceSetBesideASync:
    """Correcting a hand-laid diagram's reference lists without resending its drawing.

    W307 names a wrong entry and says to pass `connection_ids` alongside `puml`. On a hand-laid
    diagram that means a *literal* body — 13 to 22 KB of layout on the views this was reported from,
    past what a tool call carries. A sync keeps such a body verbatim and already rewrites those two
    fields' spellings, so a stated set belongs there: it is a claim about the body rather than an edit
    to it.

    Where a sync *regenerates* the body, the body decides the lists and a stated set is refused
    instead of being computed over.
    """

    def _repo(self, repo: Path) -> tuple[str, Path, list[str], str]:
        from src.application.puml_alias_declarations import alias_declared_on
        from src.infrastructure.mcp import mcp_artifact_server as mcp
        from src.infrastructure.workspace.engagement_repo_template import ensure_arch_repo_defaults

        ensure_arch_repo_defaults(repo)
        made = [
            str(mcp.artifact_create_entity(
                artifact_type="application-component", name=name, summary=f"Summary for {name}",
                dry_run=False, repo_root=str(repo))["artifact_id"])
            for name in ("Alpha", "Beta", "Gamma")
        ]
        drawn = str(mcp.artifact_add_connection(
            source_entity=made[0], target_entity=made[1], connection_type="archimate-serving",
            dry_run=False, repo_root=str(repo))["artifact_id"])
        for source, target, kind in (
            (made[0], made[2], "archimate-serving"), (made[1], made[2], "archimate-association"),
        ):
            mcp.artifact_add_connection(source_entity=source, target_entity=target,
                                        connection_type=kind, dry_run=False, repo_root=str(repo))
        created = mcp.artifact_create_diagram(
            name="Narrow", diagram_type="archimate-application", entity_ids=made,
            dry_run=False, repo_root=str(repo))
        diagram_id, path = str(created["artifact_id"]), Path(str(created["path"]))
        lines = ("@startuml" + path.read_text(encoding="utf-8").split("@startuml", 1)[1]).splitlines()
        gamma = next(
            d.alias for line in lines
            if "Gamma" in line and (d := alias_declared_on(line)) is not None
        )
        narrowed = "\n".join(
            line for line in lines
            if gamma not in line and "-[hidden]" not in line
            and "-->" not in line and " -- " not in line
        )
        mcp.artifact_edit_diagram(artifact_id=diagram_id, puml=narrowed, manual_layout=True,
                                  entity_ids=made[:2], dry_run=False, repo_root=str(repo))
        return diagram_id, path, made, drawn

    def test_a_hand_laid_diagram_takes_the_stated_set_without_its_body(self, repo: Path) -> None:
        from src.domain.repository.frontmatter import parse_frontmatter
        from src.infrastructure.mcp.artifact_mcp.edit_tools import artifact_edit_diagram

        diagram_id, path, _made, drawn = self._repo(repo)
        stale = parse_frontmatter(path.read_text(encoding="utf-8")).get("connection-ids-used") or []
        assert len(stale) > 1 and drawn not in stale

        result = artifact_edit_diagram(artifact_id=diagram_id, puml="auto-sync",
                                      connection_ids=[drawn], dry_run=False, repo_root=str(repo))

        assert result["wrote"] is True
        recorded = parse_frontmatter(path.read_text(encoding="utf-8")).get("connection-ids-used")
        assert recorded == [drawn]

    def test_a_regenerating_sync_refuses_a_stated_set(self, repo: Path) -> None:
        """The body decides its own references there, so a stated set would be computed over."""
        from src.infrastructure.mcp import mcp_artifact_server as mcp
        from src.infrastructure.mcp.artifact_mcp.edit_tools import artifact_edit_diagram

        diagram_id, _path, _made, drawn = self._repo(repo)
        # Hand the picture back to the generator: no longer hand-laid.
        mcp.artifact_edit_diagram(artifact_id=diagram_id, manual_layout=False,
                                  dry_run=False, repo_root=str(repo))

        # Raised, like the sibling refusal for the other fields auto-sync will not carry: a
        # refusal is actionable and a false success is not.
        with pytest.raises(ValueError, match="regenerates its body"):
            artifact_edit_diagram(artifact_id=diagram_id, puml="auto-sync",
                                  connection_ids=[drawn], dry_run=False, repo_root=str(repo))
