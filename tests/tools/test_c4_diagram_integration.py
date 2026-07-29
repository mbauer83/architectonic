from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from src.application.artifact_query import ArtifactRepository
from src.application.startup_validation import validate_repo_compatibility
from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.infrastructure.app_bootstrap import build_module_registry
from src.infrastructure.artifact_index import shared_artifact_index


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry  # noqa: PLC0415

    return build_runtime_catalogs(get_module_registry())


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


_ACTOR_ID = "ACT@1000000000.Cust01.customer"
_SYSTEM_ID = "APP@1000000001.Order1.ordering-system"
_PAYMENTS_ID = "APP@1000000002.Paymt2.payments-platform"
_DIAGRAM_ID = "CSC@1000000003.Ctx001.ordering-context"
_CONNECTION_ID = f"{_ACTOR_ID}---{_SYSTEM_ID}@@archimate-association"

_ACTOR_CONTENT = f"""\
---
artifact-id: {_ACTOR_ID}
artifact-type: business-actor
name: Customer
version: 0.1.0
status: draft
last-updated: '2026-05-11'
---

<!-- §content -->
## Customer

<!-- §display -->
### archimate
```yaml
domain: Business
element-type: BusinessActor
label: "Customer"
alias: ACT_Cust01
```
"""

_SYSTEM_CONTENT = f"""\
---
artifact-id: {_SYSTEM_ID}
artifact-type: application-component
name: Ordering System
version: 0.1.0
status: draft
last-updated: '2026-05-11'
---

<!-- §content -->
## Ordering System

<!-- §display -->
### archimate
```yaml
domain: Application
element-type: ApplicationComponent
label: "Ordering System"
alias: APP_Order1
```
"""

_PAYMENTS_CONTENT = f"""\
---
artifact-id: {_PAYMENTS_ID}
artifact-type: application-component
name: Payments Platform
version: 0.1.0
status: draft
last-updated: '2026-05-11'
---

<!-- §content -->
## Payments Platform

<!-- §display -->
### archimate
```yaml
domain: Application
element-type: ApplicationComponent
label: "Payments Platform"
alias: APP_Paymt2
```
"""

_OUTGOING_CONTENT = f"""\
---
source-entity: {_ACTOR_ID}
version: 0.1.0
status: draft
last-updated: '2026-05-11'
---

<!-- §connections -->

### archimate-association → {_SYSTEM_ID}

Uses the ordering system
"""

_C4_DIAGRAM_CONTENT = f"""\
---
artifact-id: {_DIAGRAM_ID}
artifact-type: diagram
name: Ordering Context
version: 0.1.0
status: draft
diagram-type: c4-system-context
entity-ids-used:
  - {_ACTOR_ID}
  - {_SYSTEM_ID}
  - {_PAYMENTS_ID}
connection-ids-used:
  - {_CONNECTION_ID}
diagram-entities:
  person:
    - id: customer
      label: Customer
      entity_id: {_ACTOR_ID}
      description: Places orders
  software-system:
    - id: ordering
      label: Ordering System
      entity_id: {_SYSTEM_ID}
      scope: true
      description: Processes customer orders
    - id: payments
      label: Payments Platform
      entity_id: {_PAYMENTS_ID}
      external: true
last-updated: '2026-05-11'
---
@startuml ordering-context
left to right direction
skinparam shadowing false
title Ordering Context
actor "Customer\\nPlaces orders" as ACT_Cust01
rectangle "Ordering System\\nProcesses customer orders" <<C4System>> as APP_Order1
rectangle "Payments Platform" <<C4External>> as APP_Paymt2
ACT_Cust01 -[hidden]right- APP_Order1
APP_Order1 -[hidden]right- APP_Paymt2
ACT_Cust01 --> APP_Order1 : Uses the ordering system
@enduml
"""


def _build_repo(root: Path) -> Path:
    _write(root / "model" / "business" / "business-actor" / f"{_ACTOR_ID}.md", _ACTOR_CONTENT)
    _write(root / "model" / "application" / "application-component" / f"{_SYSTEM_ID}.md", _SYSTEM_CONTENT)
    _write(root / "model" / "application" / "application-component" / f"{_PAYMENTS_ID}.md", _PAYMENTS_CONTENT)
    _write(
        root / "model" / "business" / "business-actor" / f"{_ACTOR_ID}.outgoing.md",
        _OUTGOING_CONTENT,
    )
    _write(root / "diagram-catalog" / "diagrams" / f"{_DIAGRAM_ID}.puml", _C4_DIAGRAM_CONTENT)
    return root


def test_c4_diagram_verification_and_validation_pass(tmp_path: Path) -> None:
    repo_root = _build_repo(tmp_path / "repo")
    registry = ArtifactRegistry(shared_artifact_index(repo_root))
    diagram_path = repo_root / "diagram-catalog" / "diagrams" / f"{_DIAGRAM_ID}.puml"

    result = ArtifactVerifier(registry, check_puml_syntax=False, catalogs=_catalogs()).verify_diagram_file(diagram_path)

    assert result.valid, [issue.message for issue in result.issues]
    validate_repo_compatibility(ArtifactRepository(shared_artifact_index(repo_root)), build_module_registry())


def test_c4_diagram_only_entities_are_indexed_and_queryable(tmp_path: Path) -> None:
    repo_root = _build_repo(tmp_path / "repo")
    repo = ArtifactRepository(shared_artifact_index(repo_root))

    summaries = repo.list_artifacts(domain="c4-system-context")
    artifact_ids = {summary.artifact_id for summary in summaries}

    assert f"{_DIAGRAM_ID}#person/customer" in artifact_ids
    assert f"{_DIAGRAM_ID}#software-system/ordering" in artifact_ids

    person_summary = next(summary for summary in summaries if summary.artifact_id == f"{_DIAGRAM_ID}#person/customer")
    assert person_summary.host_diagram_id == _DIAGRAM_ID

    person_artifact = repo.read_artifact(f"{_DIAGRAM_ID}#person/customer")
    assert person_artifact is not None
    assert person_artifact["host_diagram_id"] == _DIAGRAM_ID
    assert person_artifact["artifact_type"] == "person"

    search_hits = repo.search_artifacts("Payments Platform", limit=10).hits
    hit_ids = {hit.record.artifact_id for hit in search_hits}
    assert f"{_DIAGRAM_ID}#software-system/payments" in hit_ids
