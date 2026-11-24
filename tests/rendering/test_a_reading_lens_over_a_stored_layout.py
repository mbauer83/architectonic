"""A reading lens over a diagram that states a layout: the reader's picture, still drawn from that layout.

The lens restyles the body before PlantUML runs — fills, printed attribute lines, a legend — and a
laid-out diagram is then composed again from its stated layout (`laid_out_rendering`). Each half was
tested on its own; nothing asked of the pair whether the lens survives the composition and the layout
survives the lens. Over the product's own path: a model written with the authoring tools, attributes
declared by the type's attribute schema, a layout stored by the editor's layout patch, and the picture
asked for at the address the diagram page asks (`GET /api/diagrams/{id}/svg`).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.repository import ArtifactRepository
from src.application.artifacts.schema import SCHEMATA_DIR, clear_schema_cache
from src.application.modeling.diagram_identities import alias_by_instance
from src.domain.diagrams.layout.picture_checks import PictureDefect, check_picture
from src.domain.diagrams.layout.rendered_picture import RenderedPicture
from src.domain.repository.frontmatter import parse_frontmatter
from src.domain.viewpoints.viewpoint_style_values import AD_HOC_RAMP_TOKENS, token_color
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.rendering.layout.plantuml_svg_reader import (
    RenderedDrawing,
    read_rendered_drawing,
)
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers.diagrams.router import router as diagrams_router
from tests.support.api_app import build_api_app
from tests.support.rendered_pictures import RenderedModel, build_rendered_model, plantuml_available
from tests.support.rest_state import reset_state_for_test

pytestmark = pytest.mark.skipif(not plantuml_available(), reason="plantuml.jar not found")

#: The attributes a function's schema declares, and what each drawn function carries.
_SCHEMA = {
    "type": "object",
    "properties": {
        "risk_score": {"type": "integer", "minimum": 1, "maximum": 9},
        "team": {"type": "string"},
        "remit": {"type": "string"},
    },
}
_CARRIED = {
    "check": {"risk_score": 1, "team": "Stock"},
    "ship": {"risk_score": 5, "team": "Dispatch", "remit": "The order fulfilment and shipping operations team"},
    "bill": {"risk_score": 9, "team": "Finance", "remit": "Invoicing, dunning and the reconciliation of payments"},
}

#: What the reader asks for: colour by the score, print it and the team, explain the picture.
_LENS = {"colour_by": "risk_score", "print": ["risk_score", "team"], "legend": "true"}

#: Where the editor's patch moves the node: well away from where PlantUML drew it.
_MOVED_TO = {"x": 900, "y": 40}

#: How far a placed shape may sit from where the layout put it.
_PLACED = 0.01


@dataclass(frozen=True)
class StoredDiagram:
    model: RenderedModel
    artifact_id: str
    #: What the diagram stores: the layout block of its frontmatter, and the alias of each instance.
    layout: dict[str, dict[str, dict[str, int]]]
    aliases: dict[str, str]


@dataclass(frozen=True)
class LaidOutScene:
    stored: StoredDiagram
    client: TestClient

    @property
    def model(self) -> RenderedModel:
        return self.stored.model

    def svg(self, **lens: object) -> str:
        answer = self.client.get(f"/api/diagrams/{self.stored.artifact_id}/svg", params=lens)
        assert answer.status_code == 200, answer.text
        return answer.text


@contextmanager
def _served(model: RenderedModel) -> Iterator[TestClient]:
    # The schema files are cached per root, and the model's own writes read this one as absent.
    clear_schema_cache()
    s.init_state(ArtifactRepository(shared_artifact_index([model.repo])), model.repo, None)
    try:
        with TestClient(build_api_app(diagrams_router)) as client:
            yield client
    finally:
        reset_state_for_test()
        clear_schema_cache()


@pytest.fixture(scope="module")
def stored(tmp_path_factory: pytest.TempPathFactory) -> StoredDiagram:
    model = build_rendered_model(tmp_path_factory.mktemp("lens-over-layout"))
    schemata = model.repo / SCHEMATA_DIR
    schemata.mkdir(parents=True, exist_ok=True)
    (schemata / "attributes.function.schema.json").write_text(json.dumps(_SCHEMA), encoding="utf-8")
    clear_schema_cache()
    for nickname, carried in _CARRIED.items():
        written = mcp.artifact_edit_entity(
            artifact_id=model.ids[nickname], properties=dict(carried), dry_run=False, repo_root=str(model.repo)
        )
        assert written["wrote"], written

    path = Path(model.scenes["top-to-bottom"].path)
    with _served(model) as client:
        geometry = client.get(f"/api/diagrams/{path.stem}/layout/geometry").json()
        broker = next(row["key"] for row in geometry["elements"] if row["alias"] == model.alias("broker"))
        # The editor's Save: an automatic diagram is taken over whole, and the node is moved.
        patched = client.patch(
            f"/api/diagrams/{path.stem}/layout",
            json={"patch": {"elements": {broker: {"value": _MOVED_TO, "based_on": None}}}, "dry_run": False},
        )
        assert patched.status_code == 200, patched.text
    frontmatter = dict(parse_frontmatter(path.read_text(encoding="utf-8")))
    return StoredDiagram(
        model=model,
        artifact_id=path.stem,
        layout=frontmatter["layout"],  # type: ignore[arg-type]
        aliases=alias_by_instance(frontmatter),
    )


@pytest.fixture
def scene(stored: StoredDiagram) -> Iterator[LaidOutScene]:
    """The diagram served: the process state is reset after every test, so it is set up for each."""
    with _served(stored.model) as client:
        yield LaidOutScene(stored=stored, client=client)


def _drawing(svg: str) -> RenderedDrawing:
    drawing = read_rendered_drawing(svg)
    assert isinstance(drawing, RenderedDrawing), drawing
    return drawing


def _picture(svg: str) -> RenderedPicture:
    return _drawing(svg).picture


def _fill(drawing: RenderedDrawing, alias: str) -> str:
    """The fill of the outline PlantUML drew the element with: the first filled part of its group."""
    outline = next(part for part in drawing.shapes[alias] if part.get("fill"))
    return str(outline.get("fill")).upper()


def _printed(scene: LaidOutScene) -> dict[str, str]:
    """Each function's alias, and the label a reader should see: its name and the lines they printed."""
    names = {"check": "Check Stock", "ship": "Ship Goods", "bill": "Bill Customer"}
    return {
        scene.model.alias(nickname): (
            f"{names[nickname]} risk_score: {carried['risk_score']} team: {carried['team']}"
        )
        for nickname, carried in _CARRIED.items()
    }


