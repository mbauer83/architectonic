"""Plan-time reference closure: a selection that would leave a promoted document's
schema-required link or a promoted diagram's binding dangling enterprise-side is
refused BEFORE any file is written, with the missing artifact named — the failure
that previously surfaced only as a post-copy rollback with an id-less E155."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.artifact_index import combined_artifact_index
from src.infrastructure.write.artifact_write.promote_execute import execute_promotion
from src.infrastructure.write.artifact_write.promote_to_enterprise import plan_promotion

_REQ = "REQ@1000000701.RfcReq.closure-requirement"
_REQ2 = "REQ@1000000702.RfcRq2.closure-second-requirement"
_PRN = "PRN@1000000703.RfcPrn.closure-principle"
_STD = "STD@1000000704.RfcStd.closure-standard"
_ARC = "ARC@1000000705.RfcArc.closure-diagram"
_APP = "APP@1000000706.RfcApp.closure-component"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _entity_md(artifact_id: str, artifact_type: str, name: str) -> str:
    prefix, rand = artifact_id.split("@")[0], artifact_id.split(".")[1]
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
label: "{name}"
alias: {prefix}_{rand}
```
"""


_STANDARD_SCHEMA = """\
{
  "abbreviation": "STD",
  "name": "Standard",
  "required_sections": ["Scope", "Specification"],
  "required_entity_type_connections": ["requirement"],
  "sections": [
    {"name": "Specification", "required_entity_type_connections": ["principle"]}
  ]
}
"""


def _doc_md(links_scope: list[str], links_specification: list[str]) -> str:
    def _link_lines(ids: list[str]) -> str:
        return "\n".join(
            f"See [{aid}](../../../model/motivation/requirement/{aid}.md)"
            if aid.startswith("REQ@")
            else f"See [{aid}](../../../model/motivation/principle/{aid}.md)"
            for aid in ids
        )

    return f"""\
---
artifact-id: {_STD}
artifact-type: document
doc-type: standard
title: Closure Standard
status: draft
version: 0.1.0
last-updated: '2026-01-01'
---

## Scope

{_link_lines(links_scope)}

## Specification

{_link_lines(links_specification)}
"""


def _diagram_puml(entity_ids: list[str], connection_ids: list[str]) -> str:
    entities = "\n".join(f"- {eid}" for eid in entity_ids)
    connections = "\n".join(f"- {cid}" for cid in connection_ids)
    return f"""\
---
artifact-id: {_ARC}
artifact-type: diagram
diagram-type: architecture
name: Closure Diagram
status: draft
version: 0.1.0
last-updated: '2026-01-01'
entity-ids-used:
{entities}
connection-ids-used:
{connections}
---
@startuml
title Closure Diagram
rectangle placeholder
@enduml
"""


@pytest.fixture()
def roots(tmp_path: Path) -> tuple[Path, Path]:
    eng = tmp_path / "engagements" / "ENG-RFC" / "architecture-repository"
    ent = tmp_path / "enterprise-repository"
    for root in (eng, ent):
        (root / "model").mkdir(parents=True, exist_ok=True)
        _write(root / ".arch-repo" / "documents" / "standard.json", _STANDARD_SCHEMA)
    _write(eng / "model/motivation/requirement" / f"{_REQ}.md", _entity_md(_REQ, "requirement", "Closure Req"))
    _write(eng / "model/motivation/requirement" / f"{_REQ2}.md", _entity_md(_REQ2, "requirement", "Second Req"))
    _write(eng / "model/motivation/principle" / f"{_PRN}.md", _entity_md(_PRN, "principle", "Closure Prn"))
    _write(
        eng / "model/application/application-component" / f"{_APP}.md",
        _entity_md(_APP, "application-component", "Closure App"),
    )
    return eng, ent


def _plan(eng: Path, ent: Path, **kwargs):
    index = combined_artifact_index(eng, ent)
    registry = ArtifactRegistry(index)
    repo = ArtifactRepository(index)
    return (
        plan_promotion(None, registry, repo, engagement_root=eng, enterprise_root=ent, **kwargs),
        registry,
    )


