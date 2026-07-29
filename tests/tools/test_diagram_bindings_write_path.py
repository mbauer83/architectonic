"""Write-path integration tests for diagram bindings (task 5 — §1.3).

Covers:
- format_diagram_puml emits bindings in frontmatter
- create_diagram normalizes binding: shorthand, entity_id shorthand, _scope_entity_id
  and strips them from persisted diagram-entities
- edit_diagram merges existing + new bindings, normalizes shorthand, persists
- parse_diagram_file surfaces typed bindings
- strip_diagram_shorthand and extend normalize_bindings for legacy forms
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from src.application.modeling.artifact_write_formatting import format_diagram_puml
from src.application.modeling.binding_normalize import normalize_bindings, strip_diagram_shorthand
from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.diagram import create_diagram
from src.infrastructure.write.artifact_write.diagram_edit import edit_diagram
from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs  # noqa: PLC0415

    return build_runtime_catalogs(build_module_registry())


def _noop_caches(path: Path) -> None:  # noqa: ARG001
    pass


def _verifier(repo_root: Path) -> ArtifactVerifier:
    return ArtifactVerifier(
        ArtifactRegistry(shared_artifact_index(repo_root)),
        check_puml_syntax=False,
        catalogs=_catalogs(),
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _entity(artifact_id: str, artifact_type: str = "requirement", name: str = "E") -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: {artifact_type}
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
---

<!-- §content -->

## {name}

<!-- §display -->

### archimate

```yaml
domain: Motivation
```
"""


def _diagram_path(repo_root: Path, artifact_id: str) -> Path:
    return repo_root / "diagram-catalog" / "diagrams" / f"{artifact_id}.puml"