class TestTheLensIsDrawn:
    def test_the_attributes_are_printed_with_their_elements(self, scene: LaidOutScene) -> None:
        picture = _picture(scene.svg(**_LENS))

        for alias, label in _printed(scene).items():
            assert picture.elements[alias].label == label

    def test_no_printed_line_leaks_its_markup(self, scene: LaidOutScene) -> None:
        """The second printed attribute was drawn at full size with a literal `</size>` after it."""
        picture = _picture(scene.svg(**_LENS))

        words = [word.text for element in picture.elements.values() for word in element.words]
        assert not [word for word in words if "<" in word or ">" in word]

    def test_colour_by_attribute_fills_the_elements_along_the_ramp(self, scene: LaidOutScene) -> None:
        drawing = _drawing(scene.svg(**_LENS))
        low, high = (token_color(token).upper() for token in AD_HOC_RAMP_TOKENS)
        check, ship, bill = (_fill(drawing, scene.model.alias(nickname)) for nickname in ("check", "ship", "bill"))

        assert (check, bill) == (low, high)
        assert ship not in (low, high)

    def test_an_element_the_attribute_says_nothing_about_keeps_its_kind_s_fill(self, scene: LaidOutScene) -> None:
        customer = scene.model.alias("customer")

        assert _fill(_drawing(scene.svg(**_LENS)), customer) == _fill(_drawing(scene.svg()), customer)


