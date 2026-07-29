"""Regression: a metadata-only edit_diagram call must not silently discard a
hand-authored `puml=` body on an ArchiMate diagram that also carries occurrence
bindings (`diagram-entities.occurrence`).

Root cause this guards against: `edit_diagram`'s content-determination branch
treated *any* diagram with a `diagram-entities` dict as "diagram_entities is the
body source, re-render it" — correct for diagram-owned types (activity, sequence,
C4, datatype, GSN) but wrong for ArchiMate-family diagrams, where
`diagram-entities.occurrence` is additive binding metadata (WU-B3) sitting on top
of a manually authored `puml=` layout. A plain `artifact_edit_diagram(status=...)`
or `artifact_edit_diagram(group=...)` call on such a diagram re-rendered it from
`diagram_entities` alone, producing an empty/wrong body and wiping the real content.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.diagram_edit import edit_diagram


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


_CUSTOM_GROUPING_MARKER = 'rectangle "Team / Project A" <<CommonGrouping>>'


def _make_archimate_diagram_with_occurrence(repo_root: Path, artifact_id: str) -> Path:
    _write(
        repo_root / "model" / "business" / "business-object" / "BOB@1.a.repo.md",
        "---\nartifact-id: BOB@1.a.repo\nartifact-type: business-object\nname: Repo\n"
        "version: 0.1.0\nstatus: draft\nlast-updated: '2026-01-01'\n---\n\n## Repo\n",
    )
    path = repo_root / "diagram-catalog" / "diagrams" / f"{artifact_id}.puml"
    _write(
        path,
        f"""\
---
artifact-id: {artifact_id}
artifact-type: diagram
name: Two Team View
version: 0.1.0
status: draft
diagram-type: archimate-layered
entity-ids-used:
- BOB@1.a.repo
connection-ids-used: []
diagram-entities:
  occurrence:
  - id: occ-repo-team-b
bindings:
- id: bind-occ-repo-team-b
  subject:
    kind: entity
    id: occ-repo-team-b
  correspondence_kind: represents
  target:
    entity_id: BOB@1.a.repo
last-updated: '2026-01-01'
---
@startuml two-team-view
hide stereotype
skinparam rectangle<<CommonGrouping>> {{
  BackgroundColor #EDE8E1
}}
{_CUSTOM_GROUPING_MARKER} {{
  rectangle "Repo" <<business_object>> as BOB_repo
}}
rectangle "Team / Project B" <<CommonGrouping>> {{
  rectangle "Repo" <<business_object>> as BOB_repo__2
}}
@enduml
""",
    )
    return path


def test_status_only_edit_preserves_hand_authored_puml_with_occurrence(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "model").mkdir(parents=True)
    (repo_root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    artifact_id = "ARC@1.x.two-team-view"
    _make_archimate_diagram_with_occurrence(repo_root, artifact_id)

    result = edit_diagram(
        repo_root=repo_root,
        verifier=_verifier(repo_root),
        clear_repo_caches=_noop_caches,
        artifact_id=artifact_id,
        status="active",
        dry_run=True,
    )

    assert result.content is not None
    assert _CUSTOM_GROUPING_MARKER in result.content
    assert 'rectangle "Team / Project B"' in result.content


def test_group_move_preserves_hand_authored_puml_with_occurrence(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "model").mkdir(parents=True)
    (repo_root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    artifact_id = "ARC@1.x.two-team-view-group"
    _make_archimate_diagram_with_occurrence(repo_root, artifact_id)

    result = edit_diagram(
        repo_root=repo_root,
        verifier=_verifier(repo_root),
        clear_repo_caches=_noop_caches,
        artifact_id=artifact_id,
        group="my-collection",
        dry_run=False,
    )

    assert result.wrote, result.verification
    new_path = repo_root / "diagram-catalog" / "diagrams" / "my-collection" / f"{artifact_id}.puml"
    assert new_path.exists()
    assert _CUSTOM_GROUPING_MARKER in new_path.read_text()
