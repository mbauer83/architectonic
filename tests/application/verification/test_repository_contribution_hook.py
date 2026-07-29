"""WU-0.7b acceptance: per-transaction repository-contribution hook.

Verifies that:
- RepositoryVerificationContribution.run() is called once per verify_all, not
  once per diagram file.
- The contribution receives a RepositoryVerificationContext with committed,
  candidate, and location attributes.
- Scanning multiple diagram files does NOT cause duplication.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_types import VerificationResult
from src.domain.diagrams.diagram_verification import RepositoryVerificationContext

# ── Stubs ─────────────────────────────────────────────────────────────────────


class _CountingRepoContribution:
    diagnostic_codes = ("XREPO",)

    def __init__(self) -> None:
        self.calls: list[tuple[RepositoryVerificationContext, VerificationResult]] = []

    def run(self, ctx: RepositoryVerificationContext, result: VerificationResult) -> None:
        self.calls.append((ctx, result))


class _ModuleWithRepoContrib:
    """Minimal DiagramTypeModule stub that returns a counting repo contribution."""

    name = "repo-test-diagram"
    module_class = "architecture"

    def __init__(self, contribution: _CountingRepoContribution) -> None:
        self._contribution = contribution

    def diagram_verification_contributions(self) -> tuple:
        return ()

    def repository_verification_contributions(self) -> tuple:
        return (self._contribution,)

    @property
    def primary_ontology(self) -> Any:
        return None

    @property
    def element_classes(self) -> dict:
        return {}

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
        return DiagramTypeUiConfig(label="Repo Test", entity_search_filter=True)

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
    def __init__(self, module: _ModuleWithRepoContrib) -> None:
        self._module = module

    def find_diagram_type(self, name: str) -> Any:
        return self._module if name == "repo-test-diagram" else None

    def get_diagram_type(self, name: str) -> Any:
        return self._module

    def all_diagram_types(self) -> dict:
        return {"repo-test-diagram": self._module}

    def suppressed_stereotype_tokens(self) -> frozenset:
        return frozenset()

    def diagram_type_domain(self, name: str) -> Any:
        return None


class _StubCommittedRepo:
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


def _make_catalogs(module: _ModuleWithRepoContrib):
    from src.application.runtime_catalogs import RuntimeCatalogs  # noqa: PLC0415
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry  # noqa: PLC0415
    real = build_runtime_catalogs(get_module_registry())
    fake_dt = _FakeDiagramTypeCatalog(module)
    return RuntimeCatalogs(
        module_catalog=real.module_catalog,
        ontology=real.ontology,
        connections=real.connections,
        diagram_types=fake_dt,  # type: ignore[arg-type]
        derivation=real.derivation,
    )


def _verifier_for(module: _ModuleWithRepoContrib) -> ArtifactVerifier:
    catalogs = _make_catalogs(module)
    return ArtifactVerifier(
        check_puml_syntax=False,
        catalogs=catalogs,
        committed_repo=_StubCommittedRepo(),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_repository_contribution_runs_once(tmp_path: Path) -> None:
    """verify_all calls repository contribution exactly once (not per diagram)."""
    contrib = _CountingRepoContribution()
    verifier = _verifier_for(_ModuleWithRepoContrib(contrib))

    verifier.verify_all(tmp_path)

    assert len(contrib.calls) == 1


def test_repository_contribution_receives_context(tmp_path: Path) -> None:
    """Contribution receives a RepositoryVerificationContext with required attributes."""
    contrib = _CountingRepoContribution()
    verifier = _verifier_for(_ModuleWithRepoContrib(contrib))

    verifier.verify_all(tmp_path)

    ctx, _ = contrib.calls[0]
    assert isinstance(ctx, RepositoryVerificationContext)
    assert ctx.committed is not None
    assert ctx.candidate is not None
    assert ctx.location == str(tmp_path)


def test_no_duplication_with_multiple_diagrams(tmp_path: Path) -> None:
    """Even with multiple diagram files present, repo contribution runs only once."""
    contrib = _CountingRepoContribution()
    verifier = _verifier_for(_ModuleWithRepoContrib(contrib))

    # Create two minimal .puml files (they'll fail basic checks but still trigger verify_all)
    (tmp_path / "a.puml").write_text("placeholder\n", encoding="utf-8")
    (tmp_path / "b.puml").write_text("placeholder\n", encoding="utf-8")

    verifier.verify_all(tmp_path, include_diagrams=True)

    assert len(contrib.calls) == 1