class TestTheLayoutStillPlacesThem:
    def test_every_element_is_drawn_where_the_stored_layout_puts_it(self, scene: LaidOutScene) -> None:
        picture = _picture(scene.svg(**_LENS))

        compared = 0
        for instance, where in scene.stored.layout["elements"].items():
            alias = scene.stored.aliases[instance]
            if alias not in picture.elements:
                continue  # a composite drawn as a box: placed, but not an element of the picture
            drawn = picture.elements[alias].extent
            assert (drawn.left, drawn.top) == pytest.approx((where["x"], where["y"]), abs=_PLACED), alias
            compared += 1
        assert compared == len(picture.elements)
        broker = picture.elements[scene.model.alias("broker")].extent
        assert (broker.left, broker.top) == pytest.approx((_MOVED_TO["x"], _MOVED_TO["y"]), abs=_PLACED)

    def test_a_printed_element_grows_to_hold_its_lines_and_holds_every_word(self, scene: LaidOutScene) -> None:
        authored, lensed = _picture(scene.svg()), _picture(scene.svg(**_LENS))

        for alias in _printed(scene):
            grown = lensed.elements[alias]
            assert grown.extent.height > authored.elements[alias].extent.height, alias
            for word in grown.words:
                assert grown.extent.left <= word.start.x, (alias, word)
                assert word.start.x + word.width <= grown.extent.right, (alias, word)
                assert grown.extent.top < word.start.y < grown.extent.bottom, (alias, word)

    def test_the_grown_elements_overlap_nothing(self, scene: LaidOutScene) -> None:
        report = check_picture(_picture(scene.svg(**_LENS)))

        for defect in (
            PictureDefect.SHAPES_OVERLAP, PictureDefect.LABEL_WIDER_THAN_SHAPE, PictureDefect.BOX_OVER_NON_MEMBER,
        ):
            assert not report.of(defect), defect


class TestTheLegend:
    def test_the_legend_for_the_reading_is_drawn(self, scene: LaidOutScene) -> None:
        picture = _picture(scene.svg(**_LENS))

        legend = next(
            (run for run in picture.surrounding if "risk_score" in {word.text for word in run}), None
        )
        assert legend is not None, [[word.text for word in run] for run in picture.surrounding]
        assert {"lower", "higher"} <= {word.text for word in legend}

    def test_the_legend_sits_on_the_canvas_clear_of_every_shape(self, scene: LaidOutScene) -> None:
        picture = _picture(scene.svg(**_LENS))
        legend = next(run for run in picture.surrounding if "risk_score" in {word.text for word in run})
        shapes = [drawn.extent for drawn in (*picture.elements.values(), *picture.boxes.values())]

        for word in legend:
            assert picture.canvas.left <= word.start.x and word.start.x + word.width <= picture.canvas.right
            assert picture.canvas.top <= word.start.y <= picture.canvas.bottom
            assert not [
                shape for shape in shapes
                if shape.left <= word.start.x <= shape.right and shape.top <= word.start.y <= shape.bottom
            ], word


@pytest.mark.xfail(
    strict=True,
    reason=(
        "A stored layout states where each element is, and its size only where an author resized it; "
        "a printed attribute grows the element in place, so a long value draws it over its neighbour "
        "and the box it is in over the next box. Nothing makes room for what a lens adds."
    ),
)
def test_a_long_printed_value_still_leaves_the_shapes_apart(scene: LaidOutScene) -> None:
    report = check_picture(_picture(scene.svg(colour_by="risk_score", print=["remit"])))

    assert not report.of(PictureDefect.SHAPES_OVERLAP)
