"""Verification logic for diagram files — the PlantUML form and the matrix form.

The two share a spine (frontmatter, required fields, artifact type, status, scoped references,
viewpoint) and diverge only in what a body means: PlantUML has relation rules, structure and edge
labels; a matrix has a markdown table shape. Separated from the verifier facade for the same reason
documents and outgoing files already are — a facade should dispatch to rules, not hold them.

Their collaborators arrive as one context rather than seven parameters: a function needing seven
things from its caller is a function whose context has not been named.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.verification._verifier_contribution_runner import run_diagram_contributions
from src.application.verification._verifier_rules_diagram_references import check_diagram_references_scoped
from src.application.verification._verifier_rules_edge_labels import check_edge_label_overrides
from src.application.verification._verifier_rules_puml_completeness import check_puml_relation_rules
from src.application.verification._verifier_rules_puml_declarations import check_puml_alias_declarations
from src.application.verification._verifier_rules_schema import check_frontmatter_schema
from src.application.verification._verifier_rules_viewpoint import check_viewpoint_for_diagram_type
from src.application.verification.artifact_verifier_parsing import (
    parse_frontmatter,
    parse_puml_frontmatter,
    read_file,
)
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.verification.artifact_verifier_rules import (
    check_diagram_artifact_type,
    check_enum,
    check_internal_links,
    check_matrix_markdown_shape,
    check_puml_structure,
    check_required_fields,
)
from src.application.verification.artifact_verifier_types import (
    DIAGRAM_REQUIRED,
    VALID_STATUSES,
    Issue,
    Severity,
    VerificationResult,
)
from src.application.verification.verifier_ports import PumlSyntaxPort
from src.application.viewpoints.registry_snapshot import RegistrySnapshot

if TYPE_CHECKING:
    from src.application.verification._verifier_snapshot import RepositorySnapshot

RepoScope = Literal["enterprise", "engagement", "unknown"]

@dataclass(frozen=True)
class DiagramRuleContext:
    """What a diagram rule needs from the verifier that owns it."""

    registry: ArtifactRegistry | None
    catalogs: RuntimeCatalogs
    registry_snapshot: RegistrySnapshot
    candidate_repo: object
    puml_syntax: PumlSyntaxPort
    scope_for_path: Callable[[Path], RepoScope]
    repo_root_for_path: Callable[[Path], Path | None]


def _check_common_header(fm: dict[str, Any], result: VerificationResult, loc: str) -> None:
    check_required_fields(fm, DIAGRAM_REQUIRED, result, loc)
    check_diagram_artifact_type(fm, result, loc)
    check_enum(fm, "status", VALID_STATUSES, result, loc)


def _check_scoped_references(
    ctx: DiagramRuleContext, fm: dict[str, Any], scope: RepoScope, result: VerificationResult, loc: str
) -> None:
    assert ctx.registry is not None
    check_diagram_references_scoped(
        fm,
        ctx.registry,
        scope,
        result,
        loc,
        diagram_type_catalog=ctx.catalogs.diagram_types,
        derivation_catalog=ctx.catalogs.derivation,
    )


def _no_registry_issue(loc: str) -> Issue:
    return Issue(
        Severity.WARNING, "W002", "No ArtifactRegistry provided; entity/connection reference checks skipped", loc
    )


def verify_diagram(
    path: Path,
    ctx: DiagramRuleContext,
    *,
    run_syntax_check: bool,
    snapshot: RepositorySnapshot | None = None,
) -> VerificationResult:
    """Verify a PlantUML diagram file."""
    result = VerificationResult(path=path, file_type="diagram")
    loc = str(path)
    content = read_file(path, result, loc, snapshot=snapshot)
    if content is None:
        return result
    fm = parse_puml_frontmatter(content, result, loc)
    if fm is None:
        return result

    _check_common_header(fm, result, loc)
    scope = ctx.scope_for_path(path)
    if ctx.registry is not None:
        _check_scoped_references(ctx, fm, scope, result, loc)
        check_puml_relation_rules(
            content, fm, ctx.registry, scope, result, loc, runtime_catalogs=ctx.catalogs
        )
        module = check_viewpoint_for_diagram_type(
            fm,
            target_kind="diagram",
            runtime_catalogs=ctx.catalogs,
            registry=ctx.registry,
            registry_snapshot=ctx.registry_snapshot,
            result=result,
            loc=loc,
        )
        if ctx.candidate_repo is not None and module is not None:
            run_diagram_contributions(
                module=module,
                candidate=ctx.candidate_repo,
                fm=fm,
                content=content,
                registry=ctx.registry,
                scope=scope,
                runtime_catalogs=ctx.catalogs,
                result=result,
                loc=loc,
            )
    else:
        result.issues.append(_no_registry_issue(loc))

    check_puml_structure(content, fm, result, loc)
    check_puml_alias_declarations(content, fm, result, loc, diagram_type_catalog=ctx.catalogs.diagram_types)
    check_edge_label_overrides(content, fm, result, loc)

    repo_root = ctx.repo_root_for_path(path)
    if repo_root is not None:
        check_frontmatter_schema(fm, repo_root, "diagram", result, loc)

    if run_syntax_check:
        result.issues.extend(ctx.puml_syntax.check_one(path, loc))
    return result


def verify_matrix_diagram(
    path: Path, ctx: DiagramRuleContext, *, snapshot: RepositorySnapshot | None = None
) -> VerificationResult:
    """Verify a matrix diagram file, whose body is a markdown table rather than PlantUML."""
    result = VerificationResult(path=path, file_type="diagram")
    loc = str(path)
    content = read_file(path, result, loc, snapshot=snapshot)
    if content is None:
        return result
    fm = parse_frontmatter(content, result, loc)
    if fm is None:
        return result

    _check_common_header(fm, result, loc)
    scope = ctx.scope_for_path(path)
    if ctx.registry is not None:
        _check_scoped_references(ctx, fm, scope, result, loc)
        check_viewpoint_for_diagram_type(
            fm,
            target_kind="matrix",
            runtime_catalogs=ctx.catalogs,
            registry=ctx.registry,
            registry_snapshot=ctx.registry_snapshot,
            result=result,
            loc=loc,
        )
    else:
        result.issues.append(_no_registry_issue(loc))

    check_matrix_markdown_shape(fm, content, result, loc)
    # A matrix body is prose: a table whose cells are markdown links to the elements it relates.
    # The rule that finds a link pointing at nothing had only ever been asked about documents, and
    # every dangling link in this repository was in a matrix — 57 of them, left behind when the
    # model moved under `projects/<slug>/`. Same fact, same code, a second kind of file.
    check_internal_links(content, path, result, loc)
    return result
