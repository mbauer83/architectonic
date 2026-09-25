"""A diagram holds ad-hoc icons of its own, stored normalised in its file and dropped once unused (D11)."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.rendering.generate_static_includes import generate_static_includes
from tests.support.icon_files import png_of

RABBIT_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><script>x</script>'
    b'<rect width="8" height="8" fill="#ff6600"/></svg>'
)


def _upload(content: bytes = RABBIT_SVG, source_format: str = "svg", **extra: object) -> dict:
    encoded = base64.b64encode(content).decode()
    return {"name": "RabbitMQ", "content_base64": encoded, "source_format": source_format, **extra}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    for directory in ("model", "docs", "diagram-catalog/diagrams"):
        (root / directory).mkdir(parents=True)
    generate_static_includes(root)
    return root


def _node(repo: Path) -> str:
    return str(mcp.artifact_create_entity(
        artifact_type="technology-node", name="Broker", dry_run=False, repo_root=str(repo)
    )["artifact_id"])


def _create(repo: Path, node: str, statements: dict) -> dict:
    return mcp.artifact_create_diagram(
        diagram_type="archimate-technology", name="Messaging", entity_ids=[node],
        diagram_entities=statements, dry_run=False, repo_root=str(repo),
    )


def _stored(result: dict) -> dict:
    return parse_frontmatter(Path(str(result["path"])).read_text(encoding="utf-8"))["diagram-entities"]


def test_an_upload_is_stored_normalised_in_the_diagram_and_drawn(repo: Path) -> None:
    node = _node(repo)

    result = _create(repo, node, {"icons": {"rabbit": _upload()}, "display_icons": {node: "local:rabbit"}})

    assert result["verification"]["valid"] is True, result["verification"]
    entry = _stored(result)["icons"]["rabbit"]
    assert set(entry) == {"name", "render-digest", "width", "height", "applies-to", "default-style", "png-base64"}
    assert "<img:$ARCH_ICON_" in Path(str(result["path"])).read_text(encoding="utf-8")


def test_an_icon_nothing_uses_is_dropped(repo: Path) -> None:
    node = _node(repo)

    result = _create(repo, node, {"icons": {"rabbit": _upload(), "spare": _upload(png_of(), "png")},
                                  "display_icons": {node: "local:rabbit"}})

    assert list(_stored(result)["icons"]) == ["rabbit"]


def test_a_later_edit_keeps_the_stored_icon_as_it_is(repo: Path) -> None:
    node = _node(repo)
    created = _create(repo, node, {"icons": {"rabbit": _upload()}, "display_icons": {node: "local:rabbit"}})
    stored = _stored(created)

    edited = mcp.artifact_edit_diagram(
        artifact_id=str(created["artifact_id"]), diagram_entities=stored, dry_run=False, repo_root=str(repo)
    )

    assert _stored(edited)["icons"] == stored["icons"]


@pytest.mark.parametrize(
    ("icons", "reason"),
    [
        ({"rabbit": _upload(b"GIF89a", "png")}, "not a PNG, JPEG or WebP"),
        ({"rabbit": _upload(source_format="bmp")}, "source_format"),
        ({f"k{i}": _upload(png_of((i, i, i, 255)), "png") for i in range(9)}, "at most 8"),
    ],
    ids=["undecodable", "unknown-format", "too-many"],
)
def test_an_icon_that_cannot_be_stored_refuses_the_write(repo: Path, icons: dict, reason: str) -> None:
    node = _node(repo)
    uses = {f"INSTANCE-{key}": f"local:{key}" for key in icons}

    with pytest.raises(ValueError, match=reason):
        _create(repo, node, {"icons": icons, "display_icons": uses})


def test_a_reference_to_a_key_that_is_not_a_slug_is_named_by_the_verifier(repo: Path) -> None:
    node = _node(repo)

    result = _create(repo, node, {"icons": {"Rabbit": _upload()}, "display_icons": {node: "local:Rabbit"}})

    assert result["wrote"] is False and "E364" in [i["code"] for i in result["verification"]["issues"]]
