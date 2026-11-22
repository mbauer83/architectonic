"""New members are placed beside their already placed neighbours; boxes follow their members."""

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
        original, {k: k for k in shapes}, kinds={k: DrawnKind("business", "role") for k in shapes},
    )
    result = with_new_members(picture, diagram, frozenset({"new"}), {"l": ("new", "left"), "r": ("right", "new")})
    assert result.elements == {**original.elements, "new": Placed(200, 0)}
    assert set(result.boxes) == {"rule:domain=business"}
    assert not result.z
    close = with_new_members(picture, diagram, frozenset({"new"}), {"l": ("left", "new")})
    assert close.elements["new"] != original.elements["left"]
    place = close.elements["new"]
    assert Extent(place.x, place.y, place.x + 80, place.y + 40).overlap_with(area) is None
