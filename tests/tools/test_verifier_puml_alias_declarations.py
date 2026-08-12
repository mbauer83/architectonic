"""E318: a body that declares an alias twice is refused, because PlantUML will not say so.

The rule exists because `artifact_verify` called a body `valid: true` while four of its containers
rendered empty — every id resolved, so every rule that asks about *ids* was satisfied. What was
wrong was the body's own shape, which nothing was reading.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.verification._verifier_rules_puml_declarations import check_puml_alias_declarations
from src.application.verification.artifact_verifier_types import VerificationResult
from src.domain.modules.catalogs import DiagramTypeCatalog


def _diagram_types() -> DiagramTypeCatalog:
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs  # noqa: PLC0415

    return build_runtime_catalogs(build_module_registry()).diagram_types


def _codes(content: str, fm: dict) -> list[str]:
    result = VerificationResult(path=Path("/tmp/d.puml"), file_type="diagram")
    check_puml_alias_declarations(
        content, fm, result, "/tmp/d.puml", diagram_type_catalog=_diagram_types()
    )
    return [issue.code for issue in result.issues]


_ARCHIMATE = {"diagram-type": "archimate-technology"}

_ONE_EACH = """@startuml v
title v
rectangle "Subscription" <<grouping>> as GRP_sub {
  rectangle "Environment" <<grouping>> as GRP_env
}
rectangle "West Europe" <<location>> as LOC_region
LOC_region --> GRP_env
@enduml
"""

_DECLARED_TWICE = """@startuml v
title v
rectangle "Subscription" <<grouping>> as GRP_sub {
  rectangle "Environment" <<grouping>> as GRP_env
}
rectangle "West Europe" <<location>> as LOC_region {
  rectangle "Environment" <<grouping>> as GRP_env
}
@enduml
"""


class TestADuplicateDeclarationIsRefused:
    def test_a_body_declaring_each_alias_once_passes(self) -> None:
        assert _codes(_ONE_EACH, _ARCHIMATE) == []

    def test_the_same_alias_in_two_containers_is_an_error(self) -> None:
        assert _codes(_DECLARED_TWICE, _ARCHIMATE) == ["E318"]

    def test_the_message_names_the_alias_and_the_count(self) -> None:
        result = VerificationResult(path=Path("/tmp/d.puml"), file_type="diagram")
        check_puml_alias_declarations(
            _DECLARED_TWICE, _ARCHIMATE, result, "/tmp/d.puml",
            diagram_type_catalog=_diagram_types(),
        )

        (issue,) = result.issues
        assert "GRP_env" in issue.message and "2 times" in issue.message

    def test_a_decorated_declaration_still_counts(self) -> None:
        """The reading must see past a trailing colour — the defect 0.5.3 fixed, restated over the
        rule that now depends on it, since the renderer colours every specialised element."""
        body = _DECLARED_TWICE.replace(
            'rectangle "Environment" <<grouping>> as GRP_env\n}',
            'rectangle "Environment" <<grouping>> as GRP_env #E6F3FF\n}',
        )

        assert _codes(body, _ARCHIMATE) == ["E318"]

    def test_three_declarations_are_reported_once_with_the_count(self) -> None:
        body = _DECLARED_TWICE.replace(
            "@enduml", 'rectangle "Environment" <<grouping>> as GRP_env\n@enduml'
        )

        result = VerificationResult(path=Path("/tmp/d.puml"), file_type="diagram")
        check_puml_alias_declarations(
            body, _ARCHIMATE, result, "/tmp/d.puml", diagram_type_catalog=_diagram_types()
        )

        (issue,) = result.issues
        assert "3 times" in issue.message


class TestScope:
    """A type that owns its entity types speaks its own body vocabulary, and its bodies carry
    prose. The repository's persistence-model datatype diagram says "persisted as a single
    markdown file" twice — two declarations of `a` to any reader of the syntax, and no element."""

    def test_prose_in_a_diagram_only_type_is_not_a_declaration(self) -> None:
        body = """@startuml v
title v
class Artifact {
    role: Any versioned element persisted as a single markdown file
    other: Narrative content persisted as a markdown document
}
@enduml
"""

        assert _codes(body, {"diagram-type": "datatype"}) == []

    def test_a_relation_macro_declares_nothing(self) -> None:
        """`Rel_*(SRC, TGT, "")` names two aliases and declares neither. Reading a macro's first
        argument as a declaration — which one of the owner's readings does, for the renderers that
        emit `Person(alias, "label")` — reported three duplicates in a clean diagram in this
        repository, where the same element is both drawn once and used in several relations."""
        body = """@startuml v
title v
rectangle "Promote Artifacts" <<process>> as PRC_0Rz5Ex
rectangle "Reference File" <<data_object>> as DOB_4dO6js
Rel_Access(PRC_0Rz5Ex, DOB_4dO6js, "")
Rel_Realization(PRC_0Rz5Ex, DOB_4dO6js, "")
@enduml
"""

        assert _codes(body, _ARCHIMATE) == []

    def test_two_aliases_differing_only_by_hyphen_are_two_elements(self) -> None:
        """PlantUML does not fold `-` to `_`; a reading that normalises would invent a duplicate."""
        body = """@startuml v
title v
rectangle "A" as GRP-a
rectangle "B" as GRP_a
@enduml
"""

        assert _codes(body, _ARCHIMATE) == []

    def test_the_same_prose_in_an_archimate_body_is_still_checked(self) -> None:
        """Scope is the diagram type, not the presence of prose — an ArchiMate body is code."""
        body = """@startuml v
title v
rectangle "A" as GRP_a
rectangle "B" as GRP_a
@enduml
"""

        assert _codes(body, _ARCHIMATE) == ["E318"]


