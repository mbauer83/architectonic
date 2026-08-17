"""A document's link to a diagram must resolve in the write path's staging copy.

A proposed document is verified by writing it into a temp tree that mirrors the repository around
it. The mirror symlinked `.arch-repo`, `model` and `projects`, so a link to a model entity resolved
and a link to a *diagram* did not — the diagram catalog was not there at all.

That went unnoticed while the unresolvable-link rule only ever looked at `.md`: a diagram's source
is `.puml`, so every such link was skipped before it could be checked. Widening the rule made the
gap visible immediately, and in the worst way — the write was *refused*, because a document linking
a diagram now failed verification that the real repository passes. A document type can require a
diagram link, so this is the ordinary case rather than an edge one.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.verify import verify_content_in_temp_path

_ADR_SCHEMA = {
    "abbreviation": "ADR",
    "name": "Architecture Decision Record",
    "required_sections": ["Context"],
}

_DIAGRAM = """\
---
artifact-id: CSC@1000000001.AbcDef.a-context
artifact-type: diagram
diagram-type: c4-system-context
name: "A Context"
version: 0.1.0
status: draft
last-updated: '2026-08-16'
---
@startuml
title A Context
@enduml
"""


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-STAGE" / "architecture-repository"
    schemata = root / ".arch-repo" / "documents"
    schemata.mkdir(parents=True)
    (schemata / "adr.json").write_text(json.dumps(_ADR_SCHEMA), encoding="utf-8")
    (root / "model").mkdir(parents=True, exist_ok=True)
    diagrams = root / "diagram-catalog" / "diagrams"
    diagrams.mkdir(parents=True)
    (diagrams / "CSC@1000000001.AbcDef.a-context.puml").write_text(_DIAGRAM, encoding="utf-8")
    (root / "docs" / "adr").mkdir(parents=True)
    return root


def _document(href: str) -> str:
    return f"""\
---
artifact-id: ADR@1000000002.AbcDef.links-a-diagram
artifact-type: document
doc-type: adr
title: "Links a diagram"
status: draft
version: 0.1.0
last-updated: '2026-08-16'
---

## Context

See [A Context]({href}).
"""


def _verify(root: Path, href: str):
    catalogs = build_runtime_catalogs(get_module_registry())
    verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(root)), catalogs=catalogs)
    return verify_content_in_temp_path(
        verifier=verifier,
        file_type="document",
        desired_name="adr/ADR@1000000002.AbcDef.links-a-diagram.md",
        content=_document(href),
        support_repo_root=root,
    )


def test_a_link_to_a_diagram_resolves_in_the_staging_copy(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    result = _verify(root, "../../diagram-catalog/diagrams/CSC@1000000001.AbcDef.a-context.puml")

    assert [i.message for i in result.issues] == []
    assert result.valid


def test_a_link_to_a_diagram_that_is_not_there_is_still_reported(tmp_path: Path) -> None:
    """The mirror must make the check *correct*, not silent — a genuinely broken link still warns."""
    root = _repo(tmp_path)

    result = _verify(root, "../../diagram-catalog/diagrams/CSC@1000000009.ZzzZzz.gone.puml")

    assert [i.code for i in result.issues] == ["W155"]
