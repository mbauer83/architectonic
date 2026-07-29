"""Tests for WU-E7: C4 standard node shapes via C4-PlantUML stdlib macros.

Shape resolution order:
  (1) explicit ``shape`` attribute on diagram entity → use that macro name directly
  (2) technology field → lookup in db/queue keyword sets → ContainerDb/ContainerQueue/etc.
  (3) fallback → generic Container/Component/System macro for the item type

stdlib include: ``!include <C4/C4_Component>`` is emitted in every PUML body.
"""
from __future__ import annotations

from pathlib import Path

from src.diagram_types.c4._resolve import _ResolvedItem
from src.diagram_types.c4.renderer import C4PumlRenderer, _c4_macro_name, _tech_variant

# ── helpers ────────────────────────────────────────────────────────────────────

def _item(
    *,
    item_type: str = "container",
    alias: str = "C_alias",
    label: str = "My Item",
    technology: str = "",
    external: bool = False,
    shape: str | None = None,
) -> _ResolvedItem:
    return _ResolvedItem(
        local_id="x1",
        item_type=item_type,
        alias=alias,
        label=label,
        description="",
        technology=technology,
        external=external,
        shape=shape,
    )


def _renderer() -> C4PumlRenderer:
    return C4PumlRenderer({
        "c4": {
            "scope_entity_type": "software-system",
            "scope_render_mode": "node",
            "internal_entity_types": [],
        }
    })


def _render_standalone(diagram_entities: dict) -> str:
    r = C4PumlRenderer({
        "c4": {
            "scope_entity_type": "software-system",
            "scope_render_mode": "boundary",
            "internal_entity_types": ["container"],
        }
    })
    return r.render_body("Test", [], [], "c4-container", Path("/tmp"),
                         diagram_entities=diagram_entities)


# ── _tech_variant unit tests ───────────────────────────────────────────────────

def test_tech_variant_db_postgres() -> None:
    assert _tech_variant("PostgreSQL") == "db"


def test_tech_variant_db_mysql() -> None:
    assert _tech_variant("MySQL 8.0") == "db"


def test_tech_variant_db_mongodb() -> None:
    assert _tech_variant("MongoDB Atlas") == "db"


def test_tech_variant_queue_kafka() -> None:
    assert _tech_variant("Apache Kafka") == "queue"


def test_tech_variant_queue_rabbitmq() -> None:
    assert _tech_variant("RabbitMQ") == "queue"


def test_tech_variant_generic_react() -> None:
    assert _tech_variant("React") == "generic"


def test_tech_variant_generic_empty() -> None:
    assert _tech_variant("") == "generic"


def test_tech_variant_case_insensitive() -> None:
    assert _tech_variant("POSTGRESQL") == "db"
    assert _tech_variant("KAFKA") == "queue"


# ── _c4_macro_name unit tests ──────────────────────────────────────────────────

def test_macro_name_person_internal() -> None:
    assert _c4_macro_name("person", "generic", False) == "Person"


def test_macro_name_person_external() -> None:
    assert _c4_macro_name("person", "generic", True) == "Person_Ext"


def test_macro_name_system_internal() -> None:
    assert _c4_macro_name("software-system", "generic", False) == "System"


def test_macro_name_system_external() -> None:
    assert _c4_macro_name("software-system", "generic", True) == "System_Ext"


def test_macro_name_system_db() -> None:
    assert _c4_macro_name("software-system", "db", False) == "SystemDb"


def test_macro_name_container_db() -> None:
    assert _c4_macro_name("container", "db", False) == "ContainerDb"


def test_macro_name_container_queue() -> None:
    assert _c4_macro_name("container", "queue", False) == "ContainerQueue"


def test_macro_name_container_generic() -> None:
    assert _c4_macro_name("container", "generic", False) == "Container"


def test_macro_name_container_external_db() -> None:
    assert _c4_macro_name("container", "db", True) == "ContainerDb_Ext"


def test_macro_name_component_db() -> None:
    assert _c4_macro_name("component", "db", False) == "ComponentDb"


def test_macro_name_component_queue() -> None:
    assert _c4_macro_name("component", "queue", False) == "ComponentQueue"


# ── _render_item shape-resolution tests ───────────────────────────────────────

def test_render_item_explicit_shape_overrides_tech_inference() -> None:
    """Explicit shape= controls the macro name; technology still passed as content arg."""
    renderer = _renderer()
    item = _item(item_type="container", alias="C1", label="Storage",
                 technology="PostgreSQL",  # would infer ContainerDb
                 shape="Container")        # explicit override → Container shape
    rendered = renderer._render_item(item)
    # Shape override → Container macro (not ContainerDb); tech still appears as arg.
    assert rendered.startswith("Container(")
    assert "ContainerDb" not in rendered
    assert "PostgreSQL" in rendered


def test_render_item_explicit_shape_with_external_appends_ext() -> None:
    """Explicit shape + external=True → _Ext suffix applied automatically."""
    renderer = _renderer()
    item = _item(item_type="container", alias="C_ext", label="Ext DB",
                 technology="PostgreSQL", shape="ContainerDb", external=True)
    rendered = renderer._render_item(item)
    assert rendered.startswith("ContainerDb_Ext(")
    assert "PostgreSQL" in rendered


