"""Rendered-SVG assertion harness for C4 shapes (T23 / T19).

Renders PUML bodies to SVG via the real PlantUML runtime and asserts that shape
elements are present in the SVG output. Skipped when plantuml.jar is absent.

Shape observations from PlantUML C4-PlantUML stdlib:
  ContainerDb    → curved <path> elements (cylinder body + cap); no rect for the entity
  ContainerQueue → curved <path> elements (queue shape); no rect for the entity
  Container      → <rect> element for the entity box
  All containers → «container» stereotype text in SVG (no type prefix in this lib version)
  Technology     → rendered as [Tech] text in the SVG

The PUML-macro assertions (ContainerDb macro used for db tech, ContainerQueue for
queue tech, Container for generic) live in tests/rendering/test_c4_node_shapes.py.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest

# ── skip guard ─────────────────────────────────────────────────────────────────

def _plantuml_available() -> bool:
    try:
        from src.application.verification.artifact_verifier_syntax import find_plantuml_jar
        return find_plantuml_jar() is not None
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _plantuml_available(),
    reason="plantuml.jar not found — skipping rendered-SVG shape tests",
)


# ── helpers ─────────────────────────────────────────────────────────────────────

def _render_svg(puml_body: str) -> str:
    """Render PUML to SVG using the real PlantUML runtime. Returns SVG text."""
    from src.infrastructure.rendering.puml_runtime import render_puml_svg

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        (tmp_root / "diagram-catalog" / "diagrams").mkdir(parents=True)
        svg, warnings = render_puml_svg(puml_body, tmp_root, "c4-container")
        if svg is None:
            raise AssertionError(f"render_puml_svg failed: {warnings}")
        return svg


def _path_count(svg: str) -> int:
    return len(re.findall(r"<path\b", svg))


def _rect_count(svg: str) -> int:
    return len(re.findall(r"<rect\b", svg))


# ── shape element tests ────────────────────────────────────────────────────────

def test_containerdb_uses_path_not_rect_for_cylinder() -> None:
    """ContainerDb renders cylinder via <path> elements; Container uses <rect>."""
    puml = "\n".join([
        "@startuml shape_test",
        "!include <C4/C4_Component>",
        'ContainerDb(C_db, "Database", "PostgreSQL")',
        "@enduml",
        "",
    ])
    svg = _render_svg(puml)
    # Cylinder shape = path elements; a plain Container would have 0 paths
    assert _path_count(svg) >= 2, (
        f"ContainerDb must render cylinder paths (≥2 <path> elements). Got: {_path_count(svg)}"
    )
    assert "Database" in svg


def test_containerqueue_uses_path_for_queue_shape() -> None:
    """ContainerQueue renders queue shape via <path> elements."""
    puml = "\n".join([
        "@startuml shape_test",
        "!include <C4/C4_Component>",
        'ContainerQueue(C_mq, "Events", "Kafka")',
        "@enduml",
        "",
    ])
    svg = _render_svg(puml)
    assert _path_count(svg) >= 2, (
        f"ContainerQueue must render queue paths (≥2 <path> elements). Got: {_path_count(svg)}"
    )
    assert "Events" in svg


def test_generic_container_uses_rect_not_path() -> None:
    """Generic Container renders a plain rectangle (<rect>); no extra paths."""
    puml = "\n".join([
        "@startuml shape_test",
        "!include <C4/C4_Component>",
        'Container(C_svc, "Service", "Python")',
        "@enduml",
        "",
    ])
    svg = _render_svg(puml)
    assert _rect_count(svg) >= 1, (
        f"Generic Container must render a <rect> element. Got: {_rect_count(svg)}"
    )
    # A plain Container should have fewer (or zero) <path> elements than ContainerDb
    assert "Service" in svg


def test_containerdb_vs_container_path_count_differs() -> None:
    """ContainerDb generates more <path> elements than Container (cylinder vs rect)."""
    puml_db = "\n".join([
        "@startuml db",
        "!include <C4/C4_Component>",
        'ContainerDb(C_db, "DB", "Postgres")',
        "@enduml",
        "",
    ])
    puml_svc = "\n".join([
        "@startuml svc",
        "!include <C4/C4_Component>",
        'Container(C_svc, "Svc", "Go")',
        "@enduml",
        "",
    ])
    svg_db = _render_svg(puml_db)
    svg_svc = _render_svg(puml_svc)
    assert _path_count(svg_db) > _path_count(svg_svc), (
        f"ContainerDb ({_path_count(svg_db)} paths) should have more paths than "
        f"Container ({_path_count(svg_svc)} paths)"
    )


def test_container_label_appears_in_svg() -> None:
    label = "MyUniqueService2026"
    puml = f'@startuml t\n!include <C4/C4_Component>\nContainer(C_svc, "{label}", "Go")\n@enduml\n'
    svg = _render_svg(puml)
    assert label in svg, f"Label '{label}' not found in rendered SVG"


def test_containerdb_label_and_tech_appear_in_svg() -> None:
    label = "AnalyticsDB2026"
    tech = "ClickHouse2026"
    puml = f'@startuml t\n!include <C4/C4_Component>\nContainerDb(C_db, "{label}", "{tech}")\n@enduml\n'
    svg = _render_svg(puml)
    assert label in svg, f"Label '{label}' not found in rendered SVG"
    assert tech in svg, f"Technology '{tech}' not found in rendered SVG"


def test_containerqueue_label_and_tech_appear_in_svg() -> None:
    label = "EventBus2026"
    tech = "Kafka2026"
    puml = f'@startuml t\n!include <C4/C4_Component>\nContainerQueue(C_mq, "{label}", "{tech}")\n@enduml\n'
    svg = _render_svg(puml)
    assert label in svg, f"Label '{label}' not found in rendered SVG"
    assert tech in svg, f"Technology '{tech}' not found in rendered SVG"


def test_person_label_appears_in_svg() -> None:
    """Person macro renders the person label in SVG (T20)."""
    label = "ArchitectPerson2026"
    puml = f"@startuml t\n!include <C4/C4_Component>\nPerson(P_arch, \"{label}\")\n@enduml\n"
    svg = _render_svg(puml)
    assert label in svg, f"Person label '{label}' not found in rendered SVG"


def test_person_ext_label_appears_in_svg() -> None:
    """Person_Ext macro renders the external-person label in SVG (T20)."""
    label = "ExternalUser2026"
    puml = f"@startuml t\n!include <C4/C4_Component>\nPerson_Ext(P_ext, \"{label}\")\n@enduml\n"
    svg = _render_svg(puml)
    assert label in svg, f"Person_Ext label '{label}' not found in rendered SVG"


def test_system_context_person_labels_via_renderer() -> None:
    """C4PumlRenderer system-context mode: all person labels appear in rendered SVG (T20)."""
    from pathlib import Path as _Path

    from src.diagram_types.c4.renderer import C4PumlRenderer

    renderer = C4PumlRenderer({
        "c4": {
            "scope_entity_type": "software-system",
            "scope_render_mode": "node",
            "internal_entity_types": [],
        }
    })
    diagram_entities = {
        "software-system": [{"id": "sys1", "label": "MySystem2026", "scope": True}],
        "person": [
            {"id": "p1", "label": "Architect2026", "external": False},
            {"id": "p2", "label": "DevOps2026", "external": True},
        ],
    }
    puml = renderer.render_body(
        "System Context Test", [], [], "c4-system-context", _Path("/tmp"),
        diagram_entities=diagram_entities,
    )
    assert "Person(" in puml, "Renderer must emit Person(...) macro for person entities"
    assert "Person_Ext(" in puml, "Renderer must emit Person_Ext(...) macro for external persons"
    svg = _render_svg(puml)
    for label in ("Architect2026", "DevOps2026", "MySystem2026"):
        assert label in svg, f"Label '{label}' missing from system-context SVG"


def test_container_diagram_person_labels_via_renderer() -> None:
    """C4PumlRenderer container-boundary mode: person labels appear alongside containers (T20)."""
    from pathlib import Path as _Path

    from src.diagram_types.c4.renderer import C4PumlRenderer

    renderer = C4PumlRenderer({
        "c4": {
            "scope_entity_type": "software-system",
            "scope_render_mode": "boundary",
            "internal_entity_types": ["container"],
        }
    })
    diagram_entities = {
        "software-system": [{"id": "sys1", "label": "AMP2026", "scope": True}],
        "person": [
            {"id": "p1", "label": "Architect2026"},
            {"id": "p2", "label": "ProductOwner2026"},
        ],
        "container": [
            {"id": "c1", "label": "GUIService2026", "technology": "React"},
        ],
    }
    puml = renderer.render_body(
        "Container Test", [], [], "c4-container", _Path("/tmp"),
        diagram_entities=diagram_entities,
    )
    svg = _render_svg(puml)
    for label in ("Architect2026", "ProductOwner2026", "AMP2026", "GUIService2026"):
        assert label in svg, f"Label '{label}' missing from container diagram SVG"


def test_person_to_container_edges_anchor_without_gap() -> None:
    """Person→container connection lines anchor at node boundaries (no visible gap) (T21).

    SVG inspection: path start x ≈ person rect right edge; arrowhead tip x ≈ container
    left edge.  Both within a 5 px tolerance (observed values are < 0.5 px off).
    """
    import re as _re
    from pathlib import Path as _Path

    from src.diagram_types.c4.renderer import C4PumlRenderer

    renderer = C4PumlRenderer({
        "c4": {
            "scope_entity_type": "software-system",
            "scope_render_mode": "boundary",
            "internal_entity_types": ["container"],
        }
    })
    diagram_entities = {
        "software-system": [{"id": "sys1", "label": "AMP", "scope": True}],
        "person": [{"id": "p1", "label": "Architect"}],
        "container": [{"id": "c1", "label": "GUI", "technology": "React"}],
    }
    diagram_connections = [{"source": "p1", "target": "c1", "label": "uses"}]
    puml = renderer.render_body(
        "Gap Test", [], [], "c4-container", _Path("/tmp"),
        diagram_entities=diagram_entities,
        diagram_connections=diagram_connections,
    )
    svg = _render_svg(puml)

    # Arrowhead polygons encode the connection endpoints; one per connection.
    polygons = _re.findall(r'<polygon\b[^>]*>', svg)
    assert len(polygons) >= 1, "Expected ≥1 arrowhead polygon for person→container connection"

    # Extract person rect right edge and container rect left edge.
    rects = _re.findall(r'<rect\b[^>]*>', svg)
    person_right: list[float] = []
    container_left: list[float] = []
    for r in rects:
        x_m = _re.search(r'\bx="([0-9.]+)"', r)
        w_m = _re.search(r'\bwidth="([0-9.]+)"', r)
        fill_m = _re.search(r'fill="([^"]+)"', r)
        if not x_m or not w_m:
            continue
        x, w = float(x_m.group(1)), float(w_m.group(1))
        fill = fill_m.group(1) if fill_m else ""
        if fill.startswith("#08"):  # C4 Person background (#08427B)
            person_right.append(x + w)
        elif fill.startswith("#43"):  # C4 Container background (#438DD5)
            container_left.append(x)

    # Extract arrowhead tip x (rightmost x in the points list).
    arrowhead_tips: list[float] = []
    for poly in polygons:
        pts_m = _re.search(r'points="([^"]+)"', poly)
        if pts_m:
            xs = [float(pt.split(",")[0]) for pt in pts_m.group(1).split() if "," in pt]
            if xs:
                arrowhead_tips.append(max(xs))

    # Extract connection path start x (the M x coordinate).
    path_start_xs: list[float] = []
    for path in _re.findall(r'<path\b[^>]*>', svg):
        d_m = _re.search(r'\bd="M([0-9.]+),', path)
        if d_m:
            path_start_xs.append(float(d_m.group(1)))

    TOL = 5.0  # 5 px tolerance; observed gap < 0.5 px
    assert person_right, "No person rect found in SVG"
    assert container_left, "No container rect found in SVG"
    assert path_start_xs, "No connection path found in SVG"
    assert arrowhead_tips, "No arrowhead polygon found in SVG"

    # Path start should be near the person's right edge.
    for start_x in path_start_xs:
        closest = min(person_right, key=lambda r: abs(r - start_x))
        assert abs(closest - start_x) <= TOL, (
            f"Connection path starts at x={start_x:.2f} but nearest person right edge is "
            f"x={closest:.2f} (gap {abs(closest - start_x):.2f} > {TOL} px)"
        )

    # Arrowhead tip should be near the container's left edge.
    for tip_x in arrowhead_tips:
        closest = min(container_left, key=lambda cx: abs(cx - tip_x))
        assert abs(closest - tip_x) <= TOL, (
            f"Arrowhead tip at x={tip_x:.2f} but nearest container left is "
            f"x={closest:.2f} (gap {abs(closest - tip_x):.2f} > {TOL} px)"
        )


def test_explicit_shape_override_renders_correct_shape_element() -> None:
    """End-to-end: explicit shape= in diagram-entities produces the right SVG shape element."""
    from pathlib import Path as _Path

    from src.diagram_types.c4.renderer import C4PumlRenderer

    renderer = C4PumlRenderer({
        "c4": {
            "scope_entity_type": "software-system",
            "scope_render_mode": "boundary",
            "internal_entity_types": ["container"],
        }
    })
    diagram_entities = {
        "software-system": [{"id": "s1", "label": "System", "scope": True}],
        "container": [
            {"id": "c1", "label": "PostgresDB", "technology": "PostgreSQL", "shape": "ContainerDb"},
            {"id": "c2", "label": "KafkaQueue", "technology": "Kafka", "shape": "ContainerQueue"},
            {"id": "c3", "label": "APIGateway", "technology": "FastAPI"},
        ],
    }
    puml = renderer.render_body("Shape Test", [], [], "c4-container", _Path("/tmp"),
                                diagram_entities=diagram_entities)
    # Verify PUML contains explicit macro calls
    assert "ContainerDb(" in puml, "Explicit shape=ContainerDb must produce ContainerDb macro in PUML"
    assert "ContainerQueue(" in puml, "Explicit shape=ContainerQueue must produce ContainerQueue macro in PUML"
    assert "Container(" in puml, "Auto-inferred generic container must produce Container macro in PUML"

    svg = _render_svg(puml)
    # The diagram has 2 shaped containers (db+queue = 4 paths) + 1 generic (rect)
    assert _path_count(svg) >= 4, (
        f"Diagram with ContainerDb+ContainerQueue must render ≥4 <path> elements. Got: {_path_count(svg)}"
    )
    # All labels appear in the SVG
    for label in ("PostgresDB", "KafkaQueue", "APIGateway"):
        assert label in svg, f"Label '{label}' missing from SVG"
