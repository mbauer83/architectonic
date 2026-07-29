"""Tests for WS2 — index identity multimap and canonical artifact resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import pytest

from src.application.ports import AmbiguousArtifactError, Candidate
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.infrastructure.artifact_index._identity_resolver import _IdentityResolver
from src.infrastructure.artifact_index._mem_store import _MemStore
from src.infrastructure.artifact_index._rwlock import _RWLock
from src.infrastructure.artifact_index._service_scan import _insert_mounted
from src.infrastructure.artifact_index.service import ArtifactIndex

# ── Helpers ───────────────────────────────────────────────────────────────────


def _entity_rec(artifact_id: str, path: Path) -> EntityRecord:
    """Minimal EntityRecord stub — only artifact_id and path are consulted."""
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type="requirement",
        name="Test",
        version="0.1.0",
        status="draft",
        domain="motivation",
        subdomain="req",
        path=path,
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label="",
        display_alias="",
    )


# ── Unit: _MemStore identity_candidates populated by _insert_mounted ──────────


class TestIdentityCandidatesMultimap:
    def test_single_entity_recorded(self, tmp_path: Path) -> None:
        mem = _MemStore()
        p = tmp_path / "REQ@1000.AAA.my-slug.md"
        p.touch()
        rec = _entity_rec("REQ@1000.AAA.my-slug", p)
        _insert_mounted(
            rec, "entity", tmp_path, mem.entities,
            candidates_map=mem.identity_candidates, scope="engagement",
        )
        assert "REQ@1000.AAA" in mem.identity_candidates
        assert len(mem.identity_candidates["REQ@1000.AAA"]) == 1
        assert mem.identity_candidates["REQ@1000.AAA"][0].artifact_id == "REQ@1000.AAA.my-slug"

    def test_slug_drift_both_candidates_recorded(self, tmp_path: Path) -> None:
        """Both old and new slug files are recorded even though only one wins the store."""
        mem = _MemStore()
        old_path = tmp_path / "REQ@1000.AAA.old-slug.md"
        new_path = tmp_path / "REQ@1000.AAA.new-slug.md"
        old_path.touch()
        new_path.touch()
        old_rec = _entity_rec("REQ@1000.AAA.old-slug", old_path)
        new_rec = _entity_rec("REQ@1000.AAA.new-slug", new_path)
        # First insert wins the store but both must be in identity_candidates
        _insert_mounted(
            old_rec, "entity", tmp_path, mem.entities,
            candidates_map=mem.identity_candidates, scope="engagement",
        )
        _insert_mounted(
            new_rec, "entity", tmp_path, mem.entities,
            candidates_map=mem.identity_candidates, scope="engagement",
        )
        candidates = mem.identity_candidates.get("REQ@1000.AAA", [])
        artifact_ids = {c.artifact_id for c in candidates}
        assert "REQ@1000.AAA.old-slug" in artifact_ids
        assert "REQ@1000.AAA.new-slug" in artifact_ids

    def test_cross_mount_candidates_accumulated(self, tmp_path: Path) -> None:
        mem = _MemStore()
        mount_eng = tmp_path / "eng"
        mount_ent = tmp_path / "ent"
        p_eng = mount_eng / "REQ@1000.AAA.slug.md"
        p_ent = mount_ent / "REQ@1000.AAA.slug.md"
        p_eng.parent.mkdir()
        p_eng.touch()
        p_ent.parent.mkdir()
        p_ent.touch()
        _insert_mounted(
            _entity_rec("REQ@1000.AAA.slug", p_eng), "entity", mount_eng, mem.entities,
            candidates_map=mem.identity_candidates, scope="engagement",
        )
        _insert_mounted(
            _entity_rec("REQ@1000.AAA.slug", p_ent), "entity", mount_ent, mem.entities,
            candidates_map=mem.identity_candidates, scope="enterprise",
        )
        candidates = mem.identity_candidates["REQ@1000.AAA"]
        assert len(candidates) == 2
        scopes = {c.scope for c in candidates}
        assert scopes == {"engagement", "enterprise"}

    def test_no_candidates_without_map(self, tmp_path: Path) -> None:
        mem = _MemStore()
        p = tmp_path / "REQ@1000.AAA.slug.md"
        p.touch()
        rec = _entity_rec("REQ@1000.AAA.slug", p)
        _insert_mounted(rec, "entity", tmp_path, mem.entities)  # no candidates_map
        assert "REQ@1000.AAA" not in mem.identity_candidates

    def test_clear_resets_candidates(self, tmp_path: Path) -> None:
        mem = _MemStore()
        p = tmp_path / "REQ@1000.AAA.s.md"
        p.touch()
        _insert_mounted(
            _entity_rec("REQ@1000.AAA.s", p), "entity", tmp_path, mem.entities,
            candidates_map=mem.identity_candidates, scope="engagement",
        )
        assert mem.identity_candidates
        mem.clear()
        assert not mem.identity_candidates


def test_reconcile_includes_missing_indexed_path_for_eviction(tmp_path: Path) -> None:
    model_root = tmp_path / "model" / "motivation" / "requirement"
    model_root.mkdir(parents=True)
    old_path = model_root / "REQ@1000.AAA.old.md"
    new_path = model_root / "REQ@1000.AAA.current.md"
    new_path.touch()
    mem = _MemStore()
    mem.identity_candidates["REQ@1000.AAA"] = [
        Candidate(
            artifact_id="REQ@1000.AAA.old",
            path=old_path,
            scope="engagement",
        )
    ]
    applied: list[Path] = []
    resolver = _IdentityResolver(
        mem,
        _RWLock(),
        lambda: None,
        lambda _path: "engagement",
    )

    resolver.reconcile_short_id(
        "REQ@1000.AAA",
        lambda paths: applied.extend(paths),
        [tmp_path],
    )

    assert applied == [old_path, new_path]


def test_full_refresh_publishes_identity_candidates(tmp_path: Path) -> None:
    path = tmp_path / "model" / "motivation" / "requirement" / "REQ@1000.AAA.current.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\n"
        "artifact-id: REQ@1000.AAA.current\n"
        "artifact-type: requirement\n"
        "name: Current\n"
        "version: 0.1.0\n"
        "status: draft\n"
        "---\n",
        encoding="utf-8",
    )
    index = ArtifactIndex(tmp_path)

    index.refresh()

    candidates = index.find_all_by_stable_id("REQ@1000.AAA")
    assert [(candidate.artifact_id, candidate.path) for candidate in candidates] == [
        ("REQ@1000.AAA.current", path)
    ]


# ── Unit: ArtifactRegistry.resolve_artifact via fake store ────────────────────


@dataclass
class _FakeStore:
    """Minimal VerifierStorePort stub for resolve_artifact tests."""

    _entities: dict[str, EntityRecord] = field(default_factory=dict)
    _paths: dict[str, Path] = field(default_factory=dict)
    _candidates: dict[str, list[Candidate]] = field(default_factory=dict)
    _reconcile_called: list[str] = field(default_factory=list)

    @property
    def repo_roots(self) -> list[Path]:
        return []

    @property
    def repo_mounts(self) -> list:
        return []

    @property
    def repo_root(self) -> Path:
        return Path(".")

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self._entities.get(artifact_id)

    def get_connection(self, artifact_id: str):
        return None

    def get_diagram(self, artifact_id: str):
        return None

    def get_document(self, artifact_id: str):
        return None

    def find_file_by_id(self, artifact_id: str) -> Path | None:
        return self._paths.get(artifact_id)

    def find_all_by_stable_id(self, short: str) -> list[Candidate]:
        return list(self._candidates.get(short, []))

    def reconcile_short_id(self, short: str) -> None:
        self._reconcile_called.append(short)

    def scope_for_path(self, path: Path) -> Literal["engagement", "enterprise", "unknown"]:
        return "engagement"

    def scope_of_entity(self, artifact_id: str) -> Literal["engagement", "enterprise", "unknown"]:
        return "engagement"

    def scope_of_connection(self, artifact_id: str) -> Literal["engagement", "enterprise", "unknown"]:
        return "engagement"

    def refresh(self) -> None:
        pass

    def read_model_version(self):
        return SimpleNamespace(generation=0, etag="")

    def entity_ids(self) -> set[str]:
        return set(self._entities)

    def connection_ids(self) -> set[str]:
        return set()

    def enterprise_entity_ids(self) -> set[str]:
        return set()

    def engagement_entity_ids(self) -> set[str]:
        return set(self._entities)

    def enterprise_connection_ids(self) -> set[str]:
        return set()

    def engagement_connection_ids(self) -> set[str]:
        return set()

    def enterprise_document_ids(self) -> set[str]:
        return set()

    def enterprise_diagram_ids(self) -> set[str]:
        return set()

    def entity_status(self, artifact_id: str) -> str | None:
        e = self._entities.get(artifact_id)
        return e.status if e else None

    def entity_statuses(self) -> dict[str, str]:
        return {aid: e.status for aid, e in self._entities.items()}

    def connection_status(self, artifact_id: str) -> str | None:
        return None

    def read_artifact(self, artifact_id, *, mode="summary", section=None):
        return None

    def summarize_artifact(self, artifact_id):
        return None

    def read_entity_context(self, artifact_id):
        return None

    def stats(self) -> dict[str, object]:
        return {}


class TestResolveArtifact:
    def test_exact_match_current_slug(self, tmp_path: Path) -> None:
        path = tmp_path / "REQ@1000.AAA.current-slug.md"
        path.touch()
        store = _FakeStore()
        store._paths["REQ@1000.AAA.current-slug"] = path
        store._entities["REQ@1000.AAA.current-slug"] = _entity_rec(
            "REQ@1000.AAA.current-slug", path
        )
        reg = ArtifactRegistry(store)  # type: ignore[arg-type]
        result = reg.resolve_artifact("REQ@1000.AAA.current-slug")
        assert result is not None
        assert result.canonical_id == "REQ@1000.AAA.current-slug"
        assert result.stale_slug is None
        assert not result.renamed

    def test_exact_match_no_slug_short_form(self, tmp_path: Path) -> None:
        path = tmp_path / "REQ@1000.AAA.slug.md"
        path.touch()
        store = _FakeStore()
        # Exact match by short id (find_file_by_id returns None for short form unless stored)
        # → falls through to reconcile path
        store._candidates["REQ@1000.AAA"] = [
            Candidate(artifact_id="REQ@1000.AAA.slug", path=path, scope="engagement")
        ]
        store._entities["REQ@1000.AAA.slug"] = _entity_rec("REQ@1000.AAA.slug", path)
        reg = ArtifactRegistry(store)  # type: ignore[arg-type]
        result = reg.resolve_artifact("REQ@1000.AAA")
        assert result is not None
        assert result.canonical_id == "REQ@1000.AAA.slug"
        assert result.renamed  # artifact_id differs from requested short form

    def test_drift_resolve_stale_slug(self, tmp_path: Path) -> None:
        """Requesting an old slug should still resolve via reconcile."""
        current_path = tmp_path / "REQ@1000.AAA.new-slug.md"
        current_path.touch()
        store = _FakeStore()
        # Old slug is not in the paths map; reconcile supplies the current candidate
        store._candidates["REQ@1000.AAA"] = [
            Candidate(artifact_id="REQ@1000.AAA.new-slug", path=current_path, scope="engagement")
        ]
        store._entities["REQ@1000.AAA.new-slug"] = _entity_rec("REQ@1000.AAA.new-slug", current_path)
        reg = ArtifactRegistry(store)  # type: ignore[arg-type]
        result = reg.resolve_artifact("REQ@1000.AAA.old-slug")
        assert result is not None
        assert result.canonical_id == "REQ@1000.AAA.new-slug"
        assert result.renamed
        assert result.stale_slug == "old-slug"
        assert "REQ@1000.AAA" in store._reconcile_called

    def test_evict_missing_path_returns_none(self, tmp_path: Path) -> None:
        gone_path = tmp_path / "REQ@1000.AAA.slug.md"
        # Path does not exist on disk
        store = _FakeStore()
        store._candidates["REQ@1000.AAA"] = [
            Candidate(artifact_id="REQ@1000.AAA.slug", path=gone_path, scope="engagement")
        ]
        reg = ArtifactRegistry(store)  # type: ignore[arg-type]
        result = reg.resolve_artifact("REQ@1000.AAA.slug")
        assert result is None

    def test_cross_mount_duplicate_raises_ambiguous(self, tmp_path: Path) -> None:
        path_eng = tmp_path / "eng" / "REQ@1000.AAA.slug.md"
        path_ent = tmp_path / "ent" / "REQ@1000.AAA.slug.md"
        path_eng.parent.mkdir()
        path_ent.parent.mkdir()
        path_eng.touch()
        path_ent.touch()
        store = _FakeStore()
        store._candidates["REQ@1000.AAA"] = [
            Candidate(artifact_id="REQ@1000.AAA.slug", path=path_eng, scope="engagement"),
            Candidate(artifact_id="REQ@1000.AAA.slug", path=path_ent, scope="enterprise"),
        ]
        reg = ArtifactRegistry(store)  # type: ignore[arg-type]
        with pytest.raises(AmbiguousArtifactError):
            reg.resolve_artifact("REQ@1000.AAA")

    def test_scope_selection_disambiguates(self, tmp_path: Path) -> None:
        """Specifying scope=engagement picks the right candidate from a cross-mount pair."""
        path_eng = tmp_path / "eng" / "REQ@1000.AAA.slug.md"
        path_ent = tmp_path / "ent" / "REQ@1000.AAA.slug.md"
        path_eng.parent.mkdir()
        path_ent.parent.mkdir()
        path_eng.touch()
        path_ent.touch()
        store = _FakeStore()
        store._candidates["REQ@1000.AAA"] = [
            Candidate(artifact_id="REQ@1000.AAA.slug", path=path_eng, scope="engagement"),
            Candidate(artifact_id="REQ@1000.AAA.slug", path=path_ent, scope="enterprise"),
        ]
        store._entities["REQ@1000.AAA.slug"] = _entity_rec("REQ@1000.AAA.slug", path_eng)
        reg = ArtifactRegistry(store)  # type: ignore[arg-type]
        result = reg.resolve_artifact("REQ@1000.AAA", scope="engagement")
        assert result is not None
        assert result.path == path_eng

    def test_reconcile_called_on_miss(self, tmp_path: Path) -> None:
        store = _FakeStore()
        reg = ArtifactRegistry(store)  # type: ignore[arg-type]
        result = reg.resolve_artifact("REQ@1000.AAA.missing-slug")
        assert result is None
        assert "REQ@1000.AAA" in store._reconcile_called


def _write_entity_file(tmp_path: Path, artifact_id: str) -> Path:
    path = tmp_path / "model" / "motivation" / "requirement" / f"{artifact_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nartifact-id: {artifact_id}\nartifact-type: requirement\n"
        "name: Current\nversion: 0.1.0\nstatus: draft\n---\n",
        encoding="utf-8",
    )
    return path


class TestReadPathAcceptsShortAndLongIds:
    """read_artifact / get_entity tacitly resolve short, current-slug and stale-slug ids."""

    def test_read_artifact_resolves_all_id_forms(self, tmp_path: Path) -> None:
        _write_entity_file(tmp_path, "REQ@1000.AAA.current")
        index = ArtifactIndex(tmp_path)
        index.refresh()

        assert index.read_artifact("REQ@1000.AAA.current") is not None  # exact long id
        assert index.read_artifact("REQ@1000.AAA") is not None  # short id
        assert index.read_artifact("REQ@1000.AAA.old-slug") is not None  # stale slug
        assert index.read_artifact("REQ@9999.ZZZ") is None  # genuinely absent short id

    def test_get_entity_resolves_short_and_stale_slug(self, tmp_path: Path) -> None:
        _write_entity_file(tmp_path, "REQ@1000.AAA.current")
        index = ArtifactIndex(tmp_path)
        index.refresh()

        assert index.get_entity("REQ@1000.AAA").artifact_id == "REQ@1000.AAA.current"  # type: ignore[union-attr]
        assert index.get_entity("REQ@1000.AAA.old").artifact_id == "REQ@1000.AAA.current"  # type: ignore[union-attr]


class TestEveryReadCanonicalisesTheId:
    """A short id must resolve through every read on the index, not just some of them.

    `read_artifact` and `get_entity` canonicalised; `read_entity_context`, `summarize_artifact`
    and the scoped entity read did not. The short form is what a binding stores, so an assurance
    FMEA row linking to its architecture element loaded the entity header from `/api/entity` and
    then took a 404 from `/api/entity-context` for the very same id — one page, two answers about
    whether the entity exists.
    """

    @staticmethod
    def _index(tmp_path: Path) -> ArtifactIndex:
        path = tmp_path / "model" / "application" / "application-component" / "APP@1000.AAA.backend.md"
        path.parent.mkdir(parents=True)
        path.write_text(
            "---\n"
            "artifact-id: APP@1000.AAA.backend\n"
            "artifact-type: application-component\n"
            "name: Backend\n"
            "version: 0.1.0\n"
            "status: draft\n"
            "---\n\n## Backend\n\nText.\n",
            encoding="utf-8",
        )
        index = ArtifactIndex(tmp_path)
        index.refresh()
        return index

    def test_read_entity_context_resolves_a_short_id(self, tmp_path: Path) -> None:
        index = self._index(tmp_path)

        context = index.read_entity_context("APP@1000.AAA")

        assert context is not None
        assert context["entity"]["artifact_id"] == "APP@1000.AAA.backend"

    def test_summarize_artifact_resolves_a_short_id(self, tmp_path: Path) -> None:
        index = self._index(tmp_path)

        summary = index.summarize_artifact("APP@1000.AAA")

        assert summary is not None
        assert summary.artifact_id == "APP@1000.AAA.backend"

    def test_the_reads_agree_with_each_other_on_the_short_form(self, tmp_path: Path) -> None:
        """The invariant behind the symptom: no read may disagree about existence."""
        index = self._index(tmp_path)
        short = "APP@1000.AAA"

        assert index.get_entity(short) is not None
        assert index.read_artifact(short) is not None
        assert index.read_entity_context(short) is not None
        assert index.summarize_artifact(short) is not None

    def test_an_unknown_short_id_is_still_absent_everywhere(self, tmp_path: Path) -> None:
        index = self._index(tmp_path)

        assert index.get_entity("APP@9999.ZZZ") is None
        assert index.read_entity_context("APP@9999.ZZZ") is None
        assert index.summarize_artifact("APP@9999.ZZZ") is None
