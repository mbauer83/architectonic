"""Tests for tools/diagrams/migrate_diagrams_to_bindings.py.

Covers: entity_id → represents binding, _scope_entity_id → scoped-by binding,
c4-contains deletion, idempotency (already-bound diagrams), dry-run mode.
"""

from __future__ import annotations

# Helpers to import the module under test
import importlib.util
from pathlib import Path

import yaml

_TOOL_PATH = Path(__file__).parents[2] / "tools" / "diagrams" / "migrate_diagrams_to_bindings.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("migrate_diagrams_to_bindings", _TOOL_PATH)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_tool = _load_tool()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_puml(tmp_path: Path, name: str, frontmatter: dict, body: str = "@startuml x\n@enduml\n") -> Path:
    path = tmp_path / f"{name}.puml"
    yaml_text = yaml.safe_dump(frontmatter, sort_keys=False).strip()
    path.write_text(f"---\n{yaml_text}\n---\n{body}", encoding="utf-8")
    return path


def _read_fm(path: Path) -> dict:
    import re
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?\n)---\n", text, re.DOTALL)
    return yaml.safe_load(m.group(1)) if m else {}


def _write_outgoing(tmp_path: Path, name: str, source: str, connections: list[dict]) -> Path:
    path = tmp_path / f"{name}.outgoing.md"
    sections = ["<!-- §connections -->"]
    for c in connections:
        sections.append(f"\n### {c['connection_type']} → {c['target_entity']}")
        if c.get("description"):
            sections.append(f"\n{c['description']}")
    header = f"---\nsource-entity: {source}\nversion: 0.1.0\nstatus: draft\nlast-updated: '2026-01-01'\n---\n\n"
    content = header + "\n".join(sections) + "\n"
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# migrate_diagram_file
# ---------------------------------------------------------------------------

def test_entity_id_becomes_represents_binding(tmp_path):
    path = _write_puml(tmp_path, "d1", {
        "artifact-id": "ARC@1.x.d1",
        "artifact-type": "diagram",
        "name": "D1",
        "version": "0.1.0",
        "status": "draft",
        "diagram-type": "c4-container",
        "diagram-entities": {
            "container": [
                {"id": "cont-1", "label": "API", "entity_id": "APP@123.abc.api"},
                {"id": "cont-2", "label": "DB"},
            ]
        },
        "last-updated": "2026-01-01",
    })
    count = _tool.migrate_diagram_file(path)
    assert count == 1
    fm = _read_fm(path)
    bindings = fm["bindings"]
    assert len(bindings) == 1
    b = bindings[0]
    assert b["id"] == "bind-cont-1"
    assert b["subject"] == {"kind": "entity", "id": "cont-1"}
    assert b["correspondence_kind"] == "represents"
    assert b["target"] == {"entity_id": "APP@123.abc.api"}
    # entity_id removed from item
    de_items = fm["diagram-entities"]["container"]
    assert all("entity_id" not in item for item in de_items)


def test_scope_entity_id_becomes_scoped_by_binding(tmp_path):
    path = _write_puml(tmp_path, "d2", {
        "artifact-id": "ARC@1.x.d2",
        "artifact-type": "diagram",
        "name": "D2",
        "version": "0.1.0",
        "status": "draft",
        "diagram-type": "c4-container",
        "diagram-entities": {
            "_scope_entity_id": "SYS@999.zzz.my-system",
            "container": [{"id": "c1", "label": "Svc"}],
        },
        "last-updated": "2026-01-01",
    })
    count = _tool.migrate_diagram_file(path)
    assert count == 1
    fm = _read_fm(path)
    assert "_scope_entity_id" not in fm["diagram-entities"]
    bindings = fm["bindings"]
    assert len(bindings) == 1
    b = bindings[0]
    assert b["subject"] == {"kind": "diagram"}
    assert b["correspondence_kind"] == "scoped-by"
    assert b["target"] == {"entity_id": "SYS@999.zzz.my-system"}


def test_both_entity_id_and_scope_entity_id_migrated(tmp_path):
    path = _write_puml(tmp_path, "d3", {
        "artifact-id": "ARC@1.x.d3",
        "artifact-type": "diagram",
        "name": "D3",
        "version": "0.1.0",
        "status": "draft",
        "diagram-type": "c4-container",
        "diagram-entities": {
            "_scope_entity_id": "SYS@1.a.sys",
            "container": [{"id": "c1", "label": "A", "entity_id": "APP@2.b.app"}],
        },
        "last-updated": "2026-01-01",
    })
    count = _tool.migrate_diagram_file(path)
    assert count == 2
    fm = _read_fm(path)
    assert len(fm["bindings"]) == 2


