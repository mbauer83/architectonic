"""PlantUML's own arrangement, written down as a layout, raises none of the layout's geometry findings.

The measurement behind the rules' severities. Every element and every authored-grouping box of each
fixture picture is placed and sized where PlantUML drew it, the block is stored through the tools,
and verification is asked: an arrangement nobody has touched must not be reported as two connected
elements over each other, nor as a box hiding an element. A rule that fired here would fire on every
diagram the moment it is taken over.

Routes are not written down here: turning a drawn line into ports and bends is the router's work,
and what its output satisfies is that stage's to measure.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.application.modeling.binding_normalize import restore_diagram_shorthand
from src.domain.artifact_id import stable_id
from src.domain.diagrams.authored_groupings import GROUPING_ID_KEY, walk_groupings
from src.domain.diagrams.layout.box_aliases import authored_grouping_alias
from src.domain.diagrams.layout.geometry import Extent
from src.domain.diagrams.layout.rendered_picture import RenderedPicture
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.context import repo_cached, roots_key
from src.infrastructure.rendering.archimate_occurrences import instance_by_alias
from src.infrastructure.rendering.layout.plantuml_svg_reader import read_rendered_picture
from tests.support.rendered_pictures import RenderedModel, build_rendered_model, plantuml_available

pytestmark = pytest.mark.skipif(
    not plantuml_available(), reason="plantuml.jar not found — skipping rendered-picture assertions"
)

_SCENES = ("top-to-bottom", "occurrence", "groupings", "type-boxes")
_GEOMETRY = {"W376", "W377", "W378", "W379"}


@pytest.fixture(scope="module")
def model(tmp_path_factory: pytest.TempPathFactory) -> RenderedModel:
    return build_rendered_model(tmp_path_factory.mktemp("layouts-from-pictures"))


def _placed(extent: Extent) -> dict[str, int]:
    return {
        "x": round(extent.left), "y": round(extent.top),
        "w": max(1, round(extent.width)), "h": max(1, round(extent.height)),
    }


def _layout_from(model: RenderedModel, scene: str) -> tuple[str, dict[str, object]]:
    """The scene's diagram id, and a layout placing every instance and stated box where the picture has it."""
    path = Path(model.scenes[scene].path)
    stored = parse_frontmatter(path.read_text(encoding="utf-8"))
    picture = read_rendered_picture(model.scenes[scene].svg)
    assert isinstance(picture, RenderedPicture)
    repo = repo_cached(roots_key([model.repo]))
    entity_by_id = {str(i): repo.get_entity(str(i)) for i in stored["entity-ids-used"]}
    stated = restore_diagram_shorthand(stored.get("diagram-entities"), stored.get("bindings"))
    elements = {
        (stable_id(instance) if instance in entity_by_id else instance): _placed(extent)
        for alias, instance in instance_by_alias(stated, entity_by_id).items()
        if (extent := picture.extent_of(alias)) is not None
    }
    # A grouping's box is named by its rank among the groupings a body draws, in document order.
    boxes = {
        str(entry[GROUPING_ID_KEY]): _placed(extent)
        for rank, (_trail, entry) in enumerate(walk_groupings(stored.get("authored-groupings")), start=1)
        if (extent := picture.extent_of(authored_grouping_alias(rank))) is not None
    }
    assert elements, scene
    return str(stored["artifact-id"]), {"elements": elements, **({"boxes": boxes} if boxes else {})}


@pytest.mark.parametrize("scene", _SCENES)
def test_the_arrangement_plantuml_chose_is_stored_and_raises_no_geometry_finding(
    model: RenderedModel, scene: str
) -> None:
    diagram_id, layout = _layout_from(model, scene)

    written = mcp.artifact_edit_diagram(artifact_id=diagram_id, layout=layout, dry_run=False, repo_root=str(model.repo))

    assert written["wrote"], written
    path = str(model.scenes[scene].path)
    verified = asyncio.run(mcp.artifact_verify(path=path, repo_root=str(model.repo), repo_scope="engagement"))
    found = {issue["code"]: issue["message"] for issue in verified["issues"] if issue["code"] in _GEOMETRY | {"E371"}}
    assert found == {}


def test_the_grouped_scene_s_boxes_were_among_what_was_measured(model: RenderedModel) -> None:
    """Otherwise "no box hides an element" would be true of a layout that sized no box."""
    _diagram_id, layout = _layout_from(model, "groupings")

    assert len(layout.get("boxes", {})) == 2  # type: ignore[arg-type]