class TestTheVerifierSurfacesTheRule:
    """A rule the verifier does not call is a rule nobody runs."""

    def test_verify_diagram_file_reports_the_duplicate(self, tmp_path: Path) -> None:
        from src.application.verification.artifact_verifier import ArtifactVerifier  # noqa: PLC0415
        from src.application.verification.artifact_verifier_registry import ArtifactRegistry  # noqa: PLC0415
        from src.infrastructure.app_bootstrap import (  # noqa: PLC0415
            build_module_registry,
            build_runtime_catalogs,
        )
        from src.infrastructure.artifact_index import shared_artifact_index  # noqa: PLC0415

        diagrams = tmp_path / "diagram-catalog" / "diagrams"
        diagrams.mkdir(parents=True)
        (tmp_path / "model").mkdir()
        diagram_path = diagrams / "ARC@1000000009.DiagAa.view.puml"
        diagram_path.write_text(
            """---
artifact-id: ARC@1000000009.DiagAa.view
artifact-type: diagram
name: "View"
version: 0.1.0
status: draft
diagram-type: archimate-technology
entity-ids-used: []
last-updated: '2026-08-12'
---
"""
            + _DECLARED_TWICE,
            encoding="utf-8",
        )
        catalogs = build_runtime_catalogs(build_module_registry())
        verifier = ArtifactVerifier(
            ArtifactRegistry(shared_artifact_index(tmp_path)), check_puml_syntax=False, catalogs=catalogs
        )

        result = verifier.verify_diagram_file(diagram_path)

        assert any(issue.code == "E318" for issue in result.issues), [i.message for i in result.issues]


class TestTheRealRepositorySatisfiesIt:
    """Stated as an invariant over whatever the repository holds, not over a count of files."""

    @pytest.fixture(scope="class")
    def archimate_bodies(self) -> list[tuple[Path, str]]:
        roots = [Path("engagements"), Path("enterprise-repository")]
        return [
            (path, text)
            for root in roots
            for path in sorted(root.rglob("*"))
            if path.suffix in {".puml", ".md"}
            and "@startuml" in (text := path.read_text(encoding="utf-8", errors="replace"))
            and "diagram-type: archimate" in text
        ]

    def test_no_archimate_diagram_declares_an_alias_twice(
        self, archimate_bodies: list[tuple[Path, str]]
    ) -> None:
        assert archimate_bodies, "no ArchiMate diagrams found — the walk is looking in the wrong place"

        offenders = {
            str(path): _codes(text, _ARCHIMATE) for path, text in archimate_bodies if _codes(text, _ARCHIMATE)
        }

        assert offenders == {}, offenders