def test_render_item_explicit_shape_already_ext_not_doubled() -> None:
    """If shape already includes _Ext suffix it is not doubled."""
    renderer = _renderer()
    item = _item(item_type="container", alias="C_ext2", label="Ext Queue",
                 shape="ContainerQueue_Ext", external=True)
    rendered = renderer._render_item(item)
    assert rendered.startswith("ContainerQueue_Ext(")
    assert "ContainerQueue_Ext_Ext" not in rendered


def test_render_item_tech_postgres_gives_containerdb() -> None:
    renderer = _renderer()
    item = _item(item_type="container", alias="C_db", label="Database", technology="PostgreSQL")
    rendered = renderer._render_item(item)
    assert rendered == 'ContainerDb(C_db, "Database", "PostgreSQL")'


def test_render_item_tech_kafka_gives_containerqueue() -> None:
    renderer = _renderer()
    item = _item(item_type="container", alias="C_mq", label="Events", technology="Kafka")
    rendered = renderer._render_item(item)
    assert rendered == 'ContainerQueue(C_mq, "Events", "Kafka")'


def test_render_item_unknown_tech_gives_container() -> None:
    renderer = _renderer()
    item = _item(item_type="container", alias="C_ws", label="Worker", technology="Go")
    rendered = renderer._render_item(item)
    assert rendered == 'Container(C_ws, "Worker", "Go")'


def test_render_item_person_internal() -> None:
    renderer = _renderer()
    item = _item(item_type="person", alias="P_u1", label="Alice")
    assert renderer._render_item(item) == 'Person(P_u1, "Alice")'


def test_render_item_person_external() -> None:
    renderer = _renderer()
    item = _item(item_type="person", alias="P_ext", label="Partner", external=True)
    assert renderer._render_item(item) == 'Person_Ext(P_ext, "Partner")'


def test_render_item_system_internal() -> None:
    renderer = _renderer()
    item = _item(item_type="software-system", alias="SS_sys", label="My System")
    assert renderer._render_item(item) == 'System(SS_sys, "My System")'


def test_render_item_system_external() -> None:
    renderer = _renderer()
    item = _item(item_type="software-system", alias="SS_ext", label="Third Party", external=True)
    assert renderer._render_item(item) == 'System_Ext(SS_ext, "Third Party")'


def test_render_item_with_description_when_enabled() -> None:
    renderer = _renderer()
    item = _ResolvedItem(
        local_id="c1", item_type="container", alias="C_api", label="API",
        description="Handles requests", technology="FastAPI", external=False,
    )
    rendered = renderer._render_item(item, show_descriptions=True)
    assert "Handles requests" in rendered
    assert "FastAPI" in rendered


# ── Full render_body stdlib include test ──────────────────────────────────────

def test_render_body_includes_c4_component_stdlib() -> None:
    """Every render must include the C4-PlantUML stdlib so macros resolve."""
    diagram_entities = {
        "software-system": [{"id": "s1", "label": "System", "scope": True}],
        "container": [{"id": "c1", "label": "API", "technology": "FastAPI"}],
    }
    puml = _render_standalone(diagram_entities)
    assert "!include <C4/C4_Component>" in puml


def test_render_body_db_tech_uses_containerdb_shape() -> None:
    diagram_entities = {
        "software-system": [{"id": "s1", "label": "System", "scope": True}],
        "container": [{"id": "db1", "label": "DB", "technology": "PostgreSQL"}],
    }
    puml = _render_standalone(diagram_entities)
    assert 'ContainerDb(C_db1_0, "DB", "PostgreSQL")' in puml


def test_render_body_queue_tech_uses_containerqueue_shape() -> None:
    diagram_entities = {
        "software-system": [{"id": "s1", "label": "System", "scope": True}],
        "container": [{"id": "mq1", "label": "Queue", "technology": "Kafka"}],
    }
    puml = _render_standalone(diagram_entities)
    assert 'ContainerQueue(C_mq1_0, "Queue", "Kafka")' in puml


def test_render_body_explicit_shape_attribute() -> None:
    """A diagram entity with shape= uses that macro; ContainerDb not used despite Postgres tech."""
    diagram_entities = {
        "software-system": [{"id": "s1", "label": "System", "scope": True}],
        "container": [
            {"id": "c1", "label": "Storage",
             "technology": "PostgreSQL",  # would infer ContainerDb without explicit shape
             "shape": "Container"},        # explicit → Container macro, tech still in args
        ],
    }
    puml = _render_standalone(diagram_entities)
    # Uses Container (not ContainerDb) because shape is explicit; tech still appears in args
    assert "Container(" in puml
    assert "ContainerDb" not in puml
    assert "PostgreSQL" in puml


def test_render_body_boundary_uses_system_boundary() -> None:
    """Scope in boundary mode uses System_Boundary, not rectangle."""
    diagram_entities = {
        "software-system": [{"id": "s1", "label": "My System", "scope": True}],
        "container": [{"id": "c1", "label": "Service", "technology": "Python"}],
    }
    puml = _render_standalone(diagram_entities)
    assert 'System_Boundary(SS_s1_0, "My System") {' in puml
    assert "<<C4System>>" not in puml
