"""Behavioural tests for ArtifactVerifier rules.

Covers verify_entity_file, verify_outgoing_file, and verify_all for both
single-repo and two-repo setups.  GRF-specific verifier rules are in
test_two_repo_and_grf.py; this file covers the non-GRF verification paths.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest

from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.artifact_index import shared_artifact_index

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _all_entity_types() -> dict:
    from src.infrastructure.app_bootstrap import build_module_registry  # noqa: PLC0415

    return {str(k): v for k, v in build_module_registry().all_entity_types().items()}


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs  # noqa: PLC0415

    return build_runtime_catalogs(build_module_registry())


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _entity(
    artifact_id: str,
    artifact_type: str = "requirement",
    name: str = "Test Entity",
    *,
    extra_fm: str = "",
    no_content_section: bool = False,
    no_display_section: bool = False,
) -> str:
    prefix = artifact_id.split("@")[0]
    rand = artifact_id.split(".")[1] if "." in artifact_id else "XXXXXX"
    content_marker = "" if no_content_section else "<!-- §content -->"
    display_marker = "" if no_display_section else "<!-- §display -->"
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: {artifact_type}
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-04-17'{extra_fm}
---

{content_marker}

## {name}

{display_marker}

### archimate

```yaml
domain: Motivation
element-type: Requirement
label: "{name}"
alias: {prefix}_{rand}
```
"""


def _outgoing(source: str, connections: list[tuple[str, str]]) -> str:
    sections = "\n".join(f"### {ct} → {tgt}\n" for ct, tgt in connections)
    return f"""\
---
source-entity: {source}
version: 0.1.0
status: draft
last-updated: '2026-04-17'
---

<!-- §connections -->

{sections}
"""


def _diagram(name: str, body: str, extra_fm: str = "") -> str:
    return f"""\
---
artifact-id: {name}
artifact-type: diagram
name: "Test Diagram"
version: 0.1.0
status: draft
diagram-type: archimate-application
last-updated: '2026-04-29'{extra_fm}
---
{body}
"""


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


# ---------------------------------------------------------------------------
# verify_entity_file
# ---------------------------------------------------------------------------


class TestVerifyEntityFile:
    @pytest.mark.verifies("REQ@1712870400.V5EdQk")
    def test_valid_entity_passes(self, repo: Path) -> None:
        eid = "REQ@1000000000.AbcDef.my-req"
        path = repo / "model" / "motivation" / "requirement" / f"{eid}.md"
        _write(path, _entity(eid))
        result = ArtifactVerifier(catalogs=_catalogs()).verify_entity_file(path)
        assert result.valid, [i.message for i in result.issues]

    @pytest.mark.verifies("REQ@1712870400.Aa1Bb1")
    def test_missing_artifact_id_field(self, repo: Path) -> None:
        path = repo / "model" / "motivation" / "requirement" / "REQ@1000000001.XxXxXx.bad.md"
        _write(
            path,
            """\
---
artifact-type: requirement
name: "Bad"
version: 0.1.0
status: draft
last-updated: '2026-04-17'
---
<!-- §content -->
## Bad
<!-- §display -->
### archimate
```yaml
domain: Motivation
element-type: Requirement
label: "Bad"
alias: REQ_XxXxXx
```
""",
        )
        result = ArtifactVerifier(catalogs=_catalogs()).verify_entity_file(path)
        assert not result.valid
        codes = {i.code for i in result.issues if i.severity == "error"}
        assert "E021" in codes  # missing required field

    def test_invalid_artifact_type(self, repo: Path) -> None:
        eid = "REQ@1000000002.AbcDef.bad-type"
        path = repo / "model" / "motivation" / "requirement" / f"{eid}.md"
        content = _entity(eid, artifact_type="not-a-real-type")
        _write(path, content)
        result = ArtifactVerifier(catalogs=_catalogs()).verify_entity_file(path)
        assert not result.valid
        assert any(i.code == "E102" for i in result.issues)

    @pytest.mark.verifies("REQ@1712870400.V5EdQk")
    def test_missing_content_section(self, repo: Path) -> None:
        eid = "REQ@1000000003.AbcDef.no-content"
        path = repo / "model" / "motivation" / "requirement" / f"{eid}.md"
        _write(path, _entity(eid, no_content_section=True))
        result = ArtifactVerifier(catalogs=_catalogs()).verify_entity_file(path)
        assert not result.valid
        assert any(i.code == "E031" for i in result.issues)

    def test_artifact_id_mismatch(self, repo: Path) -> None:
        eid = "REQ@1000000004.AbcDef.correct-name"
        wrong_id = "REQ@1000000004.AbcDef.wrong-name"
        path = repo / "model" / "motivation" / "requirement" / f"{eid}.md"
        _write(path, _entity(wrong_id))  # frontmatter id ≠ filename
        result = ArtifactVerifier(catalogs=_catalogs()).verify_entity_file(path)
        assert not result.valid
        assert any(i.code == "E104" for i in result.issues)

    def test_invalid_status_value(self, repo: Path) -> None:
        eid = "REQ@1000000005.AbcDef.bad-status"
        path = repo / "model" / "motivation" / "requirement" / f"{eid}.md"
        _write(path, _entity(eid, extra_fm="\nbad-status: yes").replace("status: draft", "status: invalid-value"))
        result = ArtifactVerifier(catalogs=_catalogs()).verify_entity_file(path)
        assert not result.valid
        assert any(i.code == "E022" for i in result.issues)


