"""MCP arranges a diagram as the REST layout routes do: a patch or intents, one write, the patch answered."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.mcp.artifact_mcp.layout_tools import artifact_arrange_diagram
from src.infrastructure.rendering.layout.diagram_geometry import stored_geometry
from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file
from tests.support.rendered_pictures import RenderedModel, build_rendered_model, plantuml_available

pytestmark = pytest.mark.skipif(not plantuml_available(), reason="plantuml.jar not found")


@pytest.fixture
def model(tmp_path: Path) -> RenderedModel:
    return build_rendered_model(tmp_path)


def _keys(model: RenderedModel, path: Path) -> list[str]:
    geometry = stored_geometry(parse_diagram_file(path), path.stem, model.repo, process_runtime_catalogs().ontology)
    return [str(row["key"]) for row in geometry["elements"]][:2]  # type: ignore[index, union-attr]


def test_intents_are_written_and_the_compiled_patch_is_answered(model: RenderedModel) -> None:
    path = Path(model.scenes["top-to-bottom"].path)
    keys = _keys(model, path)
    answer = artifact_arrange_diagram(
        artifact_id=path.stem, intents=[{"intent": "align", "keys": keys, "edge": "left"}],
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
        artifact_arrange_diagram(artifact_id=path.stem, patch={}, intents=[], repo_root=str(model.repo))


def test_grouping_intents_answer_the_compiled_groupings_and_write_nothing_on_a_dry_run(model: RenderedModel) -> None:
    path = Path(model.scenes["groupings"].path)
    before = path.read_text(encoding="utf-8")
    answer = artifact_arrange_diagram(
        artifact_id=path.stem, intents=[{"intent": "create_grouping", "label": "Pair", "keys": _keys(model, path)}],
        repo_root=str(model.repo),
    )
    assert answer["wrote"] is False and path.read_text(encoding="utf-8") == before
    labels = [entry["label"] for entry in answer["authored_groupings"]]  # type: ignore[attr-defined]
    assert "Pair" in labels
