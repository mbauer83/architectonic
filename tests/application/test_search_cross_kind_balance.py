"""Cross-kind search visibility: minority kinds stay visible and diagrams are
discoverable by the names of the entities they contain or bind.

Regression for the navigation search where a flood of entity hits crowded diagrams
and documents out of the result window, and where diagrams were only findable by
their own title/type — never by a member entity's name.
"""

from __future__ import annotations

from pathlib import Path

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _entity_md(artifact_id: str, name: str, artifact_type: str = "application-component") -> str:
    slug = artifact_id.split(".")[-1].replace("-", "_")
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

Description.

## Properties

| Attribute | Value |
|---|---|
| (none) | (none) |

<!-- §display -->

### archimate

```yaml
domain: Application
element-type: ApplicationComponent
label: "{name}"
alias: A_{slug}
```
"""


def _document_md(artifact_id: str, title: str) -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: document
doc-type: standard
title: "{title}"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
---

# {title}

Body.
"""


def _matrix_md(artifact_id: str, name: str, from_ids: list[str], to_ids: list[str]) -> str:
    from_block = "\n".join(f"- {i}" for i in from_ids)
    to_block = "\n".join(f"- {i}" for i in to_ids)
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: diagram
diagram-type: matrix
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
from-entity-ids:
{from_block}
to-entity-ids:
{to_block}
---

Matrix body.
"""


def _balanced_repo(root: Path) -> Path:
    # 30 entities all matching "service".
    comp_dir = root / "model" / "application" / "application-component"
    for i in range(30):
        eid = f"APP@1000000060.ENT{i:03d}.service-component-{i}"
        _write(comp_dir / f"{eid}.md", _entity_md(eid, f"Service Component {i}"))
    doc_id = "STD@1000000060.SvcDoc.service-standards"
    _write(root / "docs" / "standard" / f"{doc_id}.md", _document_md(doc_id, "Service Standards"))
    diag_id = "DIAG@1000000060.SvcDia.service-landscape"
    _write(root / "diagram-catalog" / "diagrams" / f"{diag_id}.md", _matrix_md(diag_id, "Service Landscape", [], []))
    return root


def test_minority_kinds_not_crowded_out_by_entity_flood(tmp_path: Path) -> None:
    repo = ArtifactRepository(shared_artifact_index(_balanced_repo(tmp_path / "repo")))

    result = repo.search_artifacts("service", limit=12, include_connections=False)

    kinds = {h.record_type for h in result.hits}
    assert {"entity", "diagram", "document"} <= kinds, f"A kind was crowded out. Got: {kinds}"


def test_diagram_found_by_contained_entity_name(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    member_id = "APP@1000000061.Quag00.quagmire-subsystem"
    target_id = "OUT@1000000061.Outc00.consolidation-outcome"
    member_md = _entity_md(member_id, "Quagmire Subsystem")
    target_md = _entity_md(target_id, "Consolidation Outcome", "outcome")
    _write(root / "model" / "application" / "application-component" / f"{member_id}.md", member_md)
    _write(root / "model" / "motivation" / "outcome" / f"{target_id}.md", target_md)
    diag_id = "MAT@1000000061.Coup00.coupling-overview"
    _write(
        root / "diagram-catalog" / "diagrams" / f"{diag_id}.md",
        _matrix_md(diag_id, "Coupling Overview", [member_id], [target_id]),
    )
    repo = ArtifactRepository(shared_artifact_index([root]))

    # "quagmire" appears only in the member entity's name, not in the diagram's own title.
    result = repo.search_artifacts("quagmire", limit=20, include_connections=False)

    diagram_ids = [h.record.artifact_id for h in result.hits if h.record_type == "diagram"]
    all_ids = [h.record.artifact_id for h in result.hits]
    assert diag_id in diagram_ids, f"Diagram not found by member entity name. Hits: {all_ids}"
