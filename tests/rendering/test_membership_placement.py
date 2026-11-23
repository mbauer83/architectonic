"""New members are placed beside their already placed neighbours; boxes follow their members."""

from dataclasses import replace

from src.domain.diagrams.layout.box_aliases import domain_box_alias
from src.domain.diagrams.layout.geometry import Extent
from src.domain.diagrams.layout.laid_out_diagram import DrawnKind, LaidOutDiagram
from src.domain.diagrams.layout.layout_block import Layout, Placed
from src.domain.diagrams.layout.rendered_picture import DrawnBox, DrawnElement, RenderedPicture
from src.infrastructure.rendering.layout.membership_placement import with_new_members


def test_neighbours_new_ruled_box_and_orphaned_stacking():
    alias = domain_box_alias("business")
    old_box = "rule:domain=application"
    original = Layout(
        elements={"left": Placed(0, 0), "right": Placed(400, 0)}, boxes={old_box: Placed(20, 30)}, z={old_box: 1},
    )
    area = Extent(0, 0, 80, 40)
    shapes = {k: DrawnElement(k, area, alias) for k in ("left", "right", "new")}
    picture = RenderedPicture(area, shapes, {alias: DrawnBox(alias, Extent(-10, -20, 90, 55), None)}, ())
    diagram = LaidOutDiagram(
        original, {k: k for k in shapes}, relations={"l": ("new", "left"), "r": ("right", "new")},
        kinds={k: DrawnKind("business", "role") for k in shapes},
    )
    result = with_new_members(picture, diagram, frozenset({"new"}))
    assert result.elements == {**original.elements, "new": Placed(200, 0)}
    assert set(result.boxes) == {"rule:domain=business"}
    assert not result.z
    close = with_new_members(picture, replace(diagram, relations={"l": ("left", "new")}), frozenset({"new"}))
    assert close.elements["new"] != original.elements["left"]
    place = close.elements["new"]
    assert Extent(place.x, place.y, place.x + 80, place.y + 40).overlap_with(area) is None


def test_a_new_member_cannot_close_a_retained_relations_only_stated_port():
    from src.domain.diagrams.layout.layout_block import Port, Route, Side
    from src.domain.diagrams.layout.rendered_picture import DrawnRelation, EndMark, MarkShape
    from src.infrastructure.rendering.layout.arrangement import arrange

    shapes = {k: DrawnElement(k, Extent(0, top, 80, top + 40), None)
              for k, top in (("process", -240), ("service", 0), ("new", -70))}
    r = DrawnRelation(("process", "service"), "association", (), (), second_marks=(EndMark(MarkShape.POLYGON, (), True),))
    picture = RenderedPicture(Extent(-100, -300, 300, 200), shapes, {}, (r,))
    route = Route(target=Port(Side.TOP, 0.5))
    key = "process---service@@association"
    layout = Layout(elements={"process": Placed(0, -240), "service": Placed(0, 0)}, relations={key: route})
    diagram = LaidOutDiagram(layout, {k: k for k in shapes}, relations={key: r.ends})
    placed = with_new_members(picture, diagram, frozenset({"new"}))
    assert placed.elements["process"] == layout.elements["process"]
    assert placed.elements["service"] == layout.elements["service"]
    assert not arrange(picture, replace(diagram, layout=placed)).unroutable