class TestDocumentClosure:
    def test_required_link_left_behind_blocks_and_names_the_artifact(self, roots) -> None:
        eng, ent = roots
        _write(eng / "docs/standard/closure" / f"{_STD}.md", _doc_md([_REQ], [_PRN]))
        plan, _ = _plan(eng, ent, document_ids=[_STD], entity_ids=[_PRN])

        deps = [d for d in plan.missing_dependencies if d.kind == "document_required_link"]
        assert [d.artifact_id for d in deps] == [_REQ]
        assert deps[0].required_by == _STD
        assert any(_REQ in e and _STD in e for e in plan.schema_errors)

    def test_execute_refuses_before_writing_anything(self, roots) -> None:
        eng, ent = roots
        _write(eng / "docs/standard/closure" / f"{_STD}.md", _doc_md([_REQ], [_PRN]))
        plan, registry = _plan(eng, ent, document_ids=[_STD], entity_ids=[_PRN])

        result = execute_promotion(plan, eng, ent, registry)
        assert result.executed is False
        assert result.rolled_back is False
        assert result.copied_files == []
        assert not (ent / "docs").exists()
        assert result.verification_errors  # the refusal carries the plan's errors

    def test_requirement_in_the_set_satisfies_the_closure(self, roots) -> None:
        eng, ent = roots
        _write(eng / "docs/standard/closure" / f"{_STD}.md", _doc_md([_REQ], [_PRN]))
        plan, _ = _plan(eng, ent, document_ids=[_STD], entity_ids=[_REQ, _PRN])
        assert plan.missing_dependencies == []
        assert plan.schema_errors == []

    def test_enterprise_resident_requirement_satisfies_the_closure(self, roots) -> None:
        eng, ent = roots
        _write(ent / "model/motivation/requirement" / f"{_REQ}.md", _entity_md(_REQ, "requirement", "Closure Req"))
        _write(eng / "docs/standard/closure" / f"{_STD}.md", _doc_md([_REQ], [_PRN]))
        plan, _ = _plan(eng, ent, document_ids=[_STD], entity_ids=[_PRN])
        assert plan.missing_dependencies == []

    def test_any_satisfying_link_suffices(self, roots) -> None:
        eng, ent = roots
        _write(eng / "docs/standard/closure" / f"{_STD}.md", _doc_md([_REQ, _REQ2], [_PRN]))
        plan, _ = _plan(eng, ent, document_ids=[_STD], entity_ids=[_REQ2, _PRN])
        assert [d for d in plan.missing_dependencies if d.kind == "document_required_link"] == []

    def test_section_level_requirement_is_checked_in_its_section(self, roots) -> None:
        eng, ent = roots
        # Principle linked in Scope only — the Specification section's requirement is unmet
        # by an engagement-only principle staying behind.
        _write(eng / "docs/standard/closure" / f"{_STD}.md", _doc_md([_REQ], [_PRN]))
        plan, _ = _plan(eng, ent, document_ids=[_STD], entity_ids=[_REQ])
        deps = [d for d in plan.missing_dependencies if d.artifact_id == _PRN]
        assert deps and deps[0].kind == "document_required_link"

    def test_absent_link_is_not_a_closure_finding(self, roots) -> None:
        eng, ent = roots
        # No requirement link at all: the engagement verifier owns that defect; closure
        # must not invent a dependency it cannot name.
        _write(eng / "docs/standard/closure" / f"{_STD}.md", _doc_md([], [_PRN]))
        plan, _ = _plan(eng, ent, document_ids=[_STD], entity_ids=[_PRN])
        assert [d for d in plan.missing_dependencies if d.kind == "document_required_link"] == []


class TestDiagramClosure:
    def test_bound_entity_left_behind_blocks_with_kind_diagram_entity(self, roots) -> None:
        eng, ent = roots
        _write(eng / "diagram-catalog/diagrams/closure" / f"{_ARC}.puml", _diagram_puml([_APP], []))
        plan, _ = _plan(eng, ent, diagram_ids=[_ARC])
        deps = [d for d in plan.missing_dependencies if d.kind == "diagram_entity"]
        assert [d.artifact_id for d in deps] == [_APP]
        assert deps[0].required_by == _ARC

    def test_bound_entity_in_set_passes(self, roots) -> None:
        eng, ent = roots
        _write(eng / "diagram-catalog/diagrams/closure" / f"{_ARC}.puml", _diagram_puml([_APP], []))
        plan, _ = _plan(eng, ent, diagram_ids=[_ARC], entity_ids=[_APP])
        assert plan.missing_dependencies == []

    def test_connection_endpoints_close_one_hop(self, roots) -> None:
        eng, ent = roots
        cid = f"{_APP}---{_REQ}@@archimate-realization"
        _write(eng / "diagram-catalog/diagrams/closure" / f"{_ARC}.puml", _diagram_puml([_APP], [cid]))
        plan, _ = _plan(eng, ent, diagram_ids=[_ARC], entity_ids=[_APP])
        missing_ids = {d.artifact_id for d in plan.missing_dependencies}
        assert _REQ in missing_ids
        kinds = {d.kind for d in plan.missing_dependencies if d.artifact_id == _REQ}
        assert "diagram_connection_endpoint" in kinds

    def test_connection_with_both_endpoints_in_set_passes(self, roots) -> None:
        eng, ent = roots
        cid = f"{_APP}---{_REQ}@@archimate-realization"
        _write(eng / "diagram-catalog/diagrams/closure" / f"{_ARC}.puml", _diagram_puml([_APP], [cid]))
        plan, _ = _plan(eng, ent, diagram_ids=[_ARC], entity_ids=[_APP, _REQ])
        assert plan.missing_dependencies == []


class TestCombinedArtifactTypesRoundTrip:
    def test_entity_document_and_diagram_promote_together(self, roots) -> None:
        """One run covering three artifact types whose closure depends on each other:
        the document requires the entity, the diagram binds it — a set containing all
        three plans clean and executes with every file landing enterprise-side."""
        eng, ent = roots
        _write(eng / "docs/standard/closure" / f"{_STD}.md", _doc_md([_REQ], [_PRN]))
        _write(eng / "diagram-catalog/diagrams/closure" / f"{_ARC}.puml", _diagram_puml([_REQ], []))
        plan, registry = _plan(
            eng, ent, document_ids=[_STD], diagram_ids=[_ARC], entity_ids=[_REQ, _PRN]
        )
        assert plan.schema_errors == []
        assert plan.missing_dependencies == []

        result = execute_promotion(plan, eng, ent, registry)
        assert result.executed is True, result.verification_errors
        assert (ent / "model/motivation/requirement" / f"{_REQ}.md").exists()
        assert (ent / "docs/standard/closure" / f"{_STD}.md").exists()
        assert (ent / "diagram-catalog/diagrams/closure" / f"{_ARC}.puml").exists()
