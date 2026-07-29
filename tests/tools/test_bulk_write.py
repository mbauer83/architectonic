"""Tests for artifact_bulk_write.

Covers: happy-path creates and connections, $ref substitution, auto-ordering
(connections submitted before entities still resolve), edit operations, error
isolation (one failure does not abort remaining items), content suppression,
dependency conflicts (duplicate connections, failed-ref propagation), and
dry-run coherence.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import pytest

from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.domain.artifact_id import stable_id
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.artifact_index.events import AuthoritativeIndexMutationCommitted, event_bus
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.bulk_tools import (
    artifact_bulk_delete,
    artifact_bulk_write,
    artifact_get_operation,
)
from src.infrastructure.write import artifact_write_ops


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs  # noqa: PLC0415

    return build_runtime_catalogs(build_module_registry())

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _make(repo: Path, artifact_type: str, name: str) -> str:
    r = mcp.artifact_create_entity(artifact_type=artifact_type, name=name, dry_run=False, repo_root=str(repo))
    assert r["wrote"], r
    return str(r["artifact_id"])


def _connect(repo: Path, src: str, tgt: str, conn_type: str) -> None:
    mcp.artifact_add_connection(
        source_entity=src, connection_type=conn_type, target_entity=tgt, dry_run=False, repo_root=str(repo)
    )


def _bulk(repo: Path, items, *, dry_run: bool = False, auto_sync_diagrams: bool = False):
    return artifact_bulk_write(
        items=items,
        dry_run=dry_run,
        repo_root=str(repo),
        auto_sync_diagrams=auto_sync_diagrams,
    )


def _bulk_delete(repo: Path, items, *, dry_run: bool = False, auto_sync_diagrams: bool = False):
    return artifact_bulk_delete(
        items=items,
        dry_run=dry_run,
        repo_root=str(repo),
        auto_sync_diagrams=auto_sync_diagrams,
    )


def _bulk_with_key(repo: Path, items, *, key: str, dry_run: bool = False):
    return artifact_bulk_write(
        items=items,
        dry_run=dry_run,
        repo_root=str(repo),
        idempotency_key=key,
    )


def _bulk_delete_with_key(repo: Path, items, *, key: str, dry_run: bool = False):
    return artifact_bulk_delete(
        items=items,
        dry_run=dry_run,
        repo_root=str(repo),
        idempotency_key=key,
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    root = _repo_root_for(path)
    if root is not None:
        shared_artifact_index(root).apply_file_changes([path])


def _repo_root_for(path: Path) -> Path | None:
    return next((parent for parent in path.parents if parent.name == "architecture-repository"), None)


# ---------------------------------------------------------------------------
# Happy path — entity creates
# ---------------------------------------------------------------------------


class TestBulkCreate:
    def test_single_entity_live(self, repo: Path) -> None:
        results = _bulk(
            repo,
            [
                {"op": "create_entity", "artifact_type": "requirement", "name": "R1"},
            ],
        )
        assert len(results) == 1
        assert results[0]["wrote"] is True
        assert results[0]["op"] == "create_entity"
        assert Path(str(results[0]["path"])).exists()
        registry = ArtifactRegistry(shared_artifact_index(repo))
        assert str(results[0]["artifact_id"]) in registry.entity_ids()

    def test_multiple_entities_live(self, repo: Path) -> None:
        results = _bulk(
            repo,
            [
                {"op": "create_entity", "artifact_type": "requirement", "name": "Ra"},
                {"op": "create_entity", "artifact_type": "outcome", "name": "Ob"},
                {"op": "create_entity", "artifact_type": "goal", "name": "Gc"},
            ],
        )
        assert all(r["wrote"] is True for r in results)
        assert all(Path(str(r["path"])).exists() for r in results)
        registry = ArtifactRegistry(shared_artifact_index(repo))
        for result in results:
            assert str(result["artifact_id"]) in registry.entity_ids()

    def test_dry_run_does_not_write_files(self, repo: Path) -> None:
        results = _bulk(
            repo,
            [
                {"op": "create_entity", "artifact_type": "requirement", "name": "DryR"},
            ],
            dry_run=True,
        )
        assert results[0]["wrote"] is False
        assert not Path(str(results[0]["path"])).exists()

    def test_dry_run_still_assigns_artifact_id(self, repo: Path) -> None:
        results = _bulk(
            repo,
            [
                {"op": "create_entity", "artifact_type": "outcome", "name": "DryId"},
            ],
            dry_run=True,
        )
        assert results[0]["artifact_id"]


# ---------------------------------------------------------------------------
# Field propagation: group / specialization / attribute_types must reach the
# create+edit core exactly as the single-item tools deliver them. Regression for
# the bulk path silently dropping these (group → entity landed in the root model
# dir instead of projects/<group>/; specialization → effective attribute schema
# computed against the wrong profile).
# ---------------------------------------------------------------------------


class TestBulkFieldPropagation:
    def test_create_group_places_entity_under_projects_dir(self, repo: Path) -> None:
        results = _bulk(
            repo,
            [
                {"op": "create_entity", "artifact_type": "requirement", "name": "Grouped", "group": "my-group"},
            ],
        )
        assert results[0]["wrote"] is True, results[0]
        path = str(results[0]["path"])
        assert "projects/my-group/model/motivation/requirement/" in path, path

    def test_create_without_group_stays_in_root_model(self, repo: Path) -> None:
        results = _bulk(
            repo,
            [
                {"op": "create_entity", "artifact_type": "requirement", "name": "Ungrouped"},
            ],
        )
        path = str(results[0]["path"])
        assert "/projects/" not in path, path
        assert "/model/motivation/requirement/" in path, path

    def test_create_specialization_is_persisted(self, repo: Path) -> None:
        results = _bulk(
            repo,
            [
                {
                    "op": "create_entity",
                    "artifact_type": "requirement",
                    "name": "Constrained",
                    "specialization": "constraint",
                },
            ],
        )
        assert results[0]["wrote"] is True, results[0]
        assert "specialization: constraint" in Path(str(results[0]["path"])).read_text()

    def test_edit_applies_specialization(self, repo: Path) -> None:
        eid = _make(repo, "requirement", "To Specialize")
        results = _bulk(
            repo,
            [
                {"op": "edit_entity", "artifact_id": eid, "specialization": "constraint"},
            ],
        )
        assert results[0]["wrote"] is True, results[0]
        assert "specialization: constraint" in Path(str(results[0]["path"])).read_text()


# ---------------------------------------------------------------------------
# $ref substitution
# ---------------------------------------------------------------------------


class TestRefSubstitution:
    def test_ref_creates_connection_between_batch_entities(self, repo: Path) -> None:
        results = _bulk(
            repo,
            [
                {"op": "create_entity", "artifact_type": "goal", "name": "G", "_ref": "g"},
                {"op": "create_entity", "artifact_type": "requirement", "name": "R", "_ref": "r"},
                {
                    "op": "add_connection",
                    "source_entity": "$ref:g",
                    "connection_type": "archimate-influence",
                    "target_entity": "$ref:r",
                },
            ],
        )
        assert all("error" not in res for res in results), results
        assert all(res["wrote"] is True for res in results)

    def test_connection_path_contains_source_entity_id(self, repo: Path) -> None:
        results = _bulk(
            repo,
            [
                {"op": "create_entity", "artifact_type": "goal", "name": "Src", "_ref": "src"},
                {"op": "create_entity", "artifact_type": "outcome", "name": "Tgt", "_ref": "tgt"},
                {
                    "op": "add_connection",
                    "source_entity": "$ref:src",
                    "connection_type": "archimate-influence",
                    "target_entity": "$ref:tgt",
                },
            ],
        )
        src_id = str(results[0]["artifact_id"])
        conn_path = str(results[2]["path"])
        assert src_id in conn_path

    def test_dry_run_ref_is_substituted_even_if_connection_fails_validation(self, repo: Path) -> None:
        """In dry_run, entity creates don't write to disk, so connection validation
        will reject the source as 'not found'. The ref IS substituted though — the error
        mentions the artifact_id, not the literal '$ref:' string."""
        results = _bulk(
            repo,
            [
                {"op": "create_entity", "artifact_type": "driver", "name": "D", "_ref": "d"},
                {
                    "op": "add_connection",
                    "source_entity": "$ref:d",
                    "connection_type": "archimate-association",
                    "target_entity": "$ref:d",
                },
            ],
            dry_run=True,
        )
        assert results[0]["wrote"] is False  # entity dry_run, not written
        # Connection may fail because entity isn't in the model, but ref was resolved
        if "error" in results[1]:
            assert "$ref:" not in cast(str, results[1]["error"]), "ref was not substituted"

    def test_unresolved_ref_returns_error_not_exception(self, repo: Path) -> None:
        results = _bulk(
            repo,
            [
                {
                    "op": "add_connection",
                    "source_entity": "$ref:missing",
                    "connection_type": "archimate-serving",
                    "target_entity": "$ref:also_missing",
                },
            ],
        )
        assert "error" in results[0]
        assert "missing" in cast(str, results[0]["error"])


# ---------------------------------------------------------------------------
# Auto-ordering (connections before entities in input)
# ---------------------------------------------------------------------------


class TestAutoOrdering:
    def test_connection_listed_first_still_resolves(self, repo: Path) -> None:
        results = _bulk(
            repo,
            [
                {
                    "op": "add_connection",
                    "source_entity": "$ref:comp",
                    "connection_type": "archimate-association",
                    "target_entity": "$ref:svc",
                },
                {"op": "create_entity", "artifact_type": "application-component", "name": "Comp", "_ref": "comp"},
                {"op": "create_entity", "artifact_type": "service", "name": "Svc", "_ref": "svc"},
            ],
        )
        assert all("error" not in res for res in results), results
        assert all(res["wrote"] is True for res in results)

    def test_results_maintain_input_order(self, repo: Path) -> None:
        results = _bulk(
            repo,
            [
                {
                    "op": "add_connection",
                    "source_entity": "$ref:g",
                    "connection_type": "archimate-association",
                    "target_entity": "$ref:g",
                },
                {"op": "create_entity", "artifact_type": "goal", "name": "G", "_ref": "g"},
                {"op": "create_entity", "artifact_type": "assessment", "name": "A"},
            ],
        )
        assert results[0]["op"] == "add_connection"
        assert results[1]["op"] == "create_entity"
        assert results[2]["op"] == "create_entity"

    def test_edits_run_after_creates(self, repo: Path) -> None:
        """Edits on pre-existing entities should succeed even when mixed with creates."""
        existing = _make(repo, "requirement", "Pre-existing")
        results = _bulk(
            repo,
            [
                {"op": "edit_entity", "artifact_id": existing, "summary": "Batch edit"},
                {"op": "create_entity", "artifact_type": "outcome", "name": "New"},
            ],
        )
        assert results[0]["op"] == "edit_entity"
        assert results[0]["wrote"] is True
        assert results[1]["op"] == "create_entity"
        assert results[1]["wrote"] is True


# ---------------------------------------------------------------------------
# Content suppression
# ---------------------------------------------------------------------------


class TestContentSuppression:
    def test_no_content_in_dry_run_results(self, repo: Path) -> None:
        results = _bulk(
            repo,
            [
                {"op": "create_entity", "artifact_type": "requirement", "name": "NC"},
            ],
            dry_run=True,
        )
        assert "content" not in results[0]

    def test_no_content_in_live_write_results(self, repo: Path) -> None:
        results = _bulk(
            repo,
            [
                {"op": "create_entity", "artifact_type": "outcome", "name": "NCL"},
            ],
        )
        assert "content" not in results[0]


# ---------------------------------------------------------------------------
# Error handling and isolation
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_unknown_op_returns_error_result(self, repo: Path) -> None:
        results = _bulk(repo, [{"op": "do_magic"}])
        assert "error" in results[0]
        assert results[0]["wrote"] is False

    def test_partial_failure_aborts_batch_without_live_mutation(self, repo: Path) -> None:
        repository = ArtifactRegistry(shared_artifact_index(repo))
        before_ids = repository.entity_ids()
        before_version = shared_artifact_index(repo).read_model_version()

        results = _bulk(
            repo,
            [
                {"op": "create_entity", "artifact_type": "not-a-real-type", "name": "Bad"},
                {"op": "create_entity", "artifact_type": "requirement", "name": "Good"},
            ],
        )
        assert "error" in results[0] or results[0]["wrote"] is False
        assert results[1]["wrote"] is False
        assert "Skipped because an earlier batch item failed" in cast(str, results[1]["error"])
        assert not list((repo / "model").rglob("*.md"))

        registry = ArtifactRegistry(shared_artifact_index(repo))
        after_version = shared_artifact_index(repo).read_model_version()
        assert registry.entity_ids() == before_ids
        assert after_version == before_version

    def test_missing_required_name_field_returns_error(self, repo: Path) -> None:
        results = _bulk(
            repo,
            [
                {"op": "create_entity", "artifact_type": "requirement"},  # missing name
            ],
        )
        assert "error" in results[0]

    def test_connection_to_nonexistent_entity_fails_gracefully(self, repo: Path) -> None:
        results = _bulk(
            repo,
            [
                {
                    "op": "add_connection",
                    "source_entity": "REQ@0000000000.XXXXXX.ghost",
                    "connection_type": "archimate-realization",
                    "target_entity": "OUT@0000000000.YYYYYY.ghost",
                },
            ],
        )
        assert "error" in results[0] or results[0]["wrote"] is False

    def test_failed_create_ref_causes_connection_error(self, repo: Path) -> None:
        """$ref: from a failed create has no ID to resolve — connection must error."""
        results = _bulk(
            repo,
            [
                {"op": "create_entity", "artifact_type": "bad-type", "name": "Bad", "_ref": "bad"},
                {
                    "op": "add_connection",
                    "source_entity": "$ref:bad",
                    "connection_type": "archimate-serving",
                    "target_entity": "$ref:bad",
                },
            ],
        )
        assert "error" in results[0] or results[0]["wrote"] is False
        assert "error" in results[1]

    def test_edit_nonexistent_entity_returns_error(self, repo: Path) -> None:
        results = _bulk(
            repo,
            [
                {"op": "edit_entity", "artifact_id": "REQ@9999999999.NoExist.ghost", "summary": "Should fail"},
            ],
        )
        assert "error" in results[0]


# ---------------------------------------------------------------------------
# Edit operations
# ---------------------------------------------------------------------------


class TestBulkEdits:
    def test_edit_entity_summary(self, repo: Path) -> None:
        eid = _make(repo, "requirement", "Before Edit")
        results = _bulk(
            repo,
            [
                {"op": "edit_entity", "artifact_id": eid, "summary": "Updated via bulk"},
            ],
        )
        assert results[0]["wrote"] is True
        assert "Updated via bulk" in Path(str(results[0]["path"])).read_text()

    def test_remove_connection(self, repo: Path) -> None:
        src = _make(repo, "goal", "RemSrc")
        tgt = _make(repo, "requirement", "RemTgt")
        _connect(repo, src, tgt, "archimate-influence")
        results = _bulk(
            repo,
            [
                {
                    "op": "edit_connection",
                    "source_entity": src,
                    "target_entity": tgt,
                    "connection_type": "archimate-influence",
                    "operation": "remove",
                },
            ],
        )
        assert results[0]["wrote"] is True

    def test_dry_run_edit_does_not_write(self, repo: Path) -> None:
        eid = _make(repo, "outcome", "Dry Edit")
        results = _bulk(
            repo,
            [
                {"op": "edit_entity", "artifact_id": eid, "summary": "Not written"},
            ],
            dry_run=True,
        )
        assert results[0]["wrote"] is False
        assert "Not written" not in Path(str(results[0]["path"])).read_text()

    def test_edit_entity_group_relocates_file(self, repo: Path) -> None:
        """Regression: the bulk edit_entity op previously dropped `group`, so
        a batch group re-home (as WU-C3's mass re-grouping relies on) silently
        no-opped despite reporting wrote=True."""
        eid = _make(repo, "requirement", "Group Me")
        old_path = Path(str(mcp.artifact_edit_entity(artifact_id=eid, dry_run=True, repo_root=str(repo))["path"]))
        assert old_path.exists()

        results = _bulk(
            repo,
            [
                {"op": "edit_entity", "artifact_id": eid, "group": "my-collection"},
            ],
        )

        assert results[0]["wrote"] is True
        new_path = Path(str(results[0]["path"]))
        assert "my-collection" in new_path.parts
        assert new_path.exists()
        assert not old_path.exists()


# ---------------------------------------------------------------------------
# Conflict and dependency scenarios
# ---------------------------------------------------------------------------


class TestConflictsAndDependencies:
    def test_duplicate_connection_second_is_idempotent_or_errors(self, repo: Path) -> None:
        src = _make(repo, "requirement", "DupSrc")
        tgt = _make(repo, "outcome", "DupTgt")
        results = _bulk(
            repo,
            [
                {
                    "op": "add_connection",
                    "source_entity": src,
                    "connection_type": "archimate-realization",
                    "target_entity": tgt,
                },
                {
                    "op": "add_connection",
                    "source_entity": src,
                    "connection_type": "archimate-realization",
                    "target_entity": tgt,
                },
            ],
        )
        assert len(results) == 2
        # The first item succeeded during staging but the batch aborted because the
        # second (duplicate) item failed — it must carry a reason, not a bare
        # wrote:False that is indistinguishable from "never attempted".
        assert results[0]["wrote"] is False
        assert "error" in results[0]
        assert "already exists" not in results[0]["error"]
        assert "error" in results[1]
        assert "already exists" in results[1]["error"]

        outgoing = Path(str(results[0]["path"]))
        if outgoing.exists():
            assert "archimate-realization" not in outgoing.read_text(encoding="utf-8")

    def test_earlier_batch_item_reports_rollback_reason_not_bare_wrote_false(self, repo: Path) -> None:
        """Regression for the item that *succeeded* during staging before a later
        item failed: it must not look identical to an item that was never attempted
        (skipped_result) or one that itself failed (error_result)."""
        src = _make(repo, "requirement", "RollbackSrc")
        tgt = _make(repo, "outcome", "RollbackTgt")
        other_tgt = _make(repo, "outcome", "RollbackTgt2")
        results = _bulk(
            repo,
            [
                {
                    "op": "add_connection",
                    "source_entity": src,
                    "connection_type": "archimate-realization",
                    "target_entity": tgt,
                },
                {
                    "op": "add_connection",
                    "source_entity": src,
                    "connection_type": "archimate-realization",
                    "target_entity": other_tgt,
                },
                {
                    "op": "add_connection",
                    "source_entity": src,
                    "connection_type": "archimate-realization",
                    "target_entity": tgt,
                },
            ],
        )
        assert len(results) == 3
        assert results[0]["wrote"] is False
        assert results[0]["error"] == "Rolled back: a later item in this batch failed, so no changes were committed"
        assert results[1]["wrote"] is False
        assert results[1]["error"] == "Rolled back: a later item in this batch failed, so no changes were committed"
        assert "already exists" in results[2]["error"]

    def test_same_ref_used_in_multiple_connections(self, repo: Path) -> None:
        """One entity can be both source and target of multiple connections via the same ref."""
        results = _bulk(
            repo,
            [
                {"op": "create_entity", "artifact_type": "driver", "name": "Hub", "_ref": "hub"},
                {"op": "create_entity", "artifact_type": "assessment", "name": "A1", "_ref": "a1"},
                {"op": "create_entity", "artifact_type": "assessment", "name": "A2", "_ref": "a2"},
                {
                    "op": "add_connection",
                    "source_entity": "$ref:hub",
                    "connection_type": "archimate-association",
                    "target_entity": "$ref:a1",
                },
                {
                    "op": "add_connection",
                    "source_entity": "$ref:hub",
                    "connection_type": "archimate-association",
                    "target_entity": "$ref:a2",
                },
            ],
        )
        assert all("error" not in res for res in results), results
        assert all(res["wrote"] is True for res in results)

    def test_unrelated_broken_diagram_does_not_block_impacted_bulk_write(self, repo: Path) -> None:
        _write(
            repo / "diagram-catalog" / "diagrams" / "broken-unrelated.puml",
            """\
---
artifact-id: broken-unrelated
artifact-type: diagram
diagram-type: archimate-application
name: "Broken Unrelated"
version: 0.1.0
status: draft
last-updated: '2026-04-28'
---
@startuml
this is not valid plantuml
@enduml
""",
        )

        results = _bulk(
            repo,
            [
                {"op": "create_entity", "artifact_type": "requirement", "name": "Independent"},
            ],
        )

        assert len(results) == 1
        assert results[0]["wrote"] is True

    def test_preexisting_broken_diagram_referencing_changed_entity_does_not_block_write(self, repo: Path) -> None:
        """Regression: a diagram that already references the modified entity AND is
        already broken (references a ghost entity) must not block the batch.

        The impacted-scope verifier pulls the diagram in because it uses the entity
        being edited.  Without the pre-existing check the batch fails even though
        *it* did not break the diagram.

        The batch should succeed (wrote=True) while the broken diagram still
        appears as an invalid result in the batch_verification payload.
        """
        eid = _make(repo, "requirement", "TouchedEntity")

        # Write a diagram that (a) references the entity we will edit and
        # (b) is already broken because it also references a ghost entity.
        ghost = "REQ@0000000000.XXXXXX.ghost-entity"
        diag_id = "broken-references-changed-entity"
        _write(
            repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml",
            f"""\
---
artifact-id: {diag_id}
artifact-type: diagram
diagram-type: archimate-application
name: "Broken references changed entity"
entity-ids-used:
  - {eid}
  - {ghost}
version: 0.1.0
status: draft
last-updated: '2026-04-28'
---
@startuml
Alice -> Bob
@enduml
""",
        )

        # Edit the entity — the diagram is in the impacted scope.
        results = _bulk(
            repo,
            [
                {"op": "edit_entity", "artifact_id": eid, "summary": "Touched by batch"},
            ],
        )

        assert len(results) == 1
        assert results[0]["wrote"] is True, (
            "Batch was blocked by a pre-existing broken diagram that referenced the "
            "changed entity — the pre-existing invalidity must not block the commit."
        )

    def test_large_batch_all_succeed(self, repo: Path) -> None:
        """Batches larger than the old 8-item parallel limit should complete correctly."""
        items = [
            {"op": "create_entity", "artifact_type": "requirement", "name": f"Req{i}", "_ref": f"r{i}"}
            for i in range(12)
        ]
        items += [
            {
                "op": "add_connection",
                "source_entity": f"$ref:r{i}",
                "connection_type": "archimate-association",
                "target_entity": f"$ref:r{(i + 1) % 12}",
            }
            for i in range(12)
        ]
        results = _bulk(repo, items)
        assert len(results) == 24
        errors = [r for r in results if "error" in r]
        assert not errors, errors

    def test_load_style_batch_commits_and_indexes_consistently(self, repo: Path) -> None:
        items = [
            {"op": "create_entity", "artifact_type": "requirement", "name": f"LoadReq{i}", "_ref": f"r{i}"}
            for i in range(24)
        ]
        items += [
            {
                "op": "add_connection",
                "source_entity": f"$ref:r{i}",
                "connection_type": "archimate-association",
                "target_entity": f"$ref:r{(i + 1) % 24}",
            }
            for i in range(24)
        ]

        before = shared_artifact_index(repo).read_model_version()
        results = _bulk(repo, items)
        after = shared_artifact_index(repo).read_model_version()

        assert all("error" not in r for r in results), results
        assert all(r["wrote"] is True for r in results)
        assert after.generation > before.generation

        registry = ArtifactRegistry(shared_artifact_index(repo))
        for result in results[:24]:
            assert str(result["artifact_id"]) in registry.entity_ids()

    def test_staged_bulk_write_publishes_only_live_paths(self, repo: Path) -> None:
        events: list[AuthoritativeIndexMutationCommitted] = []
        unsubscribe = event_bus.subscribe(AuthoritativeIndexMutationCommitted, events.append)
        try:
            results = _bulk(
                repo,
                [
                    {"op": "create_entity", "artifact_type": "requirement", "name": "LiveOnly"},
                ],
            )
        finally:
            unsubscribe()

        assert results[0]["wrote"] is True
        assert events, "expected an authoritative mutation event"
        assert all(str(path).startswith(str(repo)) for event in events for path in event.changed_paths)
        assert all("/tmp/artifact-batch-" not in path for event in events for path in event.changed_paths)

    def test_failed_staged_bulk_write_emits_no_authoritative_mutation(self, repo: Path) -> None:
        events: list[AuthoritativeIndexMutationCommitted] = []
        unsubscribe = event_bus.subscribe(AuthoritativeIndexMutationCommitted, events.append)
        try:
            _bulk(
                repo,
                [
                    {"op": "create_entity", "artifact_type": "bad-type", "name": "Bad"},
                    {"op": "create_entity", "artifact_type": "requirement", "name": "Skipped"},
                ],
            )
        finally:
            unsubscribe()

        assert events == []

    def test_staged_bulk_write_verification_does_not_persist_incremental_state(
        self,
        repo: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_dir = tmp_path / "verifier-state"
        monkeypatch.setenv("ARCH_MODEL_VERIFY_STATE_DIR", str(state_dir))

        results = _bulk(
            repo,
            [
                {"op": "create_entity", "artifact_type": "requirement", "name": "NoVerifierState"},
            ],
        )

        assert results[0]["wrote"] is True
        assert not state_dir.exists() or not list(state_dir.rglob("*"))

    def test_bulk_write_auto_sync_updates_diagram_after_entity_rename(self, repo: Path) -> None:
        src = _make(repo, "requirement", "RenameSrc")
        tgt = _make(repo, "outcome", "RenameTgt")
        _connect(repo, src, tgt, "archimate-realization")
        diag_id = "bulk-write-rename-sync"
        _write(
            repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml",
            f"""\
---
artifact-id: {diag_id}
artifact-type: diagram
diagram-type: archimate-application
name: "Bulk Write Rename Sync"
entity-ids-used:
  - {src}
  - {tgt}
connection-ids-used:
  - {src}---{tgt}@@archimate-realization
version: 0.1.0
status: active
last-updated: '2026-04-28'
---
@startuml
Alice -> Bob
@enduml
""",
        )

        results = _bulk(
            repo,
            [{"op": "edit_entity", "artifact_id": src, "name": "Renamed Src"}],
            auto_sync_diagrams=True,
        )

        new_src = str(results[0]["artifact_id"])
        text = (repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml").read_text(encoding="utf-8")
        assert results[0]["wrote"] is True
        assert new_src in text
        assert src not in text
        assert f"{stable_id(new_src)}---{stable_id(tgt)}@@archimate-realization" in text

    def test_bulk_write_auto_sync_updates_diagram_after_connection_remove(self, repo: Path) -> None:
        src = _make(repo, "requirement", "ConnRemoveSrc")
        tgt = _make(repo, "outcome", "ConnRemoveTgt")
        _connect(repo, src, tgt, "archimate-realization")
        diag_id = "bulk-write-connection-sync"
        _write(
            repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml",
            f"""\
---
artifact-id: {diag_id}
artifact-type: diagram
diagram-type: archimate-application
name: "Bulk Write Connection Sync"
entity-ids-used:
  - {src}
  - {tgt}
connection-ids-used:
  - {src}---{tgt}@@archimate-realization
version: 0.1.0
status: active
last-updated: '2026-04-28'
---
@startuml
Alice -> Bob
@enduml
""",
        )

        results = _bulk(
            repo,
            [
                {
                    "op": "edit_connection",
                    "source_entity": src,
                    "target_entity": tgt,
                    "connection_type": "archimate-realization",
                    "operation": "remove",
                }
            ],
            auto_sync_diagrams=True,
        )

        text = (repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml").read_text(encoding="utf-8")
        assert results[0]["wrote"] is True
        assert f"{src}---{tgt}@@archimate-realization" not in text


class TestBulkOperationTracking:
    def test_bulk_write_result_is_queryable_by_operation_id(self, repo: Path) -> None:
        results = _bulk(
            repo,
            [
                {"op": "create_entity", "artifact_type": "requirement", "name": "Tracked"},
            ],
        )

        operation_id = cast(str, results[0]["operation_id"])
        operation = artifact_get_operation(operation_id=operation_id)

        assert operation["operation_id"] == operation_id
        assert operation["tool_name"] == "artifact_bulk_write"
        assert operation["status"] == "completed"
        assert operation["phase"] == "done"
        assert cast(list[dict[str, Any]], operation["result"])[0]["operation_id"] == operation_id

    def test_bulk_write_idempotency_key_reuses_completed_result(self, repo: Path) -> None:
        key = "bulk-write-idempotent-1"
        before = shared_artifact_index(repo).read_model_version()

        first = _bulk_with_key(
            repo,
            [{"op": "create_entity", "artifact_type": "requirement", "name": "Once"}],
            key=key,
        )
        mid = shared_artifact_index(repo).read_model_version()
        second = _bulk_with_key(
            repo,
            [{"op": "create_entity", "artifact_type": "requirement", "name": "Once"}],
            key=key,
        )
        after = shared_artifact_index(repo).read_model_version()

        assert first == second
        assert mid.generation > before.generation
        assert after == mid

        registry = ArtifactRegistry(shared_artifact_index(repo))
        assert len(registry.entity_ids()) == 1

    def test_bulk_delete_idempotency_key_reuses_completed_result(self, repo: Path) -> None:
        eid = _make(repo, "requirement", "Delete Once")
        key = "bulk-delete-idempotent-1"
        before = shared_artifact_index(repo).read_model_version()

        first = _bulk_delete_with_key(
            repo,
            [{"op": "delete_entity", "artifact_id": eid}],
            key=key,
        )
        mid = shared_artifact_index(repo).read_model_version()
        second = _bulk_delete_with_key(
            repo,
            [{"op": "delete_entity", "artifact_id": eid}],
            key=key,
        )
        after = shared_artifact_index(repo).read_model_version()

        assert first == second
        assert mid.generation > before.generation
        assert after == mid

        registry = ArtifactRegistry(shared_artifact_index(repo))
        assert eid not in registry.entity_ids()


# ---------------------------------------------------------------------------
# Bulk delete
# ---------------------------------------------------------------------------


class TestBulkDelete:
    def test_delete_connection_document_diagram_and_entity_batch(self, repo: Path) -> None:
        src = _make(repo, "requirement", "DeleteSrc")
        tgt = _make(repo, "outcome", "DeleteTgt")
        _connect(repo, src, tgt, "archimate-realization")

        doc_id = "ADR@1000000001.AbcDef.to-delete"
        _write(
            repo / "docs" / "adr" / f"{doc_id}.md",
            """\
---
artifact-id: ADR@1000000001.AbcDef.to-delete
artifact-type: document
doc-type: adr
title: "Delete Me"
status: draft
version: 0.1.0
last-updated: '2026-04-27'
---

## Context

Delete me.
""",
        )

        diag_id = "bulk-delete-diagram"
        diag_path = repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml"
        _write(
            diag_path,
            f"""\
---
artifact-id: {diag_id}
artifact-type: diagram
diagram-type: archimate-application
name: "Bulk Delete Diagram"
entity-ids-used:
  - {src}
connection-ids-used:
  - {src} archimate-realization → {tgt}
version: 0.1.0
status: active
last-updated: '2026-04-27'
---
@startuml
Alice -> Bob
@enduml
""",
        )
        _write(repo / "diagram-catalog" / "rendered" / f"{diag_id}.png", "png")

        payload = _bulk_delete(
            repo,
            [
                {
                    "op": "delete_connection",
                    "source_entity": src,
                    "connection_type": "archimate-realization",
                    "target_entity": tgt,
                },
                {"op": "delete_document", "artifact_id": doc_id},
                {"op": "delete_diagram", "artifact_id": diag_id},
                {"op": "delete_entity", "artifact_id": src},
                {"op": "delete_entity", "artifact_id": tgt},
            ],
        )

        results = cast(list[dict[str, Any]], payload["results"])
        assert all("error" not in item for item in results), payload
        assert all(item["wrote"] is True for item in results)
        assert cast(dict[str, Any], payload["batch_verification"])["valid"] is True

        verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())
        assert all(r.valid for r in verifier.verify_all(repo)), "repo should verify after batch delete"

    def test_delete_entity_requires_diagram_delete_in_same_batch(self, repo: Path) -> None:
        eid = _make(repo, "requirement", "DiagramBlocked")
        diag_id = "diagram-blocker"
        _write(
            repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml",
            f"""\
---
artifact-id: {diag_id}
artifact-type: diagram
diagram-type: archimate-application
name: "Diagram Blocker"
entity-ids-used:
  - {eid}
version: 0.1.0
status: active
last-updated: '2026-04-27'
---
@startuml
Alice -> Bob
@enduml
""",
        )

        payload = _bulk_delete(repo, [{"op": "delete_entity", "artifact_id": eid}], dry_run=True)
        assert cast(dict[str, Any], payload["batch_verification"])["valid"] is False
        assert "diagram must also be deleted" in cast(str, cast(list[dict[str, Any]], payload["results"])[0]["error"])

    def test_delete_connection_requires_diagram_delete_in_same_batch(self, repo: Path) -> None:
        src = _make(repo, "requirement", "ConnDiagramSrc")
        tgt = _make(repo, "outcome", "ConnDiagramTgt")
        _connect(repo, src, tgt, "archimate-realization")
        diag_id = "connection-diagram-blocker"
        _write(
            repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml",
            f"""\
---
artifact-id: {diag_id}
artifact-type: diagram
diagram-type: archimate-application
name: "Connection Diagram Blocker"
connection-ids-used:
  - {src} archimate-realization → {tgt}
version: 0.1.0
status: active
last-updated: '2026-04-28'
---
@startuml
Alice -> Bob
@enduml
""",
        )

        payload = _bulk_delete(
            repo,
            [
                {
                    "op": "delete_connection",
                    "source_entity": src,
                    "connection_type": "archimate-realization",
                    "target_entity": tgt,
                }
            ],
            dry_run=True,
        )
        assert cast(dict[str, Any], payload["batch_verification"])["valid"] is False
        assert "diagram must also be deleted" in cast(str, cast(list[dict[str, Any]], payload["results"])[0]["error"])

    def test_bulk_delete_auto_sync_updates_diagram_after_connection_delete(self, repo: Path) -> None:
        src = _make(repo, "requirement", "AutoSyncConnSrc")
        tgt = _make(repo, "outcome", "AutoSyncConnTgt")
        _connect(repo, src, tgt, "archimate-realization")
        diag_id = "bulk-delete-auto-sync-connection"
        _write(
            repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml",
            f"""\
---
artifact-id: {diag_id}
artifact-type: diagram
diagram-type: archimate-application
name: "Bulk Delete Auto Sync Connection"
entity-ids-used:
  - {src}
  - {tgt}
connection-ids-used:
  - {src}---{tgt}@@archimate-realization
version: 0.1.0
status: active
last-updated: '2026-04-28'
---
@startuml
Alice -> Bob
@enduml
""",
        )

        payload = _bulk_delete(
            repo,
            [
                {
                    "op": "delete_connection",
                    "source_entity": src,
                    "connection_type": "archimate-realization",
                    "target_entity": tgt,
                }
            ],
            auto_sync_diagrams=True,
        )

        results = cast(list[dict[str, Any]], payload["results"])
        text = (repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml").read_text(encoding="utf-8")
        assert all("error" not in item for item in results), payload
        assert f"{src}---{tgt}@@archimate-realization" not in text
        actions = cast(
            list[dict[str, Any]],
            cast(dict[str, Any], payload["batch_verification"])["auto_synced_diagrams"],
        )
        assert actions and actions[0]["artifact_id"] == diag_id

    def test_bulk_delete_auto_sync_preserves_now_empty_diagram(self, repo: Path) -> None:
        # Refresh-never-deletes: when all entity refs become unresolved, the diagram
        # is preserved (not silently deleted) so authors can decide what to do with it.
        eid = _make(repo, "requirement", "AutoSyncPreserveMe")
        diag_id = "bulk-delete-auto-sync-empty"
        _write(
            repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml",
            f"""\
---
artifact-id: {diag_id}
artifact-type: diagram
diagram-type: archimate-application
name: "Bulk Delete Auto Sync Empty"
entity-ids-used:
  - {eid}
version: 0.1.0
status: active
last-updated: '2026-04-28'
---
@startuml
Alice
@enduml
""",
        )

        payload = _bulk_delete(
            repo,
            [{"op": "delete_entity", "artifact_id": eid}],
            auto_sync_diagrams=True,
        )

        results = cast(list[dict[str, Any]], payload["results"])
        assert all("error" not in item for item in results), payload
        # Diagram is preserved on disk — authors must explicitly delete it
        assert (repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml").exists()
        actions = cast(
            list[dict[str, Any]],
            cast(dict[str, Any], payload["batch_verification"])["auto_synced_diagrams"],
        )
        assert actions and actions[0]["deleted_diagram"] is False

    def test_delete_entities_with_internal_cycle_succeeds_via_implicit_connection_cleanup(self, repo: Path) -> None:
        left = _make(repo, "goal", "Left")
        right = _make(repo, "requirement", "Right")
        _connect(repo, left, right, "archimate-influence")
        _connect(repo, right, left, "archimate-association")

        payload = _bulk_delete(
            repo,
            [
                {"op": "delete_entity", "artifact_id": left},
                {"op": "delete_entity", "artifact_id": right},
            ],
        )

        results = cast(list[dict[str, Any]], payload["results"])
        assert all("error" not in item for item in results), payload
        implicit = cast(
            list[dict[str, Any]],
            cast(dict[str, Any], payload["batch_verification"])["implicit_connection_deletes"],
        )
        assert len(implicit) == 2
        assert cast(dict[str, Any], payload["batch_verification"])["valid"] is True

    def test_delete_entity_blocked_by_external_incoming_connection(self, repo: Path) -> None:
        src = _make(repo, "goal", "ExternalSrc")
        tgt = _make(repo, "requirement", "BlockedTgt")
        _connect(repo, src, tgt, "archimate-influence")

        payload = _bulk_delete(
            repo,
            [{"op": "delete_entity", "artifact_id": tgt}],
            dry_run=True,
        )

        assert cast(dict[str, Any], payload["batch_verification"])["valid"] is False
        assert "incoming connection must also be deleted" in cast(
            str, cast(list[dict[str, Any]], payload["results"])[0]["error"]
        )

    def test_unrelated_broken_diagram_does_not_block_impacted_bulk_delete(self, repo: Path) -> None:
        eid = _make(repo, "requirement", "DeleteMe")
        _write(
            repo / "diagram-catalog" / "diagrams" / "broken-unrelated-delete.puml",
            """\
---
artifact-id: broken-unrelated-delete
artifact-type: diagram
diagram-type: archimate-application
name: "Broken Unrelated Delete"
version: 0.1.0
status: draft
last-updated: '2026-04-28'
---
@startuml
this is not valid plantuml
@enduml
""",
        )

        payload = _bulk_delete(
            repo,
            [{"op": "delete_entity", "artifact_id": eid}],
        )

        results = cast(list[dict[str, Any]], payload["results"])
        assert len(results) == 1
        assert results[0]["wrote"] is True

    def test_preexisting_broken_diagram_referencing_deleted_entity_does_not_block_delete(self, repo: Path) -> None:
        """Regression: deleting an entity that a pre-existing broken diagram also
        references must not block the batch (auto_sync_diagrams=True removes the
        reference; without auto-sync the diagram is a neighbour pulled into impacted
        scope but its prior invalidity must not block the commit).

        We use auto_sync_diagrams=True so the diagram is cleaned up and the
        structural delete succeeds; the pre-existing ghost-entity reference error
        is what we are testing does not block.
        """
        eid = _make(repo, "requirement", "DeleteTouchedEntity")
        ghost = "REQ@0000000000.YYYYYY.ghost-entity"
        diag_id = "broken-references-deleted-entity"
        _write(
            repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml",
            f"""\
---
artifact-id: {diag_id}
artifact-type: diagram
diagram-type: archimate-application
name: "Broken references deleted entity"
entity-ids-used:
  - {eid}
  - {ghost}
version: 0.1.0
status: draft
last-updated: '2026-04-28'
---
@startuml
Alice -> Bob
@enduml
""",
        )

        payload = _bulk_delete(
            repo,
            [{"op": "delete_entity", "artifact_id": eid}],
            auto_sync_diagrams=True,
        )

        results = cast(list[dict[str, Any]], payload["results"])
        assert len(results) == 1
        assert results[0]["wrote"] is True, (
            "Batch was blocked by a pre-existing broken diagram that referenced the "
            "deleted entity — the pre-existing invalidity must not block the commit."
        )

    def test_staged_bulk_delete_publishes_only_live_paths(self, repo: Path) -> None:
        eid = _make(repo, "requirement", "DeleteLiveOnly")
        events: list[AuthoritativeIndexMutationCommitted] = []
        unsubscribe = event_bus.subscribe(AuthoritativeIndexMutationCommitted, events.append)
        try:
            payload = _bulk_delete(repo, [{"op": "delete_entity", "artifact_id": eid}])
        finally:
            unsubscribe()

        results = cast(list[dict[str, Any]], payload["results"])
        assert results[0]["wrote"] is True
        assert len(events) == 1
        assert all(str(path).startswith(str(repo)) for event in events for path in event.changed_paths)
        assert all("/tmp/artifact-batch-" not in path for event in events for path in event.changed_paths)

    def test_failed_staged_bulk_delete_emits_no_authoritative_mutation(self, repo: Path) -> None:
        eid = _make(repo, "requirement", "DeleteFail")
        doc_id = "ADR@1000000002.FailDoc.to-delete"
        doc_path = repo / "docs" / "adr" / f"{doc_id}.md"
        _write(
            doc_path,
            """\
---
artifact-id: ADR@1000000002.FailDoc.to-delete
artifact-type: document
doc-type: adr
title: "Delete Fail"
status: draft
version: 0.1.0
last-updated: '2026-04-28'
---

## Context

Delete me.
""",
        )
        events: list[AuthoritativeIndexMutationCommitted] = []
        unsubscribe = event_bus.subscribe(AuthoritativeIndexMutationCommitted, events.append)
        original = artifact_write_ops.delete_document

        def fail_delete_document(*args: Any, **kwargs: Any):
            raise RuntimeError("forced staged delete failure")

        try:
            artifact_write_ops.delete_document = fail_delete_document
            payload = _bulk_delete(
                repo,
                [
                    {"op": "delete_entity", "artifact_id": eid},
                    {"op": "delete_document", "artifact_id": doc_id},
                ],
            )
        finally:
            artifact_write_ops.delete_document = original
            unsubscribe()

        results = cast(list[dict[str, Any]], payload["results"])
        assert "error" in results[1]
        assert events == []
        assert eid in ArtifactRegistry(shared_artifact_index(repo)).entity_ids()
        assert doc_path.exists()

    def test_staged_bulk_delete_verification_does_not_persist_incremental_state(
        self,
        repo: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        eid = _make(repo, "requirement", "DeleteNoVerifierState")
        state_dir = tmp_path / "verifier-state"
        monkeypatch.setenv("ARCH_MODEL_VERIFY_STATE_DIR", str(state_dir))

        payload = _bulk_delete(repo, [{"op": "delete_entity", "artifact_id": eid}])

        results = cast(list[dict[str, Any]], payload["results"])
        assert results[0]["wrote"] is True
        assert not state_dir.exists() or not list(state_dir.rglob("*"))
