"""Shared fixture builder for search-visibility tests.

Not itself a test module — imported by the search-visibility test files. Builds
engagement (and optionally enterprise) repos containing a global-artifact-reference
(GAR) proxy plus regular artifacts that match the same query tokens, so each search
surface can assert that hidden internal types never appear while eligible artifacts do.
"""

from __future__ import annotations

from pathlib import Path

GAR_TYPE = "global-artifact-reference"
EXCLUDED_TYPES = frozenset({GAR_TYPE})

REQ_ID = "REQ@1000000101.VisReq.coding-guidelines-requirement"
CAP_ID = "CAP@1000000102.VisCap.guidelines-capability"
GAR_ID = "GAR@1000000103.VisGar.general-coding-guidelines"
DOC_ID = "STD@1000000104.VisDoc.coding-guidelines-standard"
ENTERPRISE_REQ_ID = "REQ@1000000105.VisEnt.enterprise-guidelines-requirement"

QUERY = "guidelines"


def write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def entity_md(artifact_id: str, artifact_type: str, name: str) -> str:
    return (
        "---\n"
        f"artifact-id: {artifact_id}\n"
        f"artifact-type: {artifact_type}\n"
        f"name: {name}\n"
        "version: 0.1.0\n"
        "status: draft\n"
        "last-updated: '2026-01-01'\n"
        "---\n\n"
        f"## {name}\n"
    )


def gar_md(artifact_id: str, name: str, *, global_artifact_id: str) -> str:
    return (
        "---\n"
        f"artifact-id: {artifact_id}\n"
        f"artifact-type: {GAR_TYPE}\n"
        f"name: {name}\n"
        "version: 0.1.0\n"
        "status: active\n"
        "last-updated: '2026-01-01'\n"
        f"global-artifact-id: {global_artifact_id}\n"
        "global-artifact-type: document\n"
        "---\n\n"
        f"## {name}\n\n"
        f"Engagement-repo proxy for promoted document `{global_artifact_id}`.\n"
    )


def document_md(artifact_id: str, title: str) -> str:
    return (
        "---\n"
        f"artifact-id: {artifact_id}\n"
        "artifact-type: document\n"
        "doc-type: standard\n"
        f"title: {title}\n"
        "version: 0.1.0\n"
        "status: draft\n"
        "last-updated: '2026-01-01'\n"
        "---\n\n"
        f"# {title}\n\n"
        "These guidelines cover naming and style.\n"
    )


def write_gar(root: Path, *, gar_id: str = GAR_ID, name: str = "General coding guidelines") -> None:
    write_file(
        root / "model" / "common" / GAR_TYPE / f"{gar_id}.md",
        gar_md(gar_id, name, global_artifact_id=DOC_ID),
    )


def build_engagement_repo(tmp_path: Path, *, with_document: bool = True) -> Path:
    """Engagement repo: one GAR, one requirement, one capability, one document —
    all matching the shared QUERY token."""
    root = tmp_path / "engagements" / "ENG-VIS" / "architecture-repository"
    write_file(
        root / "model" / "motivation" / "requirement" / f"{REQ_ID}.md",
        entity_md(REQ_ID, "requirement", "Coding Guidelines Requirement"),
    )
    write_file(
        root / "model" / "strategy" / "capability" / f"{CAP_ID}.md",
        entity_md(CAP_ID, "capability", "Guidelines Capability"),
    )
    write_gar(root)
    if with_document:
        write_file(root / "docs" / "standard" / f"{DOC_ID}.md", document_md(DOC_ID, "Coding Guidelines Standard"))
    return root


def build_enterprise_repo(tmp_path: Path) -> Path:
    root = tmp_path / "enterprise-repository"
    write_file(
        root / "model" / "motivation" / "requirement" / f"{ENTERPRISE_REQ_ID}.md",
        entity_md(ENTERPRISE_REQ_ID, "requirement", "Enterprise Guidelines Requirement"),
    )
    return root