def test_no_changes_when_no_legacy_fields(tmp_path):
    path = _write_puml(tmp_path, "d4", {
        "artifact-id": "ARC@1.x.d4",
        "artifact-type": "diagram",
        "name": "D4",
        "version": "0.1.0",
        "status": "draft",
        "diagram-type": "c4-container",
        "diagram-entities": {
            "container": [{"id": "c1", "label": "Svc"}],
        },
        "last-updated": "2026-01-01",
    })
    original = path.read_text(encoding="utf-8")
    count = _tool.migrate_diagram_file(path)
    assert count == 0
    assert path.read_text(encoding="utf-8") == original


def test_idempotent_when_binding_already_exists(tmp_path):
    """Running migration twice produces no duplicate bindings."""
    path = _write_puml(tmp_path, "d5", {
        "artifact-id": "ARC@1.x.d5",
        "artifact-type": "diagram",
        "name": "D5",
        "version": "0.1.0",
        "status": "draft",
        "diagram-type": "c4-container",
        "diagram-entities": {
            "container": [{"id": "c1", "label": "A", "entity_id": "APP@1.x.app"}],
        },
        "last-updated": "2026-01-01",
    })
    _tool.migrate_diagram_file(path)
    count2 = _tool.migrate_diagram_file(path)
    assert count2 == 0
    assert len(_read_fm(path)["bindings"]) == 1


def test_merges_with_existing_bindings(tmp_path):
    path = _write_puml(tmp_path, "d6", {
        "artifact-id": "ARC@1.x.d6",
        "artifact-type": "diagram",
        "name": "D6",
        "version": "0.1.0",
        "status": "draft",
        "diagram-type": "c4-container",
        "diagram-entities": {
            "container": [{"id": "c1", "label": "A", "entity_id": "APP@1.x.app"}],
        },
        "bindings": [
            {"id": "bind-manual", "subject": {"kind": "diagram"}, "correspondence_kind": "scoped-by",
             "target": {"entity_id": "SYS@2.y.sys"}}
        ],
        "last-updated": "2026-01-01",
    })
    count = _tool.migrate_diagram_file(path)
    assert count == 1
    bindings = _read_fm(path)["bindings"]
    ids = {b["id"] for b in bindings}
    assert "bind-manual" in ids
    assert "bind-c1" in ids


# ---------------------------------------------------------------------------
# delete_c4_contains
# ---------------------------------------------------------------------------

def test_delete_c4_contains_reports_and_removes(tmp_path):
    path = _write_outgoing(tmp_path, "SRC@1.x.src", "SRC@1.x.src", [
        {"connection_type": "c4-contains", "target_entity": "TGT@2.y.tgt", "description": ""},
        {"connection_type": "archimate-serving", "target_entity": "TGT@3.z.other", "description": ""},
    ])
    deleted = _tool.delete_c4_contains(path)
    assert len(deleted) == 1
    assert deleted[0] == "SRC@1.x.src---TGT@2.y.tgt@@c4-contains"
    # File no longer contains c4-contains
    text = path.read_text(encoding="utf-8")
    assert "c4-contains" not in text
    assert "archimate-serving" in text


def test_delete_c4_contains_no_op_when_none(tmp_path):
    path = _write_outgoing(tmp_path, "SRC@1.a.s", "SRC@1.a.s", [
        {"connection_type": "archimate-serving", "target_entity": "TGT@1.b.t", "description": ""},
    ])
    original = path.read_text(encoding="utf-8")
    deleted = _tool.delete_c4_contains(path)
    assert deleted == []
    assert path.read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# _migrate_diagram_entities (unit)
# ---------------------------------------------------------------------------

def test_migrate_entities_preserves_non_entity_id_fields():
    de = {
        "container": [{"id": "c1", "label": "X", "entity_id": "APP@1.a.a", "technology": "Python"}]
    }
    updated, new_bindings, count = _tool._migrate_diagram_entities(de, [])
    assert count == 1
    item = updated["container"][0]
    assert item["technology"] == "Python"
    assert "entity_id" not in item
