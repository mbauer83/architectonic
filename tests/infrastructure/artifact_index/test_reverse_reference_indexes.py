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


def _write_scratchpad(path: Path, pad_id: str, *, bound_to: str, name: str = "Thinking") -> None:
    """A pad with one note bound to model content.

    `element-type` because the aggregate requires it — a reference without a type describes content the
    scratchpad cannot say anything about — and `destination: element` because a note holding a model
    reference *is* an element. A document missing either is refused and not indexed at all.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"artifact-id: {pad_id}\n"
        "artifact-type: scratchpad\n"
        f"name: {name}\n"
        "description: a pad\n"
        "version: 0.1.0\n"
        "status: active\n"
        "meta-ontology: archimate-4\n"
        "notes:\n"
        "  - id: n1\n"
        "    title: A thought\n"
        "    destination: element\n"
        "    element-type: requirement\n"
        "    model-ref:\n"
        f"      artifact-id: {bound_to}\n"
        "      kind: bound\n",
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
    _write_scratchpad(
        root / "scratchpads" / "uncategorized" / "SCR@1.pad.pad.scratchpad.yaml",
        "SCR@1.pad.pad",
        bound_to=target,
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
    # A scratchpad's references live on the *pad*, because the note carrying one stops being a
    # searchable record — the model answers for that thought instead.
    assert [p.artifact_id for p in store.scratchpads_referencing_artifact("REQ@1.target.target")] == [
        "SCR@1.pad.pad"
    ]


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

    pad_path = root / "scratchpads" / "uncategorized" / "SCR@1.pad.pad.scratchpad.yaml"
    _write_scratchpad(pad_path, "SCR@1.pad.pad", bound_to=other)

    store.apply_file_changes([
        root / "model" / "motivation" / "requirement" / f"{other}.md", diagram_path, grf_path, pad_path,
    ])

    assert store.diagrams_referencing_artifact("REQ@1.target.target") == []
    assert [d.artifact_id for d in store.diagrams_referencing_artifact(other)] == ["DIA@1.probe.probe"]
    assert store.grf_references_to_entity("REQ@1.target.target") == []
    assert [e.artifact_id for e in store.grf_references_to_entity(other)] == ["GRF@1.proxy.proxy"]
    # The pad's note was rebound. Without the incremental half, an entity page would go on linking a
    # pad whose thinking has moved on — for the life of the process.
    assert store.scratchpads_referencing_artifact("REQ@1.target.target") == []
    assert [p.artifact_id for p in store.scratchpads_referencing_artifact(other)] == ["SCR@1.pad.pad"]


class TestASpellingIsNotAnIdentity:
    """A reference is found however the file that holds it spells the id.

    The two diagram writers disagree: an ArchiMate diagram records `connection-ids-used` with short
    endpoints, a C4 diagram records them full. This lookup matched the string as written, so a
    caller holding one spelling saw only the diagrams holding the same one — and callers hold the
    full form, because that is how a connection record spells its `source` and `target`. The
    visible cost was a bulk delete that reconciled the C4 diagrams drawing a deleted connection,
    missed every ArchiMate one, and reported success over a repository left failing verification.
    """

    @staticmethod
    def _both_spellings(tmp_path: Path) -> object:
        """One connection, drawn by two diagrams that spell it differently."""
        root = _repo(tmp_path)
        archimate = root / "diagram-catalog" / "diagrams" / "ARC@1.short.short.puml"
        _write_diagram(
            archimate,
            "ARC@1.short.short",
            entity_id="REQ@1.target",
            connection_id="REQ@1.source---REQ@1.target@@archimate-association",
        )
        return shared_artifact_index(root)

    def test_a_full_form_lookup_finds_the_diagram_that_spelled_it_short(self, tmp_path: Path) -> None:
        store = self._both_spellings(tmp_path)

        found = [d.artifact_id for d in store.diagrams_referencing_artifact(
            "REQ@1.source.source---REQ@1.target.target@@archimate-association"
        )]

        assert found == ["ARC@1.short.short", "DIA@1.probe.probe"]

    def test_a_short_form_lookup_finds_the_diagram_that_spelled_it_full(self, tmp_path: Path) -> None:
        store = self._both_spellings(tmp_path)

        found = [d.artifact_id for d in store.diagrams_referencing_artifact(
            "REQ@1.source---REQ@1.target@@archimate-association"
        )]

        assert found == ["ARC@1.short.short", "DIA@1.probe.probe"]

    def test_an_entity_reference_is_matched_the_same_way(self, tmp_path: Path) -> None:
        store = self._both_spellings(tmp_path)

        assert [d.artifact_id for d in store.diagrams_referencing_artifact("REQ@1.target")] == [
            "ARC@1.short.short", "DIA@1.probe.probe",
        ]