def _document_schema(repo: Path) -> None:
    schema_path = repo / ".arch-repo" / "documents" / "adr.json"
    _write(
        schema_path,
        """\
{
  "abbreviation": "ADR",
  "name": "Architecture Decision Record",
  "frontmatter_schema": {
    "type": "object",
    "required": ["artifact-id", "artifact-type", "doc-type", "title", "status", "version", "last-updated"],
    "properties": {
      "artifact-id": { "type": "string" },
      "artifact-type": { "const": "document" },
      "doc-type": { "const": "adr" },
      "title": { "type": "string" },
      "status": { "type": "string" },
      "version": { "type": "string" },
      "last-updated": { "type": "string" }
    }
  },
  "required_sections": ["Context", "Decision", "Consequences"]
}
""",
    )


def _document_schema_with_sections(
    repo: Path,
    *,
    sections: str,
    document_required: str = "",
) -> None:
    schema_path = repo / ".arch-repo" / "documents" / "adr.json"
    document_required_text = (
        f',\n  "required_connections": {document_required}' if document_required else ""
    )
    _write(
        schema_path,
        f"""\
{{
  "abbreviation": "ADR",
  "name": "Architecture Decision Record",
  "frontmatter_schema": {{
    "type": "object",
    "required": ["artifact-id", "artifact-type", "doc-type", "title", "status", "version", "last-updated"],
    "properties": {{
      "artifact-id": {{ "type": "string" }},
      "artifact-type": {{ "const": "document" }},
      "doc-type": {{ "const": "adr" }},
      "title": {{ "type": "string" }},
      "status": {{ "type": "string" }},
      "version": {{ "type": "string" }},
      "last-updated": {{ "type": "string" }}
    }}
  }},
  "sections": {sections}{document_required_text}
}}
""",
    )


def _document(artifact_id: str, body: str) -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: document
doc-type: adr
title: "ADR Title"
status: draft
version: 0.1.0
last-updated: '2026-04-22'
---

## Context

{body}

## Decision

Decision.

## Consequences

Consequences.
"""


def _write_linked_document(repo: Path, artifact_id: str) -> str:
    """A second ADR beside the document under test; returns the href that reaches it."""
    _write(repo / "documents" / "adr" / f"{artifact_id}.md", _document(artifact_id, "Peer."))
    return f"{artifact_id}.md"


def _write_linked_diagram(
    repo: Path, artifact_id: str, diagram_type: str, *, suffix: str = ".md"
) -> str:
    """A stored diagram of *diagram_type*; returns the href that reaches it from `documents/adr/`.

    The type is written as the frontmatter says it, registered or not — which is the point of the
    unregistered cases below. `.md` and `.puml` are both diagram sources, and which one a type uses
    is a property of its notation rather than of the link.
    """
    _write(
        repo / "diagram-catalog" / "diagrams" / f"{artifact_id}{suffix}",
        f"""\
---
artifact-id: {artifact_id}
artifact-type: diagram
diagram-type: {diagram_type}
name: "Linked Diagram"
version: 0.1.0
status: draft
last-updated: '2026-04-22'
---
""",
    )
    return f"../../diagram-catalog/diagrams/{artifact_id}{suffix}"


def _document_with_body(artifact_id: str, body: str) -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: document
doc-type: adr
title: "ADR Title"
status: draft
version: 0.1.0
last-updated: '2026-04-22'
---

{body}
"""


# ---------------------------------------------------------------------------
# verify_outgoing_file
# ---------------------------------------------------------------------------


