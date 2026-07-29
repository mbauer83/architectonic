"""Every cacheable path must actually notice every kind of change.

A wrong 304 is the worst failure this mechanism can produce: the client renders what it
already holds and never learns the server moved on, so there is no error, no log line and no
symptom other than data that is quietly out of date. Correctness therefore cannot rest on
the allowlist looking reasonable — each entry has to be demonstrated.

The safety argument has two parts, and this module tests both.

1. **Caching cannot make a response staler than the source it is derived from.** Every
   allowlisted body is built from the artifact index, and the validator is the index's own
   generation tag. If the index were stale the uncached response would be equally stale, so
   caching adds no new failure mode there — it inherits the index's freshness exactly.

2. **The risk unique to caching is a body that reads something the index does not track.**
   That is a real hazard — viewpoint definitions, repo schemata, git state and the assurance
   store all move without the model generation moving — so it is contained by keeping the
   allowlist to exact paths and proving each one responds to a write of its own kind.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.backend.read_model_caching import _MODEL_DERIVED_PATHS, _entity_tag
from src.infrastructure.gui.routers import state as gui_state
from src.infrastructure.mcp import mcp_artifact_server as mcp

httpx = pytest.importorskip("httpx")


class _Url:
    def __init__(self, path: str, query: str = "") -> None:
        self.path, self.query = path, query


class _Request:
    def __init__(self, path: str, query: str = "") -> None:
        self.url = _Url(path, query)


@pytest.fixture()
def repo(tmp_path: Path):  # type: ignore[no-untyped-def]
    root = tmp_path / "engagements" / "ENG-CACHE" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    index = shared_artifact_index([root])
    index.refresh()
    gui_state.init_state(ArtifactRepository(index), root, None)
    app = FastAPI()
    yield root, index, app


def _tag(index) -> str:  # type: ignore[no-untyped-def]
    """The validator as the middleware would compute it, for a fixed URL."""
    return _entity_tag(str(index.read_model_version().etag), _Request("/api/entities"))


class TestTheGenerationNoticesEveryArtifactKind:
    """One case per artifact kind an allowlisted body can contain."""

    def test_creating_an_entity_changes_the_validator(self, repo) -> None:  # type: ignore[no-untyped-def]
        root, index, _ = repo
        before = _tag(index)

        mcp.artifact_create_entity(
            artifact_type="requirement", name="Cache Probe", summary="S.",
            dry_run=False, repo_root=str(root),
        )
        index.refresh()

        assert _tag(index) != before

    def test_editing_an_entity_changes_the_validator(self, repo) -> None:  # type: ignore[no-untyped-def]
        root, index, _ = repo
        created = mcp.artifact_create_entity(
            artifact_type="requirement", name="Cache Edit", summary="S.",
            dry_run=False, repo_root=str(root),
        )
        index.refresh()
        before = _tag(index)

        mcp.artifact_edit_entity(
            artifact_id=str(created["artifact_id"]), summary="Changed.",
            dry_run=False, repo_root=str(root),
        )
        index.refresh()

        assert _tag(index) != before

    def test_adding_a_connection_changes_the_validator(self, repo) -> None:  # type: ignore[no-untyped-def]
        root, index, _ = repo
        source = mcp.artifact_create_entity(
            artifact_type="requirement", name="Cache Source", summary="S.",
            dry_run=False, repo_root=str(root))["artifact_id"]
        target = mcp.artifact_create_entity(
            artifact_type="outcome", name="Cache Target", summary="S.",
            dry_run=False, repo_root=str(root))["artifact_id"]
        index.refresh()
        before = _tag(index)

        mcp.artifact_add_connection(
            source_entity=str(source), target_entity=str(target),
            connection_type="archimate-realization", description="Realizes.",
            dry_run=False, repo_root=str(root),
        )
        index.refresh()

        assert _tag(index) != before

    def test_deleting_an_entity_changes_the_validator(self, repo) -> None:  # type: ignore[no-untyped-def]
        root, index, _ = repo
        created = mcp.artifact_create_entity(
            artifact_type="requirement", name="Cache Delete", summary="S.",
            dry_run=False, repo_root=str(root),
        )
        index.refresh()
        before = _tag(index)

        mcp.artifact_delete_entity(
            artifact_id=str(created["artifact_id"]), dry_run=False, repo_root=str(root),
        )
        index.refresh()

        assert _tag(index) != before


class TestTheAllowlistStaysHonest:
    def test_every_entry_is_an_exact_path(self) -> None:
        """Prefixes would adopt future sub-routes without anyone deciding they qualify."""
        assert all(not path.endswith("/") for path in _MODEL_DERIVED_PATHS)

    @pytest.mark.parametrize("path", [
        "/api/viewpoints", "/api/entity-schemata", "/api/entity-taxonomy",
        "/api/sync/status", "/api/assurance/stats",
    ])
    def test_sources_outside_the_index_are_not_cached(self, path: str) -> None:
        """Each of these moves without the model generation moving."""
        assert path not in _MODEL_DERIVED_PATHS

    def test_the_allowlist_has_not_silently_grown(self) -> None:
        """A change here must come with a demonstration above, so pin the set."""
        assert _MODEL_DERIVED_PATHS == frozenset({
            "/api/entities", "/api/entity", "/api/entity-context", "/api/connections",
            "/api/diagrams", "/api/diagram-entities", "/api/documents", "/api/stats",
        })


class TestEndToEndThroughHttp:
    """The chain that actually matters: middleware + write path + index invalidation.

    The tests above prove the index notices a write. This proves the served validator does —
    including the middleware, the route, and whatever the write path does to the index. A
    green result here is the statement "a client holding the previous answer is told to fetch
    again", which is the only property the cache has to guarantee.
    """

    def _client(self, root: Path):  # type: ignore[no-untyped-def]
        from starlette.testclient import TestClient

        from src.infrastructure.backend.read_model_caching import conditional_read_middleware
        from src.infrastructure.gui.routers.entities import router

        app = FastAPI()
        app.middleware("http")(conditional_read_middleware)
        app.include_router(router)
        return TestClient(app)

    def test_a_write_makes_the_previous_validator_stale(self, repo) -> None:  # type: ignore[no-untyped-def]
        root, index, _ = repo
        client = self._client(root)

        first = client.get("/api/entities")
        assert first.status_code == 200
        tag = first.headers["ETag"]
        # Unchanged model: the client is told it already has the answer.
        assert client.get("/api/entities", headers={"If-None-Match": tag}).status_code == 304

        client.post("/api/entity", json={
            "artifact_type": "requirement", "name": "Http Cache Probe",
            "summary": "S.", "dry_run": False,
        })

        after = client.get("/api/entities", headers={"If-None-Match": tag})
        assert after.status_code == 200, "a client holding the pre-write answer was told it was current"
        assert after.headers["ETag"] != tag
        assert "Http Cache Probe" in after.text

    def test_a_different_query_never_reuses_another_answer(self, repo) -> None:  # type: ignore[no-untyped-def]
        root, index, _ = repo
        client = self._client(root)

        tag = client.get("/api/entities?domain=application").headers["ETag"]

        other = client.get("/api/entities?domain=motivation", headers={"If-None-Match": tag})

        assert other.status_code == 200

class TestTheIncrementalDoorNoticesEveryKind:
    """`apply_file_changes` is the path a live write and the watcher both take.

    The tests above call `refresh()`, which rebuilds everything and therefore bumps the
    generation whatever happened — they prove the validator is derived from the index, not
    that the index notices. Incremental application is where a kind can be missed: it
    classifies each path and applies a per-kind updater, so a kind nobody classified is the
    realistic way stale content gets served. Two guarantees are pinned here — every kind that
    *is* classified bumps the generation, and anything that is *not* classified falls back to
    a full refresh rather than being ignored.
    """

    def _entity(self, root: Path, artifact_id: str, name: str) -> Path:
        path = root / "model" / "motivation" / "requirement" / f"{artifact_id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"---\nartifact-id: {artifact_id}\nartifact-type: requirement\nname: \"{name}\"\n"
            f"version: 0.1.0\nstatus: active\nlast-updated: '2026-04-21'\n---\n\n"
            f"<!-- §content -->\n\n## {name}\n\nContent.\n\n"
            "<!-- §display -->\n\n### archimate\n\n"
            f"```yaml\ndomain: Motivation\nelement-type: Requirement\nlabel: \"{name}\"\n```\n",
            encoding="utf-8",
        )
        return path

    def test_an_entity_file_bumps_the_generation(self, repo) -> None:  # type: ignore[no-untyped-def]
        root, index, _ = repo
        before = index.read_model_version().generation

        path = self._entity(root, "REQ@1000000000.CovAA.probe", "Incremental Probe")

        assert index.apply_file_changes([path]).generation > before

    def test_an_outgoing_file_bumps_the_generation(self, repo) -> None:  # type: ignore[no-untyped-def]
        root, index, _ = repo
        source = "REQ@1000000000.CovBB.src"
        target = "REQ@1000000001.CovCC.tgt"
        index.apply_file_changes([
            self._entity(root, source, "Src"), self._entity(root, target, "Tgt"),
        ])
        before = index.read_model_version().generation

        path = root / "model" / "motivation" / "requirement" / f"{source}.outgoing.md"
        path.write_text(
            f"---\nsource: {source}\n---\n\n"
            f"| Target | Type | Description |\n|---|---|---|\n"
            f"| {target} | archimate-realization | Realizes. |\n",
            encoding="utf-8",
        )

        assert index.apply_file_changes([path]).generation > before

    def test_a_diagram_bumps_the_generation(self, repo) -> None:  # type: ignore[no-untyped-def]
        root, index, _ = repo
        before = index.read_model_version().generation

        path = root / "diagram-catalog" / "diagrams" / "MAT@1000000003.CovEE.probe-matrix.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\nartifact-id: MAT@1000000003.CovEE.probe-matrix\nartifact-type: diagram\n"
            "diagram-type: matrix\nname: \"Probe Matrix\"\nversion: 0.1.0\nstatus: active\n"
            "last-updated: '2026-04-21'\n---\n\n| A | B |\n|---|---|\n| 1 | 2 |\n",
            encoding="utf-8",
        )

        assert index.apply_file_changes([path]).generation > before

    def test_a_document_bumps_the_generation(self, repo) -> None:  # type: ignore[no-untyped-def]
        root, index, _ = repo
        before = index.read_model_version().generation

        path = root / "docs" / "adr" / "0001-a-decision.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# A Decision\n\nBody.\n", encoding="utf-8")

        assert index.apply_file_changes([path]).generation > before

    def test_an_unclassifiable_path_falls_back_to_a_full_refresh(self, repo) -> None:  # type: ignore[no-untyped-def]
        """The defence that makes the list of kinds above non-exhaustive by design."""
        root, index, _ = repo
        before = index.read_model_version().generation

        path = root / "some-future-artifact-kind" / "thing.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("kind: unknown\n", encoding="utf-8")

        assert index.apply_file_changes([path]).generation > before

    def test_a_directory_falls_back_to_a_full_refresh(self, repo) -> None:  # type: ignore[no-untyped-def]
        root, index, _ = repo
        before = index.read_model_version().generation

        assert index.apply_file_changes([root / "model"]).generation > before

    def test_a_deletion_bumps_the_generation(self, repo) -> None:  # type: ignore[no-untyped-def]
        """Removal is the case where "nothing new to parse" could be mistaken for "nothing changed"."""
        root, index, _ = repo
        path = self._entity(root, "REQ@1000000002.CovDD.gone", "Doomed")
        index.apply_file_changes([path])
        before = index.read_model_version().generation

        path.unlink()

        assert index.apply_file_changes([path]).generation > before
