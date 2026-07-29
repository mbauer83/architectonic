from __future__ import annotations

from pathlib import Path

from src.infrastructure.mcp.artifact_mcp.query_scaffold_tools import artifact_diagram_scaffold


def _write_entity(path: Path, *, artifact_id: str, artifact_type: str, name: str, alias: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""\
---
artifact-id: {artifact_id}
artifact-type: {artifact_type}
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-04-20'
---

<!-- §content -->

## {name}

<!-- §display -->

### archimate

```yaml
domain: Business
element-type: BusinessObject
label: "{name}"
alias: {alias}
```
""",
        encoding="utf-8",
    )


def test_scaffold_includes_connections_when_entity_ids_are_short_form(tmp_path: Path) -> None:
    repo_root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    source_id = "BOB@1.aaaaaa.enterprise-repository"
    target_id = "BOB@1.bbbbbb.engagement-repository"
    source_path = repo_root / "model" / "business" / "business-object" / f"{source_id}.md"
    target_path = repo_root / "model" / "business" / "business-object" / f"{target_id}.md"
    outgoing_path = repo_root / "model" / "business" / "business-object" / f"{source_id}.outgoing.md"

    _write_entity(
        source_path, artifact_id=source_id, artifact_type="business-object", name="Enterprise Repository", alias="BOB_a"
    )
    _write_entity(
        target_path, artifact_id=target_id, artifact_type="business-object", name="Engagement Repository", alias="BOB_b"
    )
    outgoing_path.write_text(
        f"""\
---
source-entity: {source_id}
version: 0.1.0
status: draft
last-updated: '2026-04-20'
---

<!-- §connections -->

### archimate-association [1] → [1..*] {target_id}

An enterprise repository serves one or more engagement repositories.
""",
        encoding="utf-8",
    )

    result = artifact_diagram_scaffold(
        entity_ids=["BOB@1.aaaaaa", "BOB@1.bbbbbb"],
        diagram_name="Short Id Scaffold",
        repo_root=str(repo_root),
        repo_scope="engagement",
    )

    assert result["entities_not_found"] == []
    assert result["connections_included"] == [
        {"source_alias": "BOB_a", "conn_dir": "association", "target_alias": "BOB_b"}
    ]
    assert "BOB_a -- BOB_b" in str(result["puml"])