class TestVerifyOutgoingFile:
    def _setup_entities(self, repo: Path, *eids_and_types) -> None:
        for eid, etype in eids_and_types:
            info = _all_entity_types()[etype]
            path = repo / "model" / Path(*info.hierarchy) / f"{eid}.md"
            _write(path, _entity(eid, etype))

    def test_valid_outgoing_passes(self, repo: Path) -> None:
        src = "REQ@1000000000.SrcAaa.src"
        tgt = "REQ@1000000001.TgtBbb.tgt"
        self._setup_entities(repo, (src, "requirement"), (tgt, "requirement"))
        out_path = repo / "model" / "motivation" / "requirement" / f"{src}.outgoing.md"
        _write(out_path, _outgoing(src, [("archimate-association", tgt)]))
        registry = ArtifactRegistry(shared_artifact_index(repo))
        result = ArtifactVerifier(registry, catalogs=_catalogs()).verify_outgoing_file(out_path)
        assert result.valid, [i.message for i in result.issues]

    def test_unknown_source_entity(self, repo: Path) -> None:
        tgt = "REQ@1000000001.TgtBbb.tgt"
        self._setup_entities(repo, (tgt, "requirement"))
        ghost_src = "REQ@9999999999.GhostX.ghost"
        out_path = repo / "model" / "motivation" / "requirement" / f"{ghost_src}.outgoing.md"
        _write(out_path, _outgoing(ghost_src, [("archimate-association", tgt)]))
        registry = ArtifactRegistry(shared_artifact_index(repo))
        result = ArtifactVerifier(registry, catalogs=_catalogs()).verify_outgoing_file(out_path)
        assert not result.valid
        assert any(i.code == "E120" for i in result.issues)

    @pytest.mark.verifies("REQ@1712870400.Ee3Ff3")
    def test_unknown_target_entity(self, repo: Path) -> None:
        src = "REQ@1000000000.SrcAaa.src"
        self._setup_entities(repo, (src, "requirement"))
        out_path = repo / "model" / "motivation" / "requirement" / f"{src}.outgoing.md"
        _write(out_path, _outgoing(src, [("archimate-association", "REQ@9999999999.GhostX.ghost")]))
        registry = ArtifactRegistry(shared_artifact_index(repo))
        result = ArtifactVerifier(registry, catalogs=_catalogs()).verify_outgoing_file(out_path)
        assert not result.valid
        assert any(i.code == "E124" for i in result.issues)


class TestVerifyDiagramFile:
    def _setup_entities(self, repo: Path, *eids_and_types) -> None:
        for eid, etype in eids_and_types:
            info = _all_entity_types()[etype]
            path = repo / "model" / Path(*info.hierarchy) / f"{eid}.md"
            _write(path, _entity(eid, etype))

    def test_hallucinated_relation_macro_fails(self, repo: Path) -> None:
        src = "SRV@1000000000.SrcAaa.authoring-service"
        tgt = "ROL@1000000001.TgtBbb.author"
        self._setup_entities(repo, (src, "service"), (tgt, "role"))

        diagram_path = repo / "diagram-catalog" / "diagrams" / "service-landscape.puml"
        _write(
            diagram_path,
            _diagram(
                "service-landscape",
                """\
@startuml service-landscape
!include ../_archimate-stereotypes.puml
title Test Diagram
rectangle "Authoring Service" <<Service>> as SRV_SrcAaa
rectangle "Author" <<Role>> as ROL_TgtBbb
Rel_Serving(SRV_SrcAaa, ROL_TgtBbb, "")
@enduml
""",
            ),
        )

        registry = ArtifactRegistry(shared_artifact_index(repo))
        verifier = ArtifactVerifier(registry, check_puml_syntax=False, catalogs=_catalogs())
        result = verifier.verify_diagram_file(diagram_path)

        assert not result.valid
        assert any(i.code == "E312" for i in result.issues)

    def test_reversed_realization_macro_is_accepted(self, repo: Path) -> None:
        service = "SRV@1000000000.SrcAaa.authoring-service"
        component = "APP@1000000001.TgtBbb.cli-tool"
        self._setup_entities(repo, (service, "service"), (component, "application-component"))

        out_path = repo / "model" / "common" / "services" / f"{service}.outgoing.md"
        _write(out_path, _outgoing(service, [("archimate-realization", component)]))

        diagram_path = repo / "diagram-catalog" / "diagrams" / "realization-view.puml"
        _write(
            diagram_path,
            _diagram(
                "realization-view",
                """\
@startuml realization-view
!include ../_archimate-stereotypes.puml
title Test Diagram
rectangle "CLI Tool" <<ApplicationComponent>> as APP_TgtBbb
rectangle "Authoring Service" <<Service>> as SRV_SrcAaa
Rel_Realization_Up(APP_TgtBbb, SRV_SrcAaa, "")
@enduml
""",
                # The completeness invariant requires the diagram to bind what it draws;
                # this test's concern is only that the REVERSED macro direction is accepted.
                extra_fm=(
                    f"\nentity-ids-used:\n- {service}\n- {component}"
                    f"\nconnection-ids-used:\n- {service}---{component}@@archimate-realization"
                ),
            ),
        )

        registry = ArtifactRegistry(shared_artifact_index(repo))
        verifier = ArtifactVerifier(registry, check_puml_syntax=False, catalogs=_catalogs())
        result = verifier.verify_diagram_file(diagram_path)

        assert result.valid, [i.message for i in result.issues]

    def test_inlined_archimate_stereotypes_are_accepted(self, repo: Path) -> None:
        src = "REQ@1000000000.SrcAaa.src"
        tgt = "REQ@1000000001.TgtBbb.tgt"
        self._setup_entities(repo, (src, "requirement"), (tgt, "requirement"))

        diagram_path = repo / "diagram-catalog" / "diagrams" / "inline-archimate.puml"
        _write(
            diagram_path,
            _diagram(
                "inline-archimate",
                """\
@startuml inline-archimate
hide stereotype
skinparam rectangle<<Requirement>> {
  BackgroundColor #EDD6F0
  BorderColor #7B3F9A
}
title Test Diagram
rectangle "Source" <<Requirement>> as REQ_SrcAaa
rectangle "Target" <<Requirement>> as REQ_TgtBbb
@enduml
""",
            ),
        )

        registry = ArtifactRegistry(shared_artifact_index(repo))
        verifier = ArtifactVerifier(registry, check_puml_syntax=False, catalogs=_catalogs())
        result = verifier.verify_diagram_file(diagram_path)

        assert result.valid, [i.message for i in result.issues]

    def test_unknown_connection_type(self, repo: Path) -> None:
        src = "REQ@1000000000.SrcAaa.src"
        tgt = "REQ@1000000001.TgtBbb.tgt"
        self._setup_entities(repo, (src, "requirement"), (tgt, "requirement"))
        out_path = repo / "model" / "motivation" / "requirement" / f"{src}.outgoing.md"
        _write(out_path, _outgoing(src, [("not-a-real-connection-type", tgt)]))
        registry = ArtifactRegistry(shared_artifact_index(repo))
        result = ArtifactVerifier(registry, catalogs=_catalogs()).verify_outgoing_file(out_path)
        assert not result.valid
        assert any(i.code == "E123" for i in result.issues)

    def test_missing_connections_section_marker(self, repo: Path) -> None:
        src = "REQ@1000000000.SrcAaa.src"
        tgt = "REQ@1000000001.TgtBbb.tgt"
        self._setup_entities(repo, (src, "requirement"), (tgt, "requirement"))
        out_path = repo / "model" / "motivation" / "requirement" / f"{src}.outgoing.md"
        content = _outgoing(src, [("archimate-association", tgt)]).replace("<!-- §connections -->", "")
        _write(out_path, content)
        registry = ArtifactRegistry(shared_artifact_index(repo))
        result = ArtifactVerifier(registry, catalogs=_catalogs()).verify_outgoing_file(out_path)
        assert not result.valid
        assert any(i.code == "E121" for i in result.issues)

    def test_enterprise_outgoing_cannot_target_engagement_entity(self, tmp_path: Path) -> None:
        eng_root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
        ent_root = tmp_path / "enterprise-repository"
        (eng_root / "model").mkdir(parents=True)
        (ent_root / "model").mkdir(parents=True)

        eng_id = "REQ@1000000000.EngAaa.eng-req"
        ent_id = "REQ@2000000000.EntBbb.ent-req"
        _write(
            eng_root / "model" / "motivation" / "requirement" / f"{eng_id}.md",
            _entity(eng_id),
        )
        _write(
            ent_root / "model" / "motivation" / "requirement" / f"{ent_id}.md",
            _entity(ent_id),
        )
        # Enterprise outgoing targeting engagement entity → error
        out_path = ent_root / "model" / "motivation" / "requirement" / f"{ent_id}.outgoing.md"
        _write(out_path, _outgoing(ent_id, [("archimate-association", eng_id)]))
        registry = ArtifactRegistry(shared_artifact_index([eng_root, ent_root]))
        result = ArtifactVerifier(registry, catalogs=_catalogs()).verify_outgoing_file(out_path)
        assert not result.valid
        assert any(i.code == "E130" for i in result.issues)


