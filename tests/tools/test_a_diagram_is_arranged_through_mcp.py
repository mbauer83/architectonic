"""MCP arranges a diagram as the REST layout routes do: a patch or intents, one write, the patch answered."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter

from src.domain.artifact_id import stable_id
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.diagram_composition import DiagramReplacement
from src.infrastructure.diagram_layout_wire import ArrangeIntent, LayoutPatch
from src.infrastructure.mcp.artifact_mcp.layout_tools import (
    artifact_arrange_diagram,
    artifact_query_diagram_layout,
    artifact_replace_diagram,
)
from src.infrastructure.rendering.layout.diagram_geometry import stored_geometry
from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file
from tests.support.rendered_pictures import RenderedModel, plantuml_available

INTENTS = TypeAdapter(list[ArrangeIntent])

pytestmark = pytest.mark.skipif(not plantuml_available(), reason="plantuml.jar not found")


@pytest.fixture
def model(rendered_model: RenderedModel) -> RenderedModel:
    """A copy of the model built once per worker: each test here writes to its own."""
    return rendered_model


def _keys(model: RenderedModel, path: Path) -> list[str]:
    geometry = stored_geometry(parse_diagram_file(path), path.stem, model.repo, process_runtime_catalogs().ontology)
    return [str(row["key"]) for row in geometry["elements"]][:2]  # type: ignore[index, union-attr]


def test_intents_are_written_and_the_compiled_patch_is_answered(model: RenderedModel) -> None:
    path = Path(model.scenes["top-to-bottom"].path)
    keys = _keys(model, path)
    answer = artifact_arrange_diagram(
        artifact_id=path.stem, intents=INTENTS.validate_python([{"intent": "align", "keys": keys, "edge": "left"}]),
        dry_run=False, repo_root=str(model.repo),
    )
    assert answer["wrote"] is True and answer["patch"]
    layout = parse_frontmatter(path.read_text(encoding="utf-8"))["layout"]
    assert layout["elements"][keys[0]]["x"] == layout["elements"][keys[1]]["x"]


def test_exactly_one_of_patch_or_intents_is_stated(model: RenderedModel) -> None:
    path = Path(model.scenes["top-to-bottom"].path)
    with pytest.raises(ValueError, match="exactly one"):
        artifact_arrange_diagram(artifact_id=path.stem, repo_root=str(model.repo))
    with pytest.raises(ValueError, match="exactly one"):
        artifact_arrange_diagram(artifact_id=path.stem, patch=LayoutPatch(), intents=[], repo_root=str(model.repo))


def test_grouping_intents_answer_the_compiled_groupings_and_write_nothing_on_a_dry_run(model: RenderedModel) -> None:
    path = Path(model.scenes["groupings"].path)
    before = path.read_text(encoding="utf-8")
    intents = INTENTS.validate_python([{"intent": "create_grouping", "label": "Pair", "keys": _keys(model, path)}])
    answer = artifact_arrange_diagram(artifact_id=path.stem, intents=intents, repo_root=str(model.repo))
    assert answer["wrote"] is False and path.read_text(encoding="utf-8") == before
    labels = [entry["label"] for entry in answer["authored_groupings"]]  # type: ignore[attr-defined]
    assert "Pair" in labels


def test_the_layout_read_answers_keys_extents_and_the_stored_block_without_drawings(model: RenderedModel) -> None:
    path = Path(model.scenes["top-to-bottom"].path)
    keys = _keys(model, path)
    artifact_arrange_diagram(
        artifact_id=path.stem, intents=INTENTS.validate_python([{"intent": "align", "keys": keys, "edge": "left"}]),
        dry_run=False, repo_root=str(model.repo),
    )

    read = artifact_query_diagram_layout(stable_id(path.stem), repo_root=str(model.repo))

    elements: list[dict[str, object]] = read["elements"]  # type: ignore[assignment]
    element_keys = {row["key"] for row in elements}
    assert set(keys) <= element_keys
    assert all(set(row) <= {"key", "label", "extent", "inside"} for row in elements)
    assert all(row["source"] in element_keys for row in read["relations"])  # type: ignore[attr-defined]
    assert read["layout"]["elements"][keys[0]]  # type: ignore[index]


def test_a_canvas_save_over_mcp_writes_an_occurrence_its_z_and_an_element_edit_in_one_write(
    model: RenderedModel,
) -> None:
    path = Path(model.scenes["top-to-bottom"].path)
    stored = parse_frontmatter(path.read_text(encoding="utf-8"))
    clerk = model.ids["clerk"]
    replacement = DiagramReplacement.model_validate({
        "diagram_type": stored["diagram-type"], "name": stored["name"],
        "entity_ids": stored["entity-ids-used"], "connection_ids": stored["connection-ids-used"],
        "diagram_entities": {"occurrence": [{"id": "clerk-again", "backing_entity_id": stable_id(clerk)}]},
        "layout_patch": {"elements": {"clerk-again": {"value": {"x": 40, "y": 40}}},
                         "z": {"clerk-again": {"value": 4}}},
        "commands": [{"op": "model.element.edit", "artifact_id": clerk, "summary": "Edited on the canvas"}],
        "dry_run": False,
    })

    answer = artifact_replace_diagram(artifact_id=path.stem, replacement=replacement, repo_root=str(model.repo))

    assert answer["wrote"] is True, answer
    body = path.read_text(encoding="utf-8")
    assert f"{model.alias('clerk')}__2" in body  # drawn, though its backing entity is named by its short id
    written = parse_frontmatter(body)["layout"]
    assert written["z"]["clerk-again"] == 4 and "clerk-again" in written["elements"]
    assert "Edited on the canvas" in next(model.repo.rglob(f"{clerk}.md")).read_text(encoding="utf-8")


def test_nesting_on_a_canvas_save_fits_the_grouping_as_the_arrange_nest_does(model: RenderedModel) -> None:
    """Regression: one nest, two outcomes. Carried by the save it kept the box's stored size; the arrange
    route fitted the box round its members. The save now fits it as the arrange does."""
    path = Path(model.scenes["groupings"].path)
    keys = _keys(model, path)
    # A laid-out diagram, so the grouping's box is stored and a stale size could survive the save.
    artifact_arrange_diagram(
        artifact_id=path.stem, intents=INTENTS.validate_python([{"intent": "align", "keys": keys, "edge": "top"}]),
        dry_run=False, repo_root=str(model.repo),
    )
    created = artifact_arrange_diagram(
        artifact_id=path.stem,
        intents=INTENTS.validate_python([{"intent": "create_grouping", "label": "Pair", "keys": keys[:1]}]),
        dry_run=False, repo_root=str(model.repo),
    )
    groupings: list[dict[str, object]] = created["authored_groupings"]  # type: ignore[assignment]
    grouping = next(one["id"] for one in groupings if one["label"] == "Pair")
    stored = parse_frontmatter(path.read_text(encoding="utf-8"))
    nest = [{"intent": "nest", "keys": keys[1:2], "grouping": grouping}]
    by_arrange = artifact_arrange_diagram(
        artifact_id=path.stem, intents=INTENTS.validate_python(nest), dry_run=True, repo_root=str(model.repo),
    )
    replacement = DiagramReplacement.model_validate({
        "diagram_type": stored["diagram-type"], "name": stored["name"],
        "entity_ids": stored["entity-ids-used"], "connection_ids": stored["connection-ids-used"],
        "authored_groupings": stored["authored-groupings"], "grouping_intents": nest,
        "layout_patch": {}, "dry_run": False,
    })

    answer = artifact_replace_diagram(artifact_id=path.stem, replacement=replacement, repo_root=str(model.repo))

    assert answer["wrote"] is True, answer
    saved = parse_frontmatter(path.read_text(encoding="utf-8"))["layout"]["boxes"][grouping]
    assert saved == by_arrange["layout"]["boxes"][grouping]  # type: ignore[index]
    assert saved != stored["layout"]["boxes"][grouping]
