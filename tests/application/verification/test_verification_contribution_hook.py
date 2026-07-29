"""WU-0.7 acceptance: per-diagram verification-contribution hook.

Verifies that:
- DiagramVerificationContribution.run() is called once per diagram when a module
  is registered for that diagram type.
- The contribution receives a BaseDiagramVerificationContext with the parsed fm.
- artifact_verifier_rules no longer imports any symbol from _verifier_rules_datatype.
- The candidate passed to contributions is a CandidateRepository (protocol).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from src.application.candidate_repository import CandidateRepository
from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_types import VerificationResult
from src.domain.concept_scope import ConceptScope
from src.domain.diagrams.diagram_verification import BaseDiagramVerificationContext

# ── Minimal stubs ─────────────────────────────────────────────────────────────


class _RecordingContribution:
    diagnostic_codes = ("XTEST",)

    def __init__(self) -> None:
        self.calls: list[tuple[Any, BaseDiagramVerificationContext, VerificationResult]] = []

    def run(
        self,
        candidate: Any,
        ctx: BaseDiagramVerificationContext,
        result: VerificationResult,
    ) -> None:
        self.calls.append((candidate, ctx, result))


class _StubRepo:
    def get_entity(self, artifact_id: str) -> None:
        return None

    def get_diagram(self, artifact_id: str) -> None:
        return None

    def list_entities(self, *, artifact_type=None, domain=None, status=None) -> list:
        return []

    def list_diagrams(self, *, diagram_type=None, status=None) -> list:
        return []

    def scope_for_path(self, path: Path) -> Literal["engagement"]:
        return "engagement"


class _FakeModule:
    """Minimal DiagramTypeModule stub for 'test-diagram' type."""

    name = "test-diagram"
    module_class = "architecture"

    def __init__(self, contribution: _RecordingContribution) -> None:
        self._contribution = contribution

    def diagram_verification_contributions(self) -> tuple:
        return (self._contribution,)

    def repository_verification_contributions(self) -> tuple:
        return ()

    # ── Unused protocol stubs ────────────────────────────────────────────────
    @property
    def primary_ontology(self) -> Any:
        return None

    @property
    def element_classes(self) -> dict:
        return {}

    def concept_scope(self, registry: Any = None) -> ConceptScope:
        return ConceptScope.unrestricted()

    def accepts_entity_type(self, t: Any) -> bool:
        return False

    def accepts_connection_type(self, t: Any) -> bool:
        return False

    def effective_entity_types(self) -> dict:
        return {}

    def effective_connection_types(self) -> dict:
        return {}

    @property
    def own_entity_types(self) -> dict:
        return {}

    @property
    def own_connection_types(self) -> dict:
        return {}

    @property
    def ui_config(self) -> Any:
        from src.domain.diagrams.diagram_type_config import DiagramTypeUiConfig  # noqa: PLC0415
        return DiagramTypeUiConfig(label="Test Diagram", entity_search_filter=True)

    @property
    def own_permitted_relationships(self) -> Any:
        from src.domain.relationships.permitted_relationships import PermittedRelationshipSet  # noqa: PLC0415
        return PermittedRelationshipSet.empty()

    @property
    def effective_permitted_relationships(self) -> Any:
        from src.domain.relationships.permitted_relationships import PermittedRelationshipSet  # noqa: PLC0415
        return PermittedRelationshipSet.empty()

    @property
    def bridges(self) -> tuple:
        return ()

    @property
    def renderer(self) -> Any:
        return None

    def write_guidance(self) -> Any:
        from src.domain.diagrams.diagram_type_config import DiagramTypeWriteGuidance  # noqa: PLC0415
        return DiagramTypeWriteGuidance(when_to_use="", when_not_to_use="")

    def build_context_extras(self, repo: Any, diagram_id: str, diagram_entities: dict) -> dict:
        return {}

    def read_diagram_extras(self, parsed_source: dict) -> dict:
        return {}


class _FakeDiagramTypeCatalog:
    def __init__(self, module: _FakeModule) -> None:
        self._module = module

    def find_diagram_type(self, name: str) -> Any:
        return self._module if name == "test-diagram" else None

    def get_diagram_type(self, name: str) -> Any:
        return self._module

    def all_diagram_types(self) -> dict:
        return {"test-diagram": self._module}

    def suppressed_stereotype_tokens(self) -> frozenset:
        return frozenset()

    def diagram_type_domain(self, name: str) -> Any:
        return None


class _FakeRegistry:
    def __init__(self) -> None:
        self._store = _FakeRegistryStore()

    @property
    def repo_roots(self) -> list:
        return []

    def entity_ids(self) -> set:
        return set()

    def connection_ids(self) -> set:
        return set()

    def enterprise_entity_ids(self) -> set:
        return set()

    def enterprise_connection_ids(self) -> set:
        return set()

    def engagement_entity_ids(self) -> set:
        return set()

    def engagement_connection_ids(self) -> set:
        return set()

    def enterprise_document_ids(self) -> set:
        return set()

    def enterprise_diagram_ids(self) -> set:
        return set()

    def entity_status(self, artifact_id: str) -> None:
        return None

    def entity_statuses(self) -> dict:
        return {}

    def connection_status(self, artifact_id: str) -> None:
        return None

    def scope_for_path(self, path: Path) -> str:
        return "engagement"

    def find_file_by_id(self, artifact_id: str) -> None:
        return None

    def get_entity(self, artifact_id: str) -> None:
        return None

    def get_connection(self, artifact_id: str) -> None:
        return None

    def refresh(self) -> None:
        pass


class _FakeRegistryStore:
    def get_entity(self, artifact_id: str) -> None:
        return None

    def get_diagram(self, artifact_id: str) -> None:
        return None

    def scope_for_path(self, path: Path) -> str:
        return "engagement"


def _fake_catalogs(module: _FakeModule) -> RuntimeCatalogs:
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry  # noqa: PLC0415
    real_catalogs = build_runtime_catalogs(get_module_registry())

    fake_dt_catalog = _FakeDiagramTypeCatalog(module)

    return RuntimeCatalogs(
        module_catalog=real_catalogs.module_catalog,
        ontology=real_catalogs.ontology,
        connections=real_catalogs.connections,
        diagram_types=fake_dt_catalog,  # type: ignore[arg-type]
        derivation=real_catalogs.derivation,
    )


def _write_test_diagram(path: Path) -> None:
    path.write_text(
        "---\n"
        "artifact-id: DT-test-123\n"
        "artifact-type: diagram\n"
        "name: Test Diagram\n"
        "diagram-type: test-diagram\n"
        "version: 0.1.0\n"
        "status: draft\n"
        "last-updated: 2026-01-01\n"
        "---\n"
        "@startuml\n"
        "@enduml\n",
        encoding="utf-8",
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_contribution_run_called(tmp_path: Path) -> None:
    """Contribution.run() is invoked once when verifying a diagram of matching type."""
    contribution = _RecordingContribution()
    module = _FakeModule(contribution)
    catalogs = _fake_catalogs(module)
    registry = _FakeRegistry()
    committed_repo = _StubRepo()

    verifier = ArtifactVerifier(
        registry,  # type: ignore[arg-type]
        check_puml_syntax=False,
        catalogs=catalogs,
        committed_repo=committed_repo,
    )
    diag_file = tmp_path / "DT-test-123.puml"
    _write_test_diagram(diag_file)

    verifier.verify_diagram_file(diag_file)

    assert len(contribution.calls) == 1


def test_contribution_receives_context(tmp_path: Path) -> None:
    """The context passed to run() has fm with parsed frontmatter and correct scope."""
    contribution = _RecordingContribution()
    module = _FakeModule(contribution)
    catalogs = _fake_catalogs(module)
    committed_repo = _StubRepo()

    verifier = ArtifactVerifier(
        _FakeRegistry(),  # type: ignore[arg-type]
        check_puml_syntax=False,
        catalogs=catalogs,
        committed_repo=committed_repo,
    )
    diag_file = tmp_path / "DT-test-123.puml"
    _write_test_diagram(diag_file)

    verifier.verify_diagram_file(diag_file)

    assert len(contribution.calls) == 1
    _, ctx, _ = contribution.calls[0]
    assert isinstance(ctx, BaseDiagramVerificationContext)
    assert ctx.fm.get("diagram-type") == "test-diagram"
    assert ctx.scope in ("enterprise", "engagement", "unknown")


def test_contribution_receives_candidate_repo(tmp_path: Path) -> None:
    """The candidate passed to contribution.run satisfies CandidateRepository protocol."""
    contribution = _RecordingContribution()
    module = _FakeModule(contribution)
    catalogs = _fake_catalogs(module)
    committed_repo = _StubRepo()

    verifier = ArtifactVerifier(
        _FakeRegistry(),  # type: ignore[arg-type]
        check_puml_syntax=False,
        catalogs=catalogs,
        committed_repo=committed_repo,
    )
    diag_file = tmp_path / "DT-test-123.puml"
    _write_test_diagram(diag_file)

    verifier.verify_diagram_file(diag_file)

    candidate, _, _ = contribution.calls[0]
    assert isinstance(candidate, CandidateRepository)


def test_no_datatype_import_in_rules_module() -> None:
    """artifact_verifier_rules no longer imports check_datatype_backing_consistency."""
    import src.application.verification.artifact_verifier_rules as rules_module  # noqa: PLC0415
    assert not hasattr(rules_module, "check_datatype_backing_consistency"), (
        "artifact_verifier_rules must not import check_datatype_backing_consistency; "
        "it belongs in the datatype contribution (WU-0.8)"
    )