def _read_fm(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    import re
    m = re.match(r"^---\n(.*?\n)---\n", text, re.DOTALL)
    return yaml.safe_load(m.group(1)) if m else {}


# ---------------------------------------------------------------------------
# format_diagram_puml
# ---------------------------------------------------------------------------


def test_format_diagram_puml_emits_bindings():
    bindings = [
        {
            "id": "bind-c1",
            "subject": {"kind": "entity", "id": "c1"},
            "correspondence_kind": "represents",
            "target": {"entity_id": "APP@1.a.app"},
        }
    ]
    result = format_diagram_puml(
        artifact_id="ARC@1.x.d",
        diagram_type="archimate-motivation",
        name="Test",
        version="0.1.0",
        status="draft",
        last_updated="2026-01-01",
        puml_body="@startuml d\n@enduml\n",
        bindings=bindings,
    )
    fm = yaml.safe_load(result.split("---\n")[1])
    assert "bindings" in fm
    assert fm["bindings"][0]["id"] == "bind-c1"


def test_format_diagram_puml_omits_bindings_when_empty():
    result = format_diagram_puml(
        artifact_id="ARC@1.x.d",
        diagram_type="archimate-motivation",
        name="Test",
        version="0.1.0",
        status="draft",
        last_updated="2026-01-01",
        puml_body="@startuml d\n@enduml\n",
        bindings=None,
    )
    fm = yaml.safe_load(result.split("---\n")[1])
    assert "bindings" not in fm


def test_format_bindings_key_before_last_updated():
    bindings = [{"id": "b1", "subject": {"kind": "diagram"}, "correspondence_kind": "scoped-by",
                 "target": {"entity_id": "SYS@1.s.s"}}]
    result = format_diagram_puml(
        artifact_id="ARC@1.x.d",
        diagram_type="archimate-motivation",
        name="T",
        version="0.1.0",
        status="draft",
        last_updated="2026-01-01",
        puml_body="@startuml d\n@enduml\n",
        bindings=bindings,
    )
    keys = list(yaml.safe_load(result.split("---\n")[1]).keys())
    assert keys.index("bindings") < keys.index("last-updated")


# ---------------------------------------------------------------------------
# strip_diagram_shorthand
# ---------------------------------------------------------------------------


def test_strip_removes_entity_id_from_items():
    de = {"container": [{"id": "c1", "label": "X", "entity_id": "APP@1.a.app"}]}
    out = strip_diagram_shorthand(de)
    assert out is not None
    assert "entity_id" not in out["container"][0]  # type: ignore[index]
    assert out["container"][0]["label"] == "X"  # type: ignore[index]


def test_strip_removes_backing_entity_id_from_items():
    de = {"occurrence": [{"id": "repo-left", "backing_entity_id": "BOB@1.a.repo"}]}
    out = strip_diagram_shorthand(de)
    assert out is not None
    assert "backing_entity_id" not in out["occurrence"][0]  # type: ignore[index]


def test_strip_removes_binding_from_items():
    de = {"container": [{"id": "c1", "label": "X", "binding": {"target": {"entity_id": "APP@1.a.a"}}}]}
    out = strip_diagram_shorthand(de)
    assert out is not None
    assert "binding" not in out["container"][0]  # type: ignore[index]


def test_strip_removes_scope_key():
    de = {"_scope_entity_id": "SYS@1.s.s", "container": [{"id": "c1", "label": "X"}]}
    out = strip_diagram_shorthand(de)
    assert out is not None
    assert "_scope_entity_id" not in out


def test_strip_passes_through_none():
    assert strip_diagram_shorthand(None) is None


# ---------------------------------------------------------------------------
# normalize_bindings extended forms
# ---------------------------------------------------------------------------


def test_normalize_entity_id_shorthand():
    de = {"container": [{"id": "c1", "label": "App", "entity_id": "APP@1.a.app"}]}
    bindings = normalize_bindings(de, None)
    assert len(bindings) == 1
    b = bindings[0]
    assert b.id == "bind-c1"
    assert b.correspondence_kind == "represents"
    assert b.target.entity_id == "APP@1.a.app"


def test_normalize_scope_entity_id():
    de = {"_scope_entity_id": "SYS@1.s.sys", "container": [{"id": "c1", "label": "X"}]}
    bindings = normalize_bindings(de, None)
    assert len(bindings) == 1
    b = bindings[0]
    assert b.id == "bind-scope"
    assert b.subject.kind == "diagram"
    assert b.correspondence_kind == "scoped-by"
    assert b.target.entity_id == "SYS@1.s.sys"


def test_normalize_binding_shorthand_takes_precedence_over_entity_id():
    """When item has both binding: and entity_id, binding: wins (entity_id shorthand skipped)."""
    de = {
        "container": [
            {
                "id": "c1",
                "label": "X",
                "binding": {"correspondence_kind": "refines", "target": {"entity_id": "APP@1.a.app"}},
                "entity_id": "APP@2.b.other",
            }
        ]
    }
    bindings = normalize_bindings(de, None)
    assert len(bindings) == 1
    assert bindings[0].correspondence_kind == "refines"


def test_normalize_entity_id_skipped_without_item_id():
    de = {"container": [{"label": "No ID", "entity_id": "APP@1.a.app"}]}
    # Should silently skip — no error for legacy entity_id (unlike binding: which errors)
    bindings = normalize_bindings(de, None)
    assert bindings == []


def test_normalize_backing_entity_id_with_visual_role():
    de = {
        "occurrence": [
            {
                "id": "repo-left",
                "backing_entity_id": "BOB@1.a.repo",
                "visual_role": "left-context",
            }
        ]
    }
    bindings = normalize_bindings(de, None)
    assert len(bindings) == 1
    assert bindings[0].target.entity_id == "BOB@1.a.repo"
    assert bindings[0].visual_role == "left-context"


# ---------------------------------------------------------------------------
# create_diagram write path
# ---------------------------------------------------------------------------


def test_create_diagram_normalizes_binding_shorthand(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "diagram-catalog" / "diagrams").mkdir(parents=True)

    de = {
        "container": [
            {
                "id": "c1",
                "label": "API",
                "binding": {"correspondence_kind": "represents", "target": {"entity_id": "APP@1.a.api"}},
            }
        ]
    }
    result = create_diagram(
        repo_root=repo_root,
        verifier=_verifier(repo_root),
        clear_repo_caches=_noop_caches,
        diagram_type="activity",
        name="My Diagram",
        puml="",
        artifact_id="ARC@1.x.my-diagram",
        diagram_entities=de,
        version="0.1.0",
        status="draft",
        last_updated="2026-01-01",
        dry_run=True,
    )
    content = result.content
    assert content is not None
    fm = yaml.safe_load(content.split("---\n")[1])
    assert "bindings" in fm
    assert fm["bindings"][0]["id"] == "bind-c1"
    # entity_id stripped from persisted diagram-entities
    items = fm.get("diagram-entities", {}).get("container", [])
    assert all("binding" not in item for item in items)


def test_create_diagram_normalizes_entity_id_shorthand(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "diagram-catalog" / "diagrams").mkdir(parents=True)

    de = {"container": [{"id": "c1", "label": "API", "entity_id": "APP@1.a.api"}]}
    result = create_diagram(
        repo_root=repo_root,
        verifier=_verifier(repo_root),
        clear_repo_caches=_noop_caches,
        diagram_type="activity",
        name="My Diagram",
        puml="",
        artifact_id="ARC@1.x.my-diagram",
        diagram_entities=de,
        version="0.1.0",
        status="draft",
        last_updated="2026-01-01",
        dry_run=True,
    )
    content = result.content
    assert content is not None
    fm = yaml.safe_load(content.split("---\n")[1])
    assert "bindings" in fm
    assert fm["bindings"][0]["correspondence_kind"] == "represents"
    items = fm.get("diagram-entities", {}).get("container", [])
    assert all("entity_id" not in item for item in items)


def test_create_diagram_normalizes_backing_entity_occurrence(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "diagram-catalog" / "diagrams").mkdir(parents=True)

    de = {
        "occurrence": [
            {
                "id": "repo-left",
                "backing_entity_id": "BOB@1.a.repo",
                "visual_role": "left-context",
            }
        ]
    }
    result = create_diagram(
        repo_root=repo_root,
        verifier=_verifier(repo_root),
        clear_repo_caches=_noop_caches,
        diagram_type="archimate-business",
        name="Occurrences",
        puml="@startuml Occurrences\n@enduml",
        artifact_id="ARC@1.x.occurrences",
        diagram_entities=de,
        version="0.1.0",
        status="draft",
        last_updated="2026-01-01",
        dry_run=True,
    )
    content = result.content
    assert content is not None
    fm = yaml.safe_load(content.split("---\n")[1])
    binding = fm["bindings"][0]
    assert binding["subject"] == {"kind": "entity", "id": "repo-left"}
    assert binding["target"] == {"entity_id": "BOB@1.a.repo"}
    assert binding["visual_role"] == "left-context"
    items = fm.get("diagram-entities", {}).get("occurrence", [])
    assert all("backing_entity_id" not in item for item in items)


def test_create_diagram_explicit_bindings_persisted(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "diagram-catalog" / "diagrams").mkdir(parents=True)

    explicit = [
        {
            "id": "bind-scope",
            "subject": {"kind": "diagram"},
            "correspondence_kind": "scoped-by",
            "target": {"entity_id": "SYS@1.s.sys"},
        }
    ]
    result = create_diagram(
        repo_root=repo_root,
        verifier=_verifier(repo_root),
        clear_repo_caches=_noop_caches,
        diagram_type="activity",
        name="Scoped",
        puml="@startuml Scoped\n@enduml",
        artifact_id="ARC@1.x.scoped",
        bindings=explicit,
        version="0.1.0",
        status="draft",
        last_updated="2026-01-01",
        dry_run=True,
    )
    content = result.content
    assert content is not None
    fm = yaml.safe_load(content.split("---\n")[1])
    assert any(b["id"] == "bind-scope" for b in fm.get("bindings", []))


# ---------------------------------------------------------------------------
# parse_diagram_file surfaces bindings
# ---------------------------------------------------------------------------


def test_parse_diagram_file_surfaces_bindings(tmp_path):
    path = tmp_path / "d.puml"
    content = """\
---
artifact-id: ARC@1.x.d
artifact-type: diagram
name: D
version: 0.1.0
status: draft
diagram-type: archimate-motivation
bindings:
- id: bind-c1
  subject:
    kind: entity
    id: c1
  correspondence_kind: represents
  target:
    entity_id: APP@1.a.app
last-updated: '2026-01-01'
---
@startuml d
@enduml
"""
    path.write_text(content, encoding="utf-8")
    parsed = parse_diagram_file(path)
    assert len(parsed.bindings) == 1
    assert parsed.bindings[0].id == "bind-c1"
    assert parsed.bindings[0].target.entity_id == "APP@1.a.app"


def test_parse_diagram_file_empty_bindings(tmp_path):
    path = tmp_path / "d.puml"
    content = """\
---
artifact-id: ARC@1.x.d
artifact-type: diagram
name: D
version: 0.1.0
status: draft
diagram-type: archimate-motivation
last-updated: '2026-01-01'
---
@startuml d
@enduml
"""
    path.write_text(content, encoding="utf-8")
    parsed = parse_diagram_file(path)
    assert parsed.bindings == []


# ---------------------------------------------------------------------------
# edit_diagram merges bindings
# ---------------------------------------------------------------------------


def _minimal_diagram(artifact_id: str, bindings: list | None = None) -> str:
    fm: dict = {
        "artifact-id": artifact_id,
        "artifact-type": "diagram",
        "name": "D",
        "version": "0.1.0",
        "status": "draft",
        "diagram-type": "archimate-motivation",
        "last-updated": "2026-01-01",
    }
    if bindings:
        fm["bindings"] = bindings
    yaml_text = yaml.safe_dump(fm, sort_keys=False).strip()
    return f"---\n{yaml_text}\n---\n@startuml {artifact_id}\n@enduml\n"


def test_edit_diagram_merges_existing_and_new_bindings(tmp_path):
    repo_root = tmp_path / "repo"
    diagrams_dir = repo_root / "diagram-catalog" / "diagrams"
    diagrams_dir.mkdir(parents=True)
    aid = "ARC@1.x.d"
    existing_bindings = [
        {"id": "bind-old", "subject": {"kind": "diagram"}, "correspondence_kind": "scoped-by",
         "target": {"entity_id": "SYS@1.s.s"}}
    ]
    (diagrams_dir / f"{aid}.puml").write_text(
        _minimal_diagram(aid, existing_bindings), encoding="utf-8"
    )
    new_binding = [
        {"id": "bind-new", "subject": {"kind": "entity", "id": "c1"}, "correspondence_kind": "represents",
         "target": {"entity_id": "APP@1.a.app"}}
    ]
    result = edit_diagram(
        repo_root=repo_root,
        verifier=_verifier(repo_root),
        clear_repo_caches=_noop_caches,
        artifact_id=aid,
        bindings=new_binding,
        dry_run=True,
    )
    content = result.content
    assert content is not None
    fm = yaml.safe_load(content.split("---\n")[1])
    ids = {b["id"] for b in fm.get("bindings", [])}
    assert "bind-old" in ids
    assert "bind-new" in ids


def test_edit_diagram_normalizes_shorthand_in_new_entities(tmp_path):
    repo_root = tmp_path / "repo"
    diagrams_dir = repo_root / "diagram-catalog" / "diagrams"
    diagrams_dir.mkdir(parents=True)
    aid = "ARC@1.x.d2"
    (diagrams_dir / f"{aid}.puml").write_text(_minimal_diagram(aid), encoding="utf-8")

    de = {"container": [{"id": "c1", "label": "X", "entity_id": "APP@1.a.app"}]}
    result = edit_diagram(
        repo_root=repo_root,
        verifier=_verifier(repo_root),
        clear_repo_caches=_noop_caches,
        artifact_id=aid,
        diagram_entities=de,
        dry_run=True,
    )
    content = result.content
    assert content is not None
    fm = yaml.safe_load(content.split("---\n")[1])
    assert any(b["id"] == "bind-c1" for b in fm.get("bindings", []))
    items = fm.get("diagram-entities", {}).get("container", [])
    assert all("entity_id" not in item for item in items)
