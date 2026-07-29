from __future__ import annotations

from pathlib import Path

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.artifact_index import mutable_artifact_index
from src.infrastructure.artifact_index.coordination import (
    publish_authoritative_mutation,
    suppress_redundant_refresh_paths,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _entity_md(artifact_id: str, name: str, alias: str) -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: requirement
name: "{name}"
version: 0.1.0
status: active
last-updated: '2026-04-21'
---

<!-- §content -->

## {name}

Content.

## Properties

| Attribute | Value |
|---|---|
| (none) | (none) |

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Requirement
label: "{name}"
alias: {alias}
```
"""


def test_apply_file_changes_batches_generation_and_refresh_suppression(tmp_path: Path) -> None:
    root = tmp_path / "architecture-repository"
    entity_id = "REQ@1000000000.TestAA.sample"
    target_id = "REQ@1000000001.TestBB.target"
    diagram_id = "DIA@1000000002.TestCC.sample-diagram"

    entity_path = root / "model" / "motivation" / "requirement" / f"{entity_id}.md"
    target_path = root / "model" / "motivation" / "requirement" / f"{target_id}.md"
    outgoing_path = root / "model" / "motivation" / "requirement" / f"{entity_id}.outgoing.md"
    diagram_path = root / "diagram-catalog" / "diagrams" / f"{diagram_id}.puml"

    _write(entity_path, _entity_md(entity_id, "Sample", "REQ_TestAA"))
    _write(target_path, _entity_md(target_id, "Target", "REQ_TestBB"))
    _write(
        outgoing_path,
        f"""\
---
source-entity: {entity_id}
version: 0.1.0
status: active
last-updated: '2026-04-21'
---

<!-- §connections -->

### archimate-association → {target_id}
""",
    )
    _write(root / "diagram-catalog" / "_archimate-stereotypes.puml", "' ok\n")
    _write(
        diagram_path,
        f"""\
---
artifact-id: {diagram_id}
artifact-type: diagram
name: Sample Diagram
diagram-type: archimate-motivation
version: 0.1.0
status: draft
last-updated: '2026-04-21'
---
@startuml {diagram_id}
!include ../_archimate-stereotypes.puml
rectangle "A" <<Requirement>> as REQ_TestAA
rectangle "B" <<Requirement>> as REQ_TestBB
REQ_TestAA --> REQ_TestBB
@enduml
""",
    )

    index = mutable_artifact_index(root)
    repo = ArtifactRepository(index)
    before = repo.read_model_version()

    _write(entity_path, _entity_md(entity_id, "Sample Updated", "REQ_TestAA"))
    _write(
        outgoing_path,
        f"""\
---
source-entity: {entity_id}
version: 0.1.0
status: active
last-updated: '2026-04-21'
---

<!-- §connections -->

### archimate-association → {target_id}
### archimate-association → {entity_id}
""",
    )

    after = index.apply_file_changes([entity_path, outgoing_path])

    assert after.generation == before.generation + 1
    assert after.etag != before.etag

    context = repo.read_entity_context(entity_id)
    assert context is not None
    assert context["generation"] == after.generation
    assert context["etag"] == after.etag
    assert context["entity"]["name"] == "Sample Updated"

    publish_authoritative_mutation([root], changed_paths=[entity_path, outgoing_path], version=after)
    remaining = suppress_redundant_refresh_paths([root], [entity_path, outgoing_path, diagram_path])

    assert remaining == [diagram_path]
