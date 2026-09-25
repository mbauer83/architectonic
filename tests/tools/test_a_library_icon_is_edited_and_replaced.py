"""A library icon's metadata is editable and its picture is not; a replacement moves every user at once."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from src.application.icons.effective_icons import with_icon_repointed
from src.application.puml_icon_header import icon_key
from src.domain.artifact_id import stable_id
from src.domain.icons.icon_file import IconFile, read_icon_file
from src.domain.icons.icon_ref import LocalIcon, SharedIcon
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.write.icon import artifact_edit_icon, artifact_replace_icon
from src.infrastructure.rendering.generate_static_includes import generate_static_includes
from tests.support.icon_files import png_of

_OLD = "ICO@1790000001.old001"
_NEW = "ICO@1790000002.new001"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    for directory in ("model", "docs", "diagram-catalog/diagrams"):
        (root / directory).mkdir(parents=True)
    generate_static_includes(root)
    return root


def _icon(repo: Path, name: str, colour: tuple[int, int, int, int]) -> str:
    return str(mcp.artifact_create_icon(
        name=name, attribution="Drawn here", content_base64=base64.b64encode(png_of(colour)).decode(),
        source_format="png", dry_run=False, repo_root=str(repo),
    )["artifact_id"])


def _icon_file(repo: Path, icon_id: str) -> IconFile:
    icon = read_icon_file((repo / "diagram-catalog" / "icons" / f"{icon_id}.md").read_text(encoding="utf-8"))
    assert isinstance(icon, IconFile)
    return icon


def _diagram_showing(repo: Path, icon: str) -> tuple[str, Path]:
    node = mcp.artifact_create_entity(artifact_type="technology-node", name="N", dry_run=False, repo_root=str(repo))
    node_id = str(node["artifact_id"])
    diagram = mcp.artifact_create_diagram(
        diagram_type="archimate-technology", name="View", entity_ids=[node_id],
        diagram_entities={"display_icons": {node_id: {"icon": icon, "style": "badge"}}},
        dry_run=False, repo_root=str(repo),
    )
    return node_id, Path(str(diagram["path"]))


# ── edit ────────────────────────────────────────────────────────────────────────────────────────


def test_an_edit_changes_what_the_icon_says_and_never_its_picture(repo: Path) -> None:
    icon = _icon(repo, "Mark", (0, 120, 212, 255))
    before = _icon_file(repo, icon)

    edited = artifact_edit_icon(
        artifact_id=icon, name="Renamed Mark", tags=["vendor"], status="retired", dry_run=False, repo_root=str(repo)
    )

    after = _icon_file(repo, icon)
    assert edited["wrote"] is True
    assert (after.metadata.name, after.metadata.tags, after.metadata.status) == ("Renamed Mark", ("vendor",), "retired")
    assert (after.png, after.metadata.render_digest) == (before.png, before.metadata.render_digest)
    assert after.metadata.attribution == before.metadata.attribution


def test_an_edit_naming_an_unknown_type_is_refused(repo: Path) -> None:
    icon = _icon(repo, "Mark", (0, 120, 212, 255))

    refused = artifact_edit_icon(artifact_id=icon, applies_to=["no-such-type"], dry_run=False, repo_root=str(repo))

    assert refused["wrote"] is False and _icon_file(repo, icon).metadata.applies_to.as_list() == []


def test_an_edit_that_clears_the_attribution_is_refused(repo: Path) -> None:
    icon = _icon(repo, "Mark", (0, 120, 212, 255))

    assert artifact_edit_icon(artifact_id=icon, attribution="  ", dry_run=False, repo_root=str(repo))["wrote"] is False


def test_editing_an_icon_not_in_the_library_says_so(repo: Path) -> None:
    assert artifact_edit_icon(artifact_id="ICO@1790000009.gone01", name="X", repo_root=str(repo))["ok"] is False


# ── replace ─────────────────────────────────────────────────────────────────────────────────────


def test_a_replacement_re_points_the_diagram_and_deletes_the_old_icon(repo: Path) -> None:
    old = _icon(repo, "Old Mark", (0, 120, 212, 255))
    new = _icon(repo, "New Mark", (200, 40, 40, 255))
    node_id, diagram_path = _diagram_showing(repo, old)
    old_key, new_key = (icon_key(_icon_file(repo, i).metadata.render_digest) for i in (old, new))
    assert old_key in diagram_path.read_text(encoding="utf-8")

    replaced = artifact_replace_icon(artifact_id=old, replacement_id=new, dry_run=False, repo_root=str(repo))

    text = diagram_path.read_text(encoding="utf-8")
    display = parse_frontmatter(text)["diagram-entities"]["display_icons"]  # type: ignore[index]
    assert replaced["wrote"] is True
    assert display == {node_id: {"icon": stable_id(new), "style": "badge"}}
    assert new_key in text and old_key not in text
    assert not (repo / "diagram-catalog" / "icons" / f"{old}.md").exists()


def test_a_dry_run_replacement_names_the_diagrams_and_changes_nothing(repo: Path) -> None:
    old = _icon(repo, "Old Mark", (0, 120, 212, 255))
    new = _icon(repo, "New Mark", (200, 40, 40, 255))
    _node, diagram_path = _diagram_showing(repo, old)
    before = diagram_path.read_text(encoding="utf-8")

    planned = artifact_replace_icon(artifact_id=old, replacement_id=new, dry_run=True, repo_root=str(repo))

    assert planned["wrote"] is False
    assert any(new in str(warning) for warning in planned.get("warnings", []))
    assert diagram_path.read_text(encoding="utf-8") == before
    assert (repo / "diagram-catalog" / "icons" / f"{old}.md").exists()


def test_an_icon_cannot_replace_itself(repo: Path) -> None:
    icon = _icon(repo, "Mark", (0, 120, 212, 255))

    refused = artifact_replace_icon(artifact_id=icon, replacement_id=icon, dry_run=False, repo_root=str(repo))

    assert refused["ok"] is False


def test_a_replacement_the_library_does_not_hold_is_refused(repo: Path) -> None:
    icon = _icon(repo, "Mark", (0, 120, 212, 255))

    refused = artifact_replace_icon(
        artifact_id=icon, replacement_id="ICO@1790000009.gone01", dry_run=False, repo_root=str(repo)
    )

    assert refused["ok"] is False and (repo / "diagram-catalog" / "icons" / f"{icon}.md").exists()


# ── the re-pointing itself ──────────────────────────────────────────────────────────────────────


def test_re_pointing_keeps_each_style_and_leaves_every_other_entry_as_written() -> None:
    entities = {
        "display_icons": {"a": {"icon": _OLD, "style": "figure"}, "b": "local:logo", "c": 7},
        "type_icons": {"technology-node": _OLD, "node": _NEW},
        "technology-node": [{"id": "x"}],
    }

    repointed = with_icon_repointed(entities, SharedIcon(_OLD), SharedIcon(_NEW))

    assert repointed == {
        "display_icons": {"a": {"icon": _NEW, "style": "figure"}, "b": "local:logo", "c": 7},
        "type_icons": {"technology-node": _NEW, "node": _NEW},
        "technology-node": [{"id": "x"}],
    }


def test_re_pointing_moves_a_local_icon_to_a_library_one() -> None:
    repointed = with_icon_repointed({"type_icons": {"node": "local:logo"}}, LocalIcon("logo"), SharedIcon(_NEW))

    assert repointed == {"type_icons": {"node": _NEW}}
