from __future__ import annotations

from pathlib import Path

from src.infrastructure.artifact_index import shared_artifact_index


def _write_entity(path: Path, artifact_id: str, artifact_type: str, name: str, extra: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"artifact-id: {artifact_id}\n"
        f"artifact-type: {artifact_type}\n"
        f"name: {name}\n"
        "version: 0.1.0\n"
        "status: draft\n"
        "last-updated: '2026-01-01'\n"
        f"{extra}"
        "---\n\n"
        f"## {name}\n",
        encoding="utf-8",
    )


def _write_diagram(path: Path, diagram_id: str, *, entity_id: str, connection_id: str) -> None:
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


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    target = "REQ@1.target.target"
    source = "REQ@1.source.source"
    conn = f"{source}---{target}@@archimate-association"
    _write_entity(root / "model" / "motivation" / "requirement" / f"{target}.md", target, "requirement", "Target")
    _write_entity(root / "model" / "motivation" / "requirement" / f"{source}.md", source, "requirement", "Source")
    _write_entity(
        root / "model" / "common" / "global-entity-reference" / "GRF@1.proxy.proxy.md",
        "GRF@1.proxy.proxy",
        "global-entity-reference",
        "Proxy",
        extra=f"global-artifact-id: {target}\n",
    )
    outgoing = root / "model" / "motivation" / "requirement" / f"{source}.outgoing.md"
    outgoing.write_text(
        "---\nsource-entity: REQ@1.source.source\nversion: 0.1.0\nstatus: draft\n---\n\n"
        "### archimate-association → REQ@1.target.target\n",
        encoding="utf-8",
    )
    _write_diagram(
        root / "diagram-catalog" / "diagrams" / "DIA@1.probe.probe.puml",
        "DIA@1.probe.probe",
        entity_id=target,
        connection_id=conn,
    )
    return root


def test_reverse_reference_indexes_are_built_by_full_refresh(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    store = shared_artifact_index(root)

    assert [d.artifact_id for d in store.diagrams_referencing_artifact("REQ@1.target.target")] == ["DIA@1.probe.probe"]
    assert [d.artifact_id for d in store.diagrams_referencing_artifact(
        "REQ@1.source.source---REQ@1.target.target@@archimate-association"
    )] == ["DIA@1.probe.probe"]
    assert [e.artifact_id for e in store.grf_references_to_entity("REQ@1.target.target")] == ["GRF@1.proxy.proxy"]


def test_reverse_reference_indexes_update_incrementally(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    store = shared_artifact_index(root)
    store.read_model_version()

    other = "REQ@1.other.other"
    _write_entity(root / "model" / "motivation" / "requirement" / f"{other}.md", other, "requirement", "Other")
    diagram_path = root / "diagram-catalog" / "diagrams" / "DIA@1.probe.probe.puml"
    _write_diagram(
        diagram_path,
        "DIA@1.probe.probe",
        entity_id=other,
        connection_id="missing---missing@@archimate-association",
    )
    grf_path = root / "model" / "common" / "global-entity-reference" / "GRF@1.proxy.proxy.md"
    _write_entity(
        grf_path,
        "GRF@1.proxy.proxy",
        "global-entity-reference",
        "Proxy",
        extra=f"global-artifact-id: {other}\n",
    )

    store.apply_file_changes([root / "model" / "motivation" / "requirement" / f"{other}.md", diagram_path, grf_path])

    assert store.diagrams_referencing_artifact("REQ@1.target.target") == []
    assert [d.artifact_id for d in store.diagrams_referencing_artifact(other)] == ["DIA@1.probe.probe"]
    assert store.grf_references_to_entity("REQ@1.target.target") == []
    assert [e.artifact_id for e in store.grf_references_to_entity(other)] == ["GRF@1.proxy.proxy"]
