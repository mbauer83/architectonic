"""Per-diagram and repository contribution dispatch, separated from ArtifactVerifier."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.application.verification import (
    _orphan_attachment_schema_rule,  # noqa: F401  # ensure W044 registered
    _workspace_identity_rules,  # noqa: F401  # ensure E335 registered
)
from src.application.verification.artifact_verifier_types import VerificationResult


class RegistryOnlyCandidateRepository:
    """Point-lookup CandidateRepository backed by VerifierStorePort; list_* returns []."""

    def __init__(self, store: object) -> None:
        self._store = store

    def get_entity(self, artifact_id: str) -> object:
        return self._store.get_entity(artifact_id)  # type: ignore[attr-defined]

    def get_diagram(self, artifact_id: str) -> object:
        return self._store.get_diagram(artifact_id)  # type: ignore[attr-defined]

    def list_entities(self, *, artifact_type: str | None = None, domain: str | None = None, status: str | None = None) -> list:  # noqa: E501
        return []

    def list_diagrams(self, *, diagram_type: str | None = None, status: str | None = None) -> list:
        return []

    def scope_for_path(self, path: Path) -> str:
        return self._store.scope_for_path(path)  # type: ignore[attr-defined]


def workspace_types_from_catalogs(catalogs: Any) -> dict[str, frozenset[str]]:
    """Return {diagram_type_name: frozenset[entity_type]} for workspace-scoped entity types."""
    result: dict[str, frozenset[str]] = {}
    for name, mod in catalogs.diagram_types.all_diagram_types().items():
        ws = frozenset(
            oe.entity_type for oe in mod.ui_config.diagram_only_types if oe.identity_scope == "workspace"
        )
        if ws:
            result[str(name)] = ws
    return result


def build_candidate_repo(committed_repo_arg: object | None, registry: Any) -> object | None:
    if committed_repo_arg is not None:
        return committed_repo_arg
    if registry is not None:
        return RegistryOnlyCandidateRepository(registry._store)
    return None


def run_diagram_contributions(
    *,
    module: Any,
    candidate: Any,
    fm: dict,
    content: str,
    registry: Any,
    scope: str,
    runtime_catalogs: Any,
    result: VerificationResult,
    loc: str,
) -> None:
    from src.domain.diagrams.diagram_verification import BaseDiagramVerificationContext  # noqa: PLC0415
    from src.domain.repository.frontmatter import body_after_frontmatter  # noqa: PLC0415

    allowed_conns = (
        frozenset(registry.enterprise_connection_ids())
        if scope == "enterprise"
        else frozenset(registry.connection_ids())
    )
    allowed_ents = (
        frozenset(registry.enterprise_entity_ids())
        if scope == "enterprise"
        else frozenset(registry.entity_ids())
    )
    ctx = BaseDiagramVerificationContext(
        fm=fm,
        loc=loc,
        scope=scope,  # type: ignore[arg-type]
        diagram_id=str(fm.get("artifact-id", "")),
        allowed_connections=allowed_conns,
        allowed_entities=allowed_ents,
        catalogs=runtime_catalogs,
        type_references_blocking=getattr(runtime_catalogs, "datatype_type_references_blocking", True),
        body=body_after_frontmatter(content),
    )
    for contribution in module.diagram_verification_contributions():
        contribution.run(candidate, ctx, result)


def run_repository_contributions(
    *,
    candidate: Any,
    runtime_catalogs: Any,
    repo_path: Path,
    committed: Any = None,
) -> VerificationResult | None:
    if candidate is None or runtime_catalogs is None:
        return None
    from src.domain.diagrams.diagram_verification import (  # noqa: PLC0415
        RepositoryVerificationContext,
        get_generic_repository_contributions,
    )

    ctx = RepositoryVerificationContext(
        committed=committed if committed is not None else candidate,
        candidate=candidate,
        location=str(repo_path),
        catalogs=runtime_catalogs,
        type_references_blocking=getattr(runtime_catalogs, "datatype_type_references_blocking", True),
    )
    result = VerificationResult(path=repo_path, file_type="diagram")
    for contrib in get_generic_repository_contributions():
        contrib.run(ctx, result)
    for mod in runtime_catalogs.diagram_types.all_diagram_types().values():
        for contrib in mod.repository_verification_contributions():
            contrib.run(ctx, result)
    return result if result.issues else None
