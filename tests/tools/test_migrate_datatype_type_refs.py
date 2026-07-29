"""WU-6.1: conservative migration of datatype attribute type references."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

_TOOL_PATH = Path(__file__).parents[2] / "tools" / "datatypes" / "migrate_datatype_type_refs.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("migrate_datatype_type_refs", _TOOL_PATH)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[spec.name] = module  # type: ignore[union-attr]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_tool = _load_tool()


class _Allocator:
    def __init__(self) -> None:
        self._next = 0

    def allocate(self, *, prefix: str, name_hint: str | None) -> str:
        self._next += 1
        slug = (name_hint or "classifier").lower().replace(" ", "-")
        return f"{prefix}@1.id{self._next}.{slug}"


def _repo(tmp_path: Path, name: str, *, enterprise: bool = False) -> Path:
    root = (
        tmp_path / "enterprise-repository"
        if enterprise
        else tmp_path / "engagements" / name / "architecture-repository"
    )
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _diagram(root: Path, diagram_id: str, classifiers: list[dict], connections: list[dict] | None = None) -> Path:
    frontmatter = {
        "artifact-id": diagram_id,
        "artifact-type": "diagram",
        "name": diagram_id,
        "version": "0.1.0",
        "status": "draft",
        "diagram-type": "datatype",
        "diagram-entities": {"classifier": classifiers},
        "connections": connections or [],
        "last-updated": "2026-06-20",
    }
    text = str(yaml.safe_dump(frontmatter, sort_keys=False)).strip()
    path = root / "diagram-catalog" / "diagrams" / f"{diagram_id}.puml"
    path.write_text(f"---\n{text}\n---\n@startuml x\n@enduml\n", encoding="utf-8")
    return path


def _attribute(report: dict) -> dict:
    return report["attributes"][0]


def test_unique_classifier_match_is_convertible(tmp_path: Path) -> None:
    root = _repo(tmp_path, "ENG-A")
    _diagram(root, "DT-A", [
        {"id": "order", "label": "Order", "attributes": [{"name": "customer", "type": "Customer"}]},
        {"id": "customer", "label": "Customer"},
    ])

    plan = _tool.plan_migration([root], allocator=_Allocator())

    decision = _attribute(plan.report)
    assert decision["status"] == "convertible"
    assert decision["proposed_type"]["kind"] == "classifier"
    assert decision["proposed_type"]["id"].startswith("CLF@")


def test_primitive_shadow_is_ambiguous(tmp_path: Path) -> None:
    root = _repo(tmp_path, "ENG-A")
    _diagram(root, "DT-A", [
        {"id": "owner", "label": "Owner", "attributes": [{"name": "value", "type": "String"}]},
        {"id": "custom-string", "label": "String"},
    ])

    decision = _attribute(_tool.plan_migration([root], allocator=_Allocator()).report)

    assert decision["status"] == "ambiguous"
    assert decision["reason"] == "primitive-shadow"


def test_multiple_visible_matches_are_ambiguous(tmp_path: Path) -> None:
    root = _repo(tmp_path, "ENG-A")
    _diagram(root, "DT-A", [
        {"id": "owner", "label": "Owner", "attributes": [{"name": "target", "type": "Thing"}]},
        {"id": "thing-a", "label": "Thing"},
        {"id": "thing-b", "label": "Thing"},
    ])

    decision = _attribute(_tool.plan_migration([root], allocator=_Allocator()).report)

    assert decision["reason"] == "multi-match"
    assert len(decision["candidates"]) == 2


def test_classifier_in_another_engagement_is_out_of_scope(tmp_path: Path) -> None:
    first = _repo(tmp_path, "ENG-A")
    second = _repo(tmp_path, "ENG-B")
    _diagram(first, "DT-A", [
        {"id": "owner", "label": "Owner", "attributes": [{"name": "target", "type": "Remote"}]},
    ])
    _diagram(second, "DT-B", [{"id": "remote", "label": "Remote"}])

    decision = _attribute(_tool.plan_migration([first, second], allocator=_Allocator()).report)

    assert decision["reason"] == "out-of-scope"


def test_explicit_selector_mapping_resolves_ambiguity(tmp_path: Path) -> None:
    root = _repo(tmp_path, "ENG-A")
    _diagram(root, "DT-A", [
        {"id": "owner", "label": "Owner", "attributes": [{"name": "target", "type": "Thing"}]},
        {"id": "thing-a", "label": "Thing"},
        {"id": "thing-b", "label": "Thing"},
    ])
    mappings = {
        "DT-A:owner:target": {"kind": "classifier", "selector": "DT-A:thing-b"},
    }

    decision = _attribute(
        _tool.plan_migration([root], allocator=_Allocator(), mappings=mappings).report
    )

    assert decision["status"] == "convertible"
    assert decision["proposed_type"]["id"] == "CLF@1.id3.thing"


def test_apply_is_blocked_before_staging_when_unresolved(tmp_path: Path) -> None:
    root = _repo(tmp_path, "ENG-A")
    path = _diagram(root, "DT-A", [
        {"id": "owner", "label": "Owner", "attributes": [{"name": "target", "type": "Missing"}]},
    ])
    original = path.read_text(encoding="utf-8")
    plan = _tool.plan_migration([root], allocator=_Allocator())

    with pytest.raises(_tool.MigrationBlockedError):
        _tool.apply_migration(plan, verify=lambda _roots: [])

    assert path.read_text(encoding="utf-8") == original


def test_staged_verification_failure_does_not_publish(tmp_path: Path) -> None:
    root = _repo(tmp_path, "ENG-A")
    path = _diagram(root, "DT-A", [
        {"id": "owner", "label": "Owner", "attributes": [{"name": "name", "type": "String"}]},
    ])
    original = path.read_text(encoding="utf-8")
    plan = _tool.plan_migration([root], allocator=_Allocator())

    with pytest.raises(_tool.MigrationBlockedError, match="Staged verification failed"):
        _tool.apply_migration(plan, verify=lambda _roots: ["E999: rejected"])

    assert path.read_text(encoding="utf-8") == original


def test_apply_rewrites_all_references_stamps_version_and_verifies(tmp_path: Path) -> None:
    root = _repo(tmp_path, "ENG-A")
    path = _diagram(root, "DT-A", [
        {
            "id": "order",
            "label": "Order",
            "attributes": [
                {"name": "name", "type": "String"},
                {"name": "customer", "type": "Customer"},
            ],
        },
        {"id": "customer", "label": "Customer"},
    ], connections=[{
        "id": "edge-1",
        "conn_type": "dt-association",
        "source": "order",
        "target": "customer",
    }])
    plan = _tool.plan_migration([root], allocator=_Allocator())
    verified: list[dict[Path, Path]] = []

    changed = _tool.apply_migration(
        plan,
        verify=lambda roots: verified.append(dict(roots)) or [],
    )

    assert changed == (path,)
    assert verified
    frontmatter, _body = _tool._parse(path)
    assert frontmatter["diagram-format-version"] == 2
    classifiers = frontmatter["diagram-entities"]["classifier"]
    assert all(item["id"].startswith("CLF@") for item in classifiers)
    assert classifiers[0]["attributes"][0]["type"] == {"kind": "primitive", "name": "String"}
    assert classifiers[0]["attributes"][1]["type"]["kind"] == "classifier"
    assert frontmatter["connections"][0]["source"] == classifiers[0]["id"]
    assert frontmatter["connections"][0]["target"] == classifiers[1]["id"]
