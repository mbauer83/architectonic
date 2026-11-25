"""No location a client names is read, evaluated or written outside the configured repositories.

Regressions, each reproduced against the code before the fix:

* `repo_root: "/"` (or any directory) on an MCP read tool was indexed and served;
* `artifact_verify` read and reported on any file its `path` named;
* an entity created with `group: "../../../elsewhere"` was written outside the repository;
* `GET /api/diagram-images/*` served whatever file the glob matched first.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from mcp.server.context import ServerRequestContext
from mcp.types import CallToolRequestParams, TextContent

from src.application.repository_confinement import (
    LocationRefused,
    confine_root,
    confine_within,
    path_inside,
    require_segment,
)
from src.infrastructure.mcp.location_parameters import confined_arguments


@pytest.fixture
def repositories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    engagement = tmp_path / "engagement"
    enterprise = tmp_path / "enterprise"
    for root in (engagement, enterprise):
        (root / "model").mkdir(parents=True)
    monkeypatch.setenv("ARCH_REPO_ROOT", str(engagement))
    monkeypatch.delenv("ARCH_MCP_MODEL_REPO_ROOT", raising=False)
    monkeypatch.setenv("ARCH_ENTERPRISE_ROOT", str(enterprise))
    return engagement, enterprise


class TestTheOwner:
    def test_a_root_must_be_a_configured_one(self, tmp_path: Path) -> None:
        configured = tmp_path / "repo"
        configured.mkdir()

        assert confine_root(tmp_path / "repo" / ".." / "repo", [configured]) == configured
        with pytest.raises(LocationRefused, match=str(configured)):
            confine_root(Path("/"), [configured])
        with pytest.raises(LocationRefused):
            confine_root(configured / "model", [configured])

    def test_a_link_inside_a_repository_pointing_out_of_it_is_refused(self, tmp_path: Path) -> None:
        configured = tmp_path / "repo"
        configured.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.md").write_text("x", encoding="utf-8")
        (configured / "link").symlink_to(outside)

        with pytest.raises(LocationRefused):
            confine_within(configured / "link" / "secret.md", [configured])
        with pytest.raises(LocationRefused):
            confine_root(configured / "link", [outside.parent / "nothing"])

    def test_a_refusal_names_the_repositories_and_not_what_was_asked_for(self, tmp_path: Path) -> None:
        with pytest.raises(LocationRefused) as refused:
            confine_within(Path("/etc/passwd"), [tmp_path])

        assert str(tmp_path) in str(refused.value)
        assert "passwd" not in str(refused.value)

    @pytest.mark.parametrize("name", ["..", ".", "", "a/b", "../x", "/abs", "a\\b", "C:x", "x\x00"])
    def test_a_name_that_could_leave_its_directory_is_refused(self, name: str) -> None:
        with pytest.raises(LocationRefused):
            require_segment(name, what="group")

    def test_a_composed_path_must_stay_inside(self, tmp_path: Path) -> None:
        assert path_inside(tmp_path, "projects", "core", "x.md") == tmp_path / "projects" / "core" / "x.md"
        with pytest.raises(LocationRefused):
            path_inside(tmp_path, "projects", "../../..", "x.md")


class TestTheMcpBoundary:
    def test_any_directory_as_a_repository_is_refused(self, repositories: tuple[Path, Path]) -> None:
        with pytest.raises(LocationRefused):
            confined_arguments("artifact_query_stats", {"repo_root": "/"})

    def test_a_configured_repository_is_passed_as_configured(self, repositories: tuple[Path, Path]) -> None:
        engagement, enterprise = repositories

        spelled = str(engagement / "model" / "..")
        assert confined_arguments("artifact_query_stats", {"repo_root": spelled}) == {"repo_root": str(engagement)}
        assert confined_arguments("artifact_query_stats", {"repo_root": str(enterprise)}) == {
            "repo_root": str(enterprise),
        }

    def test_the_enterprise_root_must_be_the_enterprise_repository(self, repositories: tuple[Path, Path]) -> None:
        engagement, _enterprise = repositories
        with pytest.raises(LocationRefused):
            confined_arguments("artifact_submit_changes", {"enterprise_root": str(engagement)})

    def test_a_file_to_verify_must_lie_inside_a_repository(self, repositories: tuple[Path, Path]) -> None:
        engagement, _enterprise = repositories
        inside = engagement / "model" / "x.md"

        assert confined_arguments("artifact_verify", {"path": "model/x.md"}) == {"path": str(inside.resolve())}
        with pytest.raises(LocationRefused):
            confined_arguments("artifact_verify", {"path": "/etc/passwd"})
        with pytest.raises(LocationRefused):
            confined_arguments("artifact_verify", {"path": "../../etc/passwd"})

    def test_a_collection_must_be_one_name(self, repositories: tuple[Path, Path]) -> None:
        assert confined_arguments("artifact_create_entity", {"group": "core"}) == {"group": "core"}
        with pytest.raises(LocationRefused):
            confined_arguments("artifact_create_entity", {"group": "../../../elsewhere"})

    def test_a_refused_location_reaches_the_caller_through_the_dispatch(
        self, repositories: tuple[Path, Path],
    ) -> None:
        from src.infrastructure.mcp import mcp_artifact_server as servers

        entry = servers.mcp_read._lowlevel_server.get_request_handler("tools/call")
        params = CallToolRequestParams(name="artifact_query_stats", arguments={"repo_root": "/"})
        context: ServerRequestContext[Any] = ServerRequestContext(
            session=None, lifespan_context=None, protocol_version=None,
            method="tools/call", params=params, request_id=1,
        )

        result = asyncio.run(entry.handler(context, params))

        assert result.is_error
        text = next(c.text for c in result.content if isinstance(c, TextContent))
        assert "configured repositories" in text


class TestTheWritePath:
    def test_an_entity_is_not_filed_outside_the_repository(self, tmp_path: Path) -> None:
        from src.infrastructure.write.artifact_write.entity import entity_path

        info = type("Info", (), {"hierarchy": ("motivation", "requirement")})()
        with pytest.raises(LocationRefused):
            entity_path(tmp_path, info, "REQ@1.a.b", "../../../elsewhere")  # type: ignore[arg-type]
        with pytest.raises(LocationRefused):
            entity_path(tmp_path, info, "../../../../elsewhere")  # type: ignore[arg-type]

    def test_a_group_is_not_created_under_a_name_that_leaves_its_directory(self, tmp_path: Path) -> None:
        from src.infrastructure.write.artifact_write.group_ops import group_create

        with pytest.raises(LocationRefused):
            group_create(tmp_path, axis="model-project", slug="../../elsewhere", name="Elsewhere")


class TestRest:
    @pytest.fixture
    def client(self) -> Any:
        from fastapi.testclient import TestClient

        from src.infrastructure.backend.arch_backend_app import _build_app

        return TestClient(_build_app(), base_url="http://localhost")

    def test_a_collection_slug_that_leaves_its_directory_is_refused(self, client: Any) -> None:
        response = client.post("/api/groups", json={
            "kind": "model-project", "slug": "../../elsewhere", "name": "Elsewhere",
        })

        assert response.status_code == 422

    def test_an_entity_filed_outside_is_refused(self, client: Any) -> None:
        response = client.post("/api/entities", json={
            "artifact_type": "requirement", "name": "Probe", "group": "../../../elsewhere",
        })

        assert response.status_code == 422

    def test_an_image_name_is_a_name_and_not_a_pattern(
        self, client: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from src.infrastructure.rest.routers import state

        rendered = tmp_path / "diagram-catalog" / "rendered"
        rendered.mkdir(parents=True)
        (rendered / "only.png").write_bytes(b"png")
        monkeypatch.setattr(state, "maybe_engagement_root", lambda: tmp_path)

        assert client.get("/api/diagram-images/*").status_code == 404
        assert client.get("/api/diagram-images/only.png").status_code == 200

    @pytest.mark.parametrize("path", ["/..%2f..%2f..%2fpyproject.toml", "/assets/..%2f..%2f..%2f..%2fpyproject.toml"])
    def test_the_gui_files_are_served_from_the_build_only(self, client: Any, path: str) -> None:
        """Confirms the static mount's own containment: an escaped `..` reaches no file beside the build."""
        response = client.get(path)

        assert "[project]" not in response.text
