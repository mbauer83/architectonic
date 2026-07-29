"""Shared fixture builder for CombinedArtifactView parity tests.

Not itself a test module (leading underscore) — imported by the sibling
test_combined_artifact_view_*.py files.
"""

from __future__ import annotations

from pathlib import Path

from src.domain.artifact_id import stable_id


def write_entity(path: Path, artifact_id: str, name: str, *, status: str = "draft") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"artifact-id: {artifact_id}\n"
        "artifact-type: requirement\n"
        f"name: {name}\n"
        "version: 0.1.0\n"
        f"status: {status}\n"
        "last-updated: '2026-01-01'\n"
        "---\n\n"
        f"## {name}\n",
        encoding="utf-8",
    )


def write_connection(root: Path, source_id: str, target_id: str, *, conn_type: str = "archimate-association") -> str:
    """Writes `source_id`'s outgoing.md with one link to `target_id`; returns the connection id."""
    path = root / "model" / "motivation" / "requirement" / f"{source_id}.outgoing.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nsource-entity: {source_id}\nversion: 0.1.0\nstatus: draft\n---\n\n"
        f"### {conn_type} → {target_id}\n",
        encoding="utf-8",
    )
    return f"{stable_id(source_id)}---{stable_id(target_id)}@@{conn_type}"


def write_diagram(path: Path, diagram_id: str, *, entity_id: str, connection_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"artifact-id: {diagram_id}\n"
        "artifact-type: diagram\n"
        "diagram-type: c4-container\n"
        "name: Probe\n"
        "version: 0.1.0\n"
        "status: draft\n"
        "last-updated: '2026-01-01'\n"
        "entity-ids-used:\n"
        f"  - {entity_id}\n"
        "connection-ids-used:\n"
        f"  - {connection_id}\n"
        "---\n"
        "@startuml\n@enduml\n",
        encoding="utf-8",
    )


def write_document(path: Path, doc_id: str, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"artifact-id: {doc_id}\n"
        "artifact-type: document\n"
        "doc-type: adr\n"
        f"title: {title}\n"
        "status: draft\n"
        "---\n\n"
        f"{title}\n",
        encoding="utf-8",
    )


def write_grf_proxy(path: Path, grf_id: str, *, target_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"artifact-id: {grf_id}\n"
        "artifact-type: global-entity-reference\n"
        "name: Proxy\n"
        "version: 0.1.0\n"
        "status: draft\n"
        "last-updated: '2026-01-01'\n"
        f"global-artifact-id: {target_id}\n"
        "---\n\n"
        "## Proxy\n",
        encoding="utf-8",
    )


# Deterministic, non-colliding, cross-repo-interleaved ids (sorted globally as
# entA(1) < engB(2) < entC(3) < engD(4)) so a true global merge is distinguishable
# from a naive per-instance-sorted-then-concatenated result.
ENT_A = "REQ@1.entA.entA"
ENG_B = "REQ@2.engB.engB"
ENT_C = "REQ@3.entC.entC"
ENG_D = "REQ@4.engD.engD"


def build_two_repo_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """Builds an engagement+enterprise pair with one entity pair, one connection, one
    diagram, one document, and one GRF proxy per repo — ids interleave globally and
    never collide, so combined-view merge/fallback correctness can be checked against
    each side's own single-instance result independently."""
    engagement = tmp_path / "engagements" / "ENG" / "architecture-repository"
    enterprise = tmp_path / "enterprise-repository"

    write_entity(enterprise / "model" / "motivation" / "requirement" / f"{ENT_A}.md", ENT_A, "Enterprise Alpha")
    write_entity(engagement / "model" / "motivation" / "requirement" / f"{ENG_B}.md", ENG_B, "Engagement Beta")
    write_entity(enterprise / "model" / "motivation" / "requirement" / f"{ENT_C}.md", ENT_C, "Enterprise Gamma")
    write_entity(engagement / "model" / "motivation" / "requirement" / f"{ENG_D}.md", ENG_D, "Engagement Delta")

    ent_conn = write_connection(enterprise, ENT_A, ENT_C)
    eng_conn = write_connection(engagement, ENG_B, ENG_D)

    write_diagram(
        enterprise / "diagram-catalog" / "diagrams" / "DIA@1.entDia.entDia.puml",
        "DIA@1.entDia.entDia",
        entity_id=ENT_A,
        connection_id=ent_conn,
    )
    write_diagram(
        engagement / "diagram-catalog" / "diagrams" / "DIA@2.engDia.engDia.puml",
        "DIA@2.engDia.engDia",
        entity_id=ENG_B,
        connection_id=eng_conn,
    )

    write_document(enterprise / "docs" / "ADR@1.entDoc.entDoc.md", "ADR@1.entDoc.entDoc", "Enterprise Decision")
    write_document(engagement / "docs" / "ADR@2.engDoc.engDoc.md", "ADR@2.engDoc.engDoc", "Engagement Decision")

    write_grf_proxy(
        engagement / "model" / "common" / "global-entity-reference" / "GRF@1.proxy.proxy.md",
        "GRF@1.proxy.proxy",
        target_id=ENT_A,
    )

    return engagement, enterprise
