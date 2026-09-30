"""`artifact_create_icon` stores one normalised icon in the library, or says why it will not."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from src.domain.icons.icon_file import IconFile, read_icon_file
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp import context as ctx
from src.infrastructure.rendering.generate_static_includes import generate_static_includes
from tests.support.icon_files import png_of

LOGO = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><script>alert(1)</script>'
    b'<rect width="10" height="10" fill="#0078d4"/></svg>'
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    for directory in ("model", "docs", "diagram-catalog/diagrams"):
        (root / directory).mkdir(parents=True)
    generate_static_includes(root)
    return root


def _create(repo: Path, content: bytes = LOGO, **overrides: object) -> dict:
    arguments: dict[str, object] = {
        "name": "Azure Kubernetes Service", "attribution": "Microsoft Azure architecture icons",
        "content_base64": base64.b64encode(content).decode(), "source_format": "svg",
        "applies_to": ["technology-node"], "dry_run": False, "repo_root": str(repo),
    }
    return mcp.artifact_create_icon(**{**arguments, **overrides})


def _refusal(result: dict) -> str:
    assert result.get("wrote") is not True, result
    issues = (result.get("verification") or {}).get("issues") or []
    return result.get("error") or " ".join(str(i["message"]) for i in issues)


def test_an_icon_is_stored_normalised_indexed_and_says_what_it_removed(repo: Path) -> None:
    result = _create(repo)

    assert result["wrote"] is True, result
    stored = read_icon_file(Path(str(result["path"])).read_text(encoding="utf-8"))
    assert isinstance(stored, IconFile) and stored.metadata.name == "Azure Kubernetes Service"
    assert stored.svg_source is not None and "script" not in stored.svg_source
    assert any("<script> removed" in w for w in result["warnings"])
    roots = ctx.resolve_repo_roots(repo_scope="engagement", repo_root=str(repo), repo_preset=None, enterprise_root=None)
    assert ctx.repo_cached(ctx.roots_key(roots)).get_icon(str(result["artifact_id"])) is not None


def test_a_new_icon_can_be_drawn_at_once(repo: Path) -> None:
    icon_id = str(_create(repo)["artifact_id"])
    node = mcp.artifact_create_entity(
        artifact_type="technology-node", name="Cluster", dry_run=False, repo_root=str(repo)
    )

    diagram = mcp.artifact_create_diagram(
        diagram_type="archimate-technology", name="View", entity_ids=[str(node["artifact_id"])],
        diagram_entities={"type_icons": {"technology-node": icon_id}}, dry_run=False, repo_root=str(repo),
    )

    assert "<img:$ARCH_ICON_" in Path(str(diagram["path"])).read_text(encoding="utf-8")


def test_a_dry_run_writes_nothing(repo: Path) -> None:
    result = _create(repo, dry_run=True)

    assert result["wrote"] is False and not Path(str(result["path"])).exists()


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"applies_to": ["technology-nod"]}, "no known type or specialization: technology-nod"),
        ({"attribution": "  "}, "attribution"),
        ({"name": ""}, "needs a name"),
        ({"content_base64": "!!not base64!!"}, "not base64"),
        ({"source_format": "png"}, "not a PNG, JPEG or WebP"),
    ],
    ids=["unknown-type", "no-attribution", "no-name", "bad-base64", "svg-declared-as-png"],
)
def test_an_upload_that_cannot_be_stored_is_refused_with_its_reason(repo: Path, overrides: dict, reason: str) -> None:
    assert reason in _refusal(_create(repo, **overrides))


def test_a_picture_the_library_holds_is_not_stored_twice(repo: Path) -> None:
    first = _create(repo, png_of(), source_format="png")

    again = _create(repo, png_of(), source_format="png", name="Same picture")

    assert first["wrote"] is True and str(first["artifact_id"]).split(".")[0] in _refusal(again)


def test_the_library_is_listed_for_what_an_agent_is_choosing(repo: Path) -> None:
    from src.infrastructure.mcp.artifact_mcp.query_icon_tools import artifact_query_icons

    def offered_for(target: str) -> list[str]:
        return sorted(row["artifact_id"] for row in artifact_query_icons(applicable_to=target, repo_root=str(repo)))

    node_icon = str(_create(repo)["artifact_id"])
    unrestricted = _create(repo, png_of((9, 9, 9, 255)), source_format="png", name="Anywhere", applies_to=[])
    anywhere = str(unrestricted["artifact_id"])

    for_nodes, for_services = offered_for("technology-node"), offered_for("application-service")

    assert sorted(for_nodes) == sorted([node_icon, anywhere]) and for_services == [anywhere]
    row = artifact_query_icons(q="kubernetes", repo_root=str(repo))[0]
    assert row["scope"] == "engagement" and row["baseline_standing"]["kind"] == "enterprise-baseline"
    assert "png" not in row and "content" not in row
    assert row["used_on"] == [] and row["default_for"] == [] and row["shown_for_element"] is False