class TestVerifyDocumentFile:
    def test_relative_internal_markdown_link_is_allowed(self, repo: Path) -> None:
        _document_schema(repo)
        target_id = "ADR@1000000001.AbcDef.target"
        source_id = "ADR@1000000000.AbcDef.source"
        target = repo / "documents" / "adr" / f"{target_id}.md"
        source = repo / "documents" / "adr" / f"{source_id}.md"
        _write(target, _document(target_id, "Target body."))
        _write(source, _document(source_id, f"[Target](./{target_id}.md)"))

        registry = ArtifactRegistry(shared_artifact_index(repo))
        result = ArtifactVerifier(registry, catalogs=_catalogs()).verify_document_file(source)

        assert result.valid, [i.message for i in result.issues]
        assert not any(i.code == "W156" for i in result.issues)

    def test_absolute_internal_markdown_link_warns(self, repo: Path) -> None:
        _document_schema(repo)
        source_id = "ADR@1000000000.AbcDef.source"
        source = repo / "documents" / "adr" / f"{source_id}.md"
        _write(
            source,
            _document(
                source_id,
                "[Absolute](/tmp/workspace/architecture-repository/model/application/components/APP@1.AbcDef.target.md)",
            ),
        )

        registry = ArtifactRegistry(shared_artifact_index(repo))
        result = ArtifactVerifier(registry, catalogs=_catalogs()).verify_document_file(source)

        assert any(i.code == "W156" for i in result.issues)
        assert any("must be relative" in i.message for i in result.issues)

    def test_required_entity_connection_accepts_class_term(self, repo: Path) -> None:
        _document_schema(repo)
        schema_path = repo / ".arch-repo" / "documents" / "adr.json"
        schema_path.write_text(
            schema_path.read_text(encoding="utf-8").replace(
                '"required_sections": ["Context", "Decision", "Consequences"]',
                '"required_sections": ["Context", "Decision", "Consequences"],\n'
                '  "required_entity_type_connections": ["@internal-behavior-element"]',
            ),
            encoding="utf-8",
        )
        entity_id = "FNC@1000000002.AbcDef.function"
        info = _all_entity_types()["function"]
        entity_path = repo / "model" / Path(*info.hierarchy) / f"{entity_id}.md"
        _write(entity_path, _entity(entity_id, "function"))

        doc_id = "ADR@1000000000.AbcDef.source"
        doc_path = repo / "documents" / "adr" / f"{doc_id}.md"
        _write(doc_path, _document(doc_id, f"[Function](../../model/{'/'.join(info.hierarchy)}/{entity_id}.md)"))

        verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())
        result = verifier.verify_document_file(doc_path)

        assert not any(i.code == "E155" for i in result.issues), [i.message for i in result.issues]

    def test_required_entity_connection_reports_class_term_readably(self, repo: Path) -> None:
        _document_schema(repo)
        schema_path = repo / ".arch-repo" / "documents" / "adr.json"
        schema_path.write_text(
            schema_path.read_text(encoding="utf-8").replace(
                '"required_sections": ["Context", "Decision", "Consequences"]',
                '"required_sections": ["Context", "Decision", "Consequences"],\n'
                '  "required_entity_type_connections": ["@internal-behavior-element"]',
            ),
            encoding="utf-8",
        )
        doc_id = "ADR@1000000000.AbcDef.source"
        doc_path = repo / "documents" / "adr" / f"{doc_id}.md"
        _write(doc_path, _document(doc_id, "No entity links."))

        verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())
        result = verifier.verify_document_file(doc_path)

        e155_messages = [i.message for i in result.issues if i.code == "E155"]
        assert e155_messages == ["Required entity-type connection missing: link at least one internal behavior element"]

    def test_required_entity_connection_accepts_all_term(self, repo: Path) -> None:
        _document_schema(repo)
        schema_path = repo / ".arch-repo" / "documents" / "adr.json"
        schema_path.write_text(
            schema_path.read_text(encoding="utf-8").replace(
                '"required_sections": ["Context", "Decision", "Consequences"]',
                '"required_sections": ["Context", "Decision", "Consequences"],\n'
                '  "required_entity_type_connections": ["@all"]',
            ),
            encoding="utf-8",
        )
        entity_id = "REQ@1000000003.AbcDef.req"
        info = _all_entity_types()["requirement"]
        entity_path = repo / "model" / Path(*info.hierarchy) / f"{entity_id}.md"
        _write(entity_path, _entity(entity_id, "requirement"))

        doc_id = "ADR@1000000000.AbcDef.source"
        doc_path = repo / "documents" / "adr" / f"{doc_id}.md"
        _write(
            doc_path,
            _document(
                doc_id,
                f"[Requirement](../../model/{'/'.join(info.hierarchy)}/{entity_id}.md#details)",
            ),
        )

        verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())
        result = verifier.verify_document_file(doc_path)

        assert not any(i.code == "E155" for i in result.issues), [i.message for i in result.issues]

    def test_section_required_entity_connection_must_be_in_that_section(self, repo: Path) -> None:
        _document_schema_with_sections(
            repo,
            sections=(
                '[{"name": "Context", "required_entity_type_connections": ["requirement"]}, '
                '{"name": "Decision"}, {"name": "Consequences"}]'
            ),
        )
        entity_id = "REQ@1000000004.AbcDef.req"
        info = _all_entity_types()["requirement"]
        entity_path = repo / "model" / Path(*info.hierarchy) / f"{entity_id}.md"
        _write(entity_path, _entity(entity_id, "requirement"))

        doc_id = "ADR@1000000000.AbcDef.source"
        doc_path = repo / "documents" / "adr" / f"{doc_id}.md"
        _write(
            doc_path,
            _document_with_body(
                doc_id,
                "## Context\n\nNo entity links here.\n\n"
                "## Decision\n\n"
                f"[Requirement](../../model/{'/'.join(info.hierarchy)}/{entity_id}.md)\n\n"
                "## Consequences\n\nConsequences.",
            ),
        )

        verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())
        result = verifier.verify_document_file(doc_path)

        e156_messages = [i.message for i in result.issues if i.code == "E156"]
        assert e156_messages == [
            "Required entity-type connection missing in section 'Context': link at least one requirement"
        ]
        assert not any(i.code == "E155" for i in result.issues), [i.message for i in result.issues]

    def test_document_required_entity_connection_still_matches_any_section(self, repo: Path) -> None:
        _document_schema_with_sections(
            repo,
            sections='[{"name": "Context"}, {"name": "Decision"}, {"name": "Consequences"}]',
            document_required='["requirement"]',
        )
        entity_id = "REQ@1000000005.AbcDef.req"
        info = _all_entity_types()["requirement"]
        entity_path = repo / "model" / Path(*info.hierarchy) / f"{entity_id}.md"
        _write(entity_path, _entity(entity_id, "requirement"))

        doc_id = "ADR@1000000000.AbcDef.source"
        doc_path = repo / "documents" / "adr" / f"{doc_id}.md"
        _write(
            doc_path,
            _document_with_body(
                doc_id,
                "## Context\n\nNo entity links here.\n\n"
                "## Decision\n\n"
                f"[Requirement](../../model/{'/'.join(info.hierarchy)}/{entity_id}.md)\n\n"
                "## Consequences\n\nConsequences.",
            ),
        )

        verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())
        result = verifier.verify_document_file(doc_path)

        assert not any(i.code == "E155" for i in result.issues), [i.message for i in result.issues]
        assert not any(i.code == "E156" for i in result.issues), [i.message for i in result.issues]

    def test_a_linked_document_does_not_satisfy_an_entity_term(self, repo: Path) -> None:
        """The reading this replaced reported every artifact's `artifact-type`, so a linked document
        contributed the literal type `document` and a linked diagram the literal type `diagram` to
        the set an entity term was matched against. Harmless only while no entity type is spelled
        either way."""
        _document_schema_with_sections(
            repo,
            sections='[{"name": "Context"}, {"name": "Decision"}, {"name": "Consequences"}]',
            document_required='["requirement"]',
        )
        peer = _write_linked_document(repo, "ADR@1000000020.AbcDef.peer")
        doc_id = "ADR@1000000021.AbcDef.source"
        doc_path = repo / "documents" / "adr" / f"{doc_id}.md"
        _write(doc_path, _document(doc_id, f"[Peer]({peer})"))

        verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())
        result = verifier.verify_document_file(doc_path)

        assert [i.message for i in result.issues if i.code == "E155"] == [
            "Required entity-type connection missing: link at least one requirement"
        ]

    def test_required_document_type_connection_is_met_by_a_link_to_one(self, repo: Path) -> None:
        _document_schema_with_sections(
            repo,
            sections='[{"name": "Context"}, {"name": "Decision"}, {"name": "Consequences"}]',
            document_required='["doc:adr"]',
        )
        peer = _write_linked_document(repo, "ADR@1000000022.AbcDef.peer")
        doc_id = "ADR@1000000023.AbcDef.source"
        doc_path = repo / "documents" / "adr" / f"{doc_id}.md"
        _write(doc_path, _document(doc_id, f"[Peer]({peer})"))

        verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())
        result = verifier.verify_document_file(doc_path)

        assert not any(i.code == "E155" for i in result.issues), [i.message for i in result.issues]

    def test_required_document_type_connection_missing_reports_the_type_name(self, repo: Path) -> None:
        _document_schema_with_sections(
            repo,
            sections='[{"name": "Context"}, {"name": "Decision"}, {"name": "Consequences"}]',
            document_required='["doc:adr"]',
        )
        doc_id = "ADR@1000000024.AbcDef.source"
        doc_path = repo / "documents" / "adr" / f"{doc_id}.md"
        _write(doc_path, _document(doc_id, "No links."))

        verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())
        result = verifier.verify_document_file(doc_path)

        assert [i.message for i in result.issues if i.code == "E155"] == [
            "Required document-type connection missing: link at least one Architecture Decision Record"
        ]

    def test_unknown_document_type_term_is_an_error_on_the_document(self, repo: Path) -> None:
        _document_schema_with_sections(
            repo,
            sections='[{"name": "Context"}, {"name": "Decision"}, {"name": "Consequences"}]',
            document_required='["doc:not-a-doc-type"]',
        )
        doc_id = "ADR@1000000025.AbcDef.source"
        doc_path = repo / "documents" / "adr" / f"{doc_id}.md"
        _write(doc_path, _document(doc_id, "No links."))

        verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())
        result = verifier.verify_document_file(doc_path)

        assert [i.message for i in result.issues if i.code == "E155"] == [
            "Unknown required document-type connection term: not a doc type (doc:not-a-doc-type)"
        ]

    def test_a_diagram_requirement_is_met_by_a_link_to_a_puml_source(self, repo: Path) -> None:
        """A diagram's source is `.puml` unless its notation is markdown, which only the matrix
        type's is. A link reading that accepts `.md` alone sees no diagram at all, so every
        `diagram:` term would have been unsatisfiable by the diagrams the product mostly writes."""
        _document_schema_with_sections(
            repo,
            sections='[{"name": "Context"}, {"name": "Decision"}, {"name": "Consequences"}]',
            document_required='["diagram:c4-container"]',
        )
        diagram = _write_linked_diagram(
            repo, "CC@1000000034.AbcDef.containers", "c4-container", suffix=".puml"
        )
        doc_id = "ADR@1000000035.AbcDef.source"
        doc_path = repo / "documents" / "adr" / f"{doc_id}.md"
        _write(doc_path, _document(doc_id, f"[Containers]({diagram})"))

        verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())
        result = verifier.verify_document_file(doc_path)

        assert not any(i.code in ("E155", "E156", "W159") for i in result.issues), [
            i.message for i in result.issues
        ]

    def test_a_broken_link_to_a_diagram_source_is_reported(self, repo: Path) -> None:
        """W155 watched `.md` alone, so a link to a deleted PlantUML diagram went unreported — and a
        document type can now require such a link."""
        _document_schema(repo)
        doc_id = "ADR@1000000037.AbcDef.source"
        doc_path = repo / "documents" / "adr" / f"{doc_id}.md"
        _write(
            doc_path,
            _document(doc_id, "[Gone](../../diagram-catalog/diagrams/CSC@1.AbcDef.gone.puml)"),
        )

        verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())
        result = verifier.verify_document_file(doc_path)

        assert [i.message for i in result.issues if i.code == "W155"] == [
            "Unresolvable internal link: '../../diagram-catalog/diagrams/CSC@1.AbcDef.gone.puml'"
        ]

    def test_a_link_to_a_file_that_is_not_an_artifact_source_resolves_to_nothing(
        self, repo: Path
    ) -> None:
        _document_schema_with_sections(
            repo,
            sections='[{"name": "Context"}, {"name": "Decision"}, {"name": "Consequences"}]',
            document_required='["diagram:matrix"]',
        )
        _write(repo / "diagram-catalog" / "diagrams" / "notes.txt", "not an artifact")
        doc_id = "ADR@1000000036.AbcDef.source"
        doc_path = repo / "documents" / "adr" / f"{doc_id}.md"
        _write(doc_path, _document(doc_id, "[Notes](../../diagram-catalog/diagrams/notes.txt)"))

        verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())
        result = verifier.verify_document_file(doc_path)

        assert any(i.code == "E155" for i in result.issues)

    def test_section_required_diagram_type_connection_is_met_by_a_link_to_one(self, repo: Path) -> None:
        _document_schema_with_sections(
            repo,
            sections=(
                '[{"name": "Context", "required_connections": ["diagram:matrix"]}, '
                '{"name": "Decision"}, {"name": "Consequences"}]'
            ),
        )
        diagram = _write_linked_diagram(repo, "MAT@1000000026.AbcDef.grid", "matrix")
        doc_id = "ADR@1000000027.AbcDef.source"
        doc_path = repo / "documents" / "adr" / f"{doc_id}.md"
        _write(doc_path, _document(doc_id, f"[Grid]({diagram})"))

        verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())
        result = verifier.verify_document_file(doc_path)

        assert not any(i.code in ("E155", "E156", "W159") for i in result.issues), [
            i.message for i in result.issues
        ]

    def test_section_required_diagram_type_connection_missing_is_e156(self, repo: Path) -> None:
        _document_schema_with_sections(
            repo,
            sections=(
                '[{"name": "Context", "required_connections": ["diagram:matrix"]}, '
                '{"name": "Decision"}, {"name": "Consequences"}]'
            ),
        )
        doc_id = "ADR@1000000028.AbcDef.source"
        doc_path = repo / "documents" / "adr" / f"{doc_id}.md"
        _write(doc_path, _document(doc_id, "No links."))

        verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())
        result = verifier.verify_document_file(doc_path)

        # The label is the registered module's, not the slug: a message that named `matrix` would be
        # telling an author the schema's spelling rather than what they would go and create.
        matrix_label = _catalogs().diagram_types.get_diagram_type("matrix").ui_config.label
        assert [i.message for i in result.issues if i.code == "E156"] == [
            f"Required diagram-type connection missing in section 'Context': link at least one {matrix_label}"
        ]

    def test_unregistered_diagram_type_warns_rather_than_refusing(self, repo: Path) -> None:
        """A repository outlives any one deployment's module set: a host without the confidential
        store registers no assurance diagram types. A template requiring one must not become
        unsatisfiable because of what the host happens to provide."""
        _document_schema_with_sections(
            repo,
            sections='[{"name": "Context"}, {"name": "Decision"}, {"name": "Consequences"}]',
            document_required='["diagram:not-a-registered-type"]',
        )
        doc_id = "ADR@1000000029.AbcDef.source"
        doc_path = repo / "documents" / "adr" / f"{doc_id}.md"
        _write(doc_path, _document(doc_id, "No links."))

        verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())
        result = verifier.verify_document_file(doc_path)

        assert not any(i.code in ("E155", "E156") for i in result.issues), [
            i.message for i in result.issues
        ]
        assert [i.message for i in result.issues if i.code == "W159"] == [
            "Required diagram-type connection unverifiable: diagram type 'not-a-registered-type' "
            "is not registered in this deployment, and nothing links one"
        ]

    def test_unregistered_diagram_type_is_still_satisfied_by_a_stored_diagram(self, repo: Path) -> None:
        _document_schema_with_sections(
            repo,
            sections='[{"name": "Context"}, {"name": "Decision"}, {"name": "Consequences"}]',
            document_required='["diagram:not-a-registered-type"]',
        )
        diagram = _write_linked_diagram(repo, "BOW@1000000030.AbcDef.stored", "not-a-registered-type")
        doc_id = "ADR@1000000031.AbcDef.source"
        doc_path = repo / "documents" / "adr" / f"{doc_id}.md"
        _write(doc_path, _document(doc_id, f"[Stored]({diagram})"))

        verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())
        result = verifier.verify_document_file(doc_path)

        assert not any(i.code in ("E155", "E156", "W159") for i in result.issues), [
            i.message for i in result.issues
        ]

    def test_doc_any_term_is_met_by_a_document_of_any_type(self, repo: Path) -> None:
        _document_schema_with_sections(
            repo,
            sections='[{"name": "Context"}, {"name": "Decision"}, {"name": "Consequences"}]',
            document_required='["doc:@all"]',
        )
        peer = _write_linked_document(repo, "ADR@1000000032.AbcDef.peer")
        doc_id = "ADR@1000000033.AbcDef.source"
        doc_path = repo / "documents" / "adr" / f"{doc_id}.md"
        _write(doc_path, _document(doc_id, f"[Peer]({peer})"))

        verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())
        result = verifier.verify_document_file(doc_path)

        assert not any(i.code == "E155" for i in result.issues), [i.message for i in result.issues]

    def test_unknown_section_entity_connection_term_warns(self, repo: Path) -> None:
        _document_schema_with_sections(
            repo,
            sections=(
                '[{"name": "Context", "required_entity_type_connections": ["@not-a-real-class"]}, '
                '{"name": "Decision"}, {"name": "Consequences"}]'
            ),
        )

        doc_id = "ADR@1000000000.AbcDef.source"
        doc_path = repo / "documents" / "adr" / f"{doc_id}.md"
        _write(doc_path, _document(doc_id, "No entity links."))

        verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())
        result = verifier.verify_document_file(doc_path)

        w157_messages = [i.message for i in result.issues if i.code == "W157"]
        assert w157_messages == [
            "Unknown required entity-type connection term in section 'Context': not a real class (@not-a-real-class)"
        ]


