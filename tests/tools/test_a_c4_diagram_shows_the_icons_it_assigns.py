"""A C4 diagram draws an assigned icon through the macro's own `$sprite`, and a group boundary's in its title."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.puml_directive_policy import find_unsafe_puml_directives
from src.application.puml_icon_header import BLOCK_BEGIN, icon_key
from src.domain.icons.render_form import render_digest
from src.infrastructure.mcp import mcp_artifact_server as mcp
from tests.support.icon_files import icon_file, png_of, write_icon

POSTGRES = "ICO@1790000002.pgs001.postgres"
PICTURE = png_of((51, 103, 145, 255), size=(64, 64))
KEY = icon_key(render_digest(PICTURE))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    for directory in ("model", "docs", "diagram-catalog/diagrams"):
        (root / directory).mkdir(parents=True)
    write_icon(root, icon_file(POSTGRES, png=PICTURE, applies_to=("container",)))
    return root


def _create(repo: Path, extra: dict) -> dict:
    return mcp.artifact_create_diagram(
        diagram_type="c4-container", name="Orders", dry_run=False, repo_root=str(repo),
        diagram_entities={
            "software-system": [{"id": "sys", "label": "Orders"}],
            "container": [
                {"id": "api", "label": "Orders API", "technology": "Python"},
                {"id": "db", "label": "Orders DB", "technology": "PostgreSQL"},
            ],
            **extra,
        },
    )


def _body(result: dict) -> str:
    return Path(str(result["path"])).read_text(encoding="utf-8")


def test_an_instance_icon_is_the_macro_s_sprite(repo: Path) -> None:
    result = _create(repo, {"display_icons": {"db": POSTGRES}})

    body = _body(result)
    db_line = next(line for line in body.splitlines() if '"Orders DB"' in line)
    api_line = next(line for line in body.splitlines() if '"Orders API"' in line)
    assert f'$sprite="img:${KEY}{{scale=' in db_line and "$sprite" not in api_line
    assert BLOCK_BEGIN in body and find_unsafe_puml_directives(body) == []
    assert result["verification"]["valid"] is True, result["verification"]


def test_a_type_icon_reaches_every_container_and_not_the_system(repo: Path) -> None:
    body = _body(_create(repo, {"type_icons": {"container": POSTGRES}}))

    assert body.count(f"img:${KEY}") == 2


def test_an_icon_restricted_to_another_type_is_not_drawn(repo: Path) -> None:
    write_icon(repo, icon_file("ICO@1790000003.per001.person", applies_to=("person",)))

    body = _body(_create(repo, {"display_icons": {"db": "ICO@1790000003.per001"}}))

    assert "$sprite" not in body and BLOCK_BEGIN not in body


def _boundary_item(item_type: str):
    from src.diagram_types.c4._c4_types import _ResolvedItem

    return _ResolvedItem(local_id="n1", item_type=item_type, alias="N_n1_0", label="EU Production",
                         description="", technology="Azure", external=False)


def test_a_deployment_node_draws_its_icon_as_a_sprite_and_a_group_in_its_title() -> None:
    from src.diagram_types.c4._projection_vocabulary import GROUP_TYPE, NODE_TYPE
    from src.diagram_types.c4.renderer import C4PumlRenderer, _Drawing

    sprite = f"img:${KEY}{{scale=0.75}}"
    drawing = _Drawing(sprites={"N_n1_0": sprite}, badges={"N_n1_0": f"<{sprite}>"})
    renderer = C4PumlRenderer({})

    node = renderer._open_boundary(_boundary_item(NODE_TYPE), drawing)
    group = renderer._open_boundary(_boundary_item(GROUP_TYPE), drawing)

    assert node.startswith("Deployment_Node(") and f'$sprite="img:${KEY}' in node
    assert group.startswith(f'Boundary(N_n1_0, "<img:${KEY}') and "$sprite" not in group


def test_an_item_drawn_from_a_model_entity_is_known_by_the_entitys_names_and_its_c4_type() -> None:
    """So a statement keyed by the entity's type, its specialization or the C4 type reaches it alike."""
    from src.diagram_types.c4._resolve_model import _item_from_entity
    from src.diagram_types.c4.renderer import _drawn
    from src.domain.ontology_representation.artifact_types import EntityRecord

    entity = EntityRecord(
        artifact_id="APP@1.a.orders", artifact_type="application-component", name="Orders", version="0.1.0",
        status="draft", domain="application", subdomain="", path=Path("x.md"), keywords=(), extra={},
        content_text="", display_blocks={}, display_label="Orders", display_alias="APP_a",
        specializations=("service",),
    )

    item = _item_from_entity(entity, entity.artifact_id, "container", external=False)

    assert _drawn(item).names == ("service", "application-component", "container")
    assert _drawn(_boundary_item("container")).names == ("container",)