# ---------------------------------------------------------------------------
# verify_all
# ---------------------------------------------------------------------------


class TestVerifyAll:
    @pytest.mark.verifies("REQ@1712870400.JTRw1x")
    def test_verify_all_passes_clean_repo(self, repo: Path) -> None:
        eid = "REQ@1000000000.AbcDef.clean"
        _write(
            repo / "model" / "motivation" / "requirement" / f"{eid}.md",
            _entity(eid),
        )
        registry = ArtifactRegistry(shared_artifact_index(repo))
        results = ArtifactVerifier(registry, catalogs=_catalogs()).verify_all(repo, include_diagrams=False)
        assert all(r.valid for r in results), [
            f"{r.path.name}: {[i.message for i in r.issues]}" for r in results if not r.valid
        ]

    def test_verify_all_finds_errors_in_bad_entity(self, repo: Path) -> None:
        eid = "REQ@1000000000.AbcDef.bad"
        path = repo / "model" / "motivation" / "requirement" / f"{eid}.md"
        _write(path, _entity(eid, no_content_section=True))
        registry = ArtifactRegistry(shared_artifact_index(repo))
        results = ArtifactVerifier(registry, catalogs=_catalogs()).verify_all(repo, include_diagrams=False)
        assert any(not r.valid for r in results)

    def test_verify_all_two_repos(self, tmp_path: Path) -> None:
        eng_root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
        ent_root = tmp_path / "enterprise-repository"
        (eng_root / "model").mkdir(parents=True)
        (ent_root / "model").mkdir(parents=True)

        eng_id = "REQ@1000000000.EngAaa.eng"
        ent_id = "REQ@2000000000.EntBbb.ent"
        _write(eng_root / "model" / "motivation" / "requirement" / f"{eng_id}.md", _entity(eng_id))
        _write(ent_root / "model" / "motivation" / "requirement" / f"{ent_id}.md", _entity(ent_id))

        registry = ArtifactRegistry(shared_artifact_index([eng_root, ent_root]))
        # verify_all for each root independently
        for root in (eng_root, ent_root):
            results = ArtifactVerifier(registry, catalogs=_catalogs()).verify_all(root, include_diagrams=False)
            assert all(r.valid for r in results), [
                i.message for r in results for i in r.issues if i.severity == "error"
            ]

    def test_verify_all_includes_project_scoped_entities(self, repo: Path) -> None:
        # Regression: the verifier inventory rooted only at top-level model/, silently
        # excluding every entity/connection under projects/<slug>/model/ (the group-aware
        # target layout) from repo-wide verification, while the index scan saw them.
        legacy_id = "REQ@1000000000.LegAaa.legacy"
        proj_id = "REQ@1000000001.PrjBbb.project-scoped"
        _write(repo / "model" / "motivation" / "requirement" / f"{legacy_id}.md", _entity(legacy_id))
        _write(
            repo / "projects" / "demo" / "model" / "motivation" / "requirement" / f"{proj_id}.md",
            _entity(proj_id),
        )
        registry = ArtifactRegistry(shared_artifact_index(repo))
        results = ArtifactVerifier(registry, catalogs=_catalogs()).verify_all(repo, include_diagrams=False)
        verified = {r.path.name for r in results}
        assert f"{proj_id}.md" in verified, "project-scoped entity must be verified, not silently excluded"
        assert f"{legacy_id}.md" in verified
        assert all(r.valid for r in results), [
            f"{r.path.name}: {[i.message for i in r.issues]}" for r in results if not r.valid
        ]
