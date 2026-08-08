"""ERP v2.0 model verification facade with modular helper backends."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Literal

from src.application.entity_type_predicates import is_internal_entity_type
from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.verification._verifier_contribution_runner import (
    build_candidate_repo,
    run_diagram_contributions,
    run_repository_contributions,
)
from src.application.verification._verifier_document import verify_document
from src.application.verification._verifier_incremental_pass import (
    IncrementalPassContext,
    run_incremental_pass,
)
from src.application.verification._verifier_inventory import FileInventory, expand_impacted_paths
from src.application.verification._verifier_outgoing import verify_outgoing
from src.application.verification._verifier_pass_planning import (
    count_verifiable_files,
    pending_full_pass_reason,
)
from src.application.verification._verifier_rules_diagram_references import check_diagram_references_scoped
from src.application.verification._verifier_rules_edge_labels import check_edge_label_overrides
from src.application.verification._verifier_rules_grf import check_global_artifact_reference
from src.application.verification._verifier_rules_puml_completeness import check_puml_relation_rules
from src.application.verification._verifier_rules_schema import (
    check_attribute_schema,
    check_frontmatter_schema,
    check_module_source_path,
)
from src.application.verification._verifier_rules_specialization import check_entity_specialization
from src.application.verification._verifier_rules_viewpoint import check_viewpoint_for_diagram_type
from src.application.verification.artifact_verifier_incremental import (
    load_runtime_config,
)
from src.application.verification.artifact_verifier_parsing import (
    parse_frontmatter,
    parse_puml_frontmatter,
    read_file,
)
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.verification.artifact_verifier_rules import (
    check_artifact_id_entity,
    check_artifact_type,
    check_diagram_artifact_type,
    check_enum,
    check_matrix_markdown_shape,
    check_puml_structure,
    check_required_fields,
    check_section,
)
from src.application.verification.artifact_verifier_types import (
    DIAGRAM_REQUIRED,
    ENTITY_REQUIRED,
    VALID_STATUSES,
    Issue,
    Severity,
    VerificationResult,
    VerifierRuntimeConfig,
    entity_id_from_path,
)
from src.application.verification.verifier_ports import (
    FileInventoryPort,
    IncrementalStatePort,
    PumlSyntaxPort,
    VerifierScheduler,
)
from src.application.viewpoints.registry_snapshot import build_registry_snapshot as registry_snapshot


class ArtifactVerifier:
    def __init__(
        self,
        registry: ArtifactRegistry | None = None,
        *,
        check_puml_syntax: bool = True,
        catalogs: RuntimeCatalogs | None = None,
        committed_repo: object | None = None,
        puml_syntax: PumlSyntaxPort | None = None,
        scheduler: VerifierScheduler | None = None,
        file_inventory: FileInventoryPort | None = None,
        incremental_state: IncrementalStatePort | None = None,
    ) -> None:
        self.registry = registry
        self.check_puml_syntax = check_puml_syntax
        self._catalogs = catalogs
        self._candidate_repo: object | None = build_candidate_repo(committed_repo, registry)
        self._puml_port = puml_syntax
        self._scheduler_port = scheduler
        self._inventory_port = file_inventory
        self._incremental_port = incremental_state

    @functools.cached_property
    def _runtime_catalogs(self) -> RuntimeCatalogs:
        if self._catalogs is None:
            raise RuntimeError("ArtifactVerifier requires catalogs from process_runtime_catalogs()")
        return self._catalogs

    @functools.cached_property
    def _puml_syntax(self) -> PumlSyntaxPort:
        if self._puml_port is not None:
            return self._puml_port
        from src.application.verification._verifier_stdlib_adapters import _NullPumlSyntax  # noqa: PLC0415

        return _NullPumlSyntax()

    @functools.cached_property
    def _scheduler(self) -> VerifierScheduler:
        if self._scheduler_port is not None:
            return self._scheduler_port
        from src.application.verification._verifier_stdlib_adapters import ThreadPoolVerifierScheduler  # noqa: PLC0415

        return ThreadPoolVerifierScheduler()

    @functools.cached_property
    def _inventory(self) -> FileInventoryPort:
        if self._inventory_port is not None:
            return self._inventory_port
        from src.application.verification._verifier_stdlib_adapters import FilesystemInventoryAdapter  # noqa: PLC0415

        return FilesystemInventoryAdapter()

    @functools.cached_property
    def _registry_snapshot(self):
        return registry_snapshot(self._runtime_catalogs, () if self.registry is None else self.registry.repo_roots)

    @functools.cached_property
    def _incremental(self) -> IncrementalStatePort:
        if self._incremental_port is not None:
            return self._incremental_port
        from src.application.verification._verifier_stdlib_adapters import (
            DefaultIncrementalStateAdapter,  # noqa: PLC0415
        )

        return DefaultIncrementalStateAdapter()

    def _repo_root_for_path(self, path: Path) -> Path | None:
        if self.registry is None:
            return None
        resolved = path.resolve()
        for root in self.registry.repo_roots:
            try:
                resolved.relative_to(root)
                return root
            except ValueError:
                continue
        return None

    def verify_entity_file(self, path: Path, *, schema_repo_root: Path | None = None) -> VerificationResult:
        result = VerificationResult(path=path, file_type="entity")
        loc = str(path)
        content = read_file(path, result, loc)
        if content is None:
            return result
        fm = parse_frontmatter(content, result, loc)
        if fm is None:
            return result

        check_required_fields(fm, ENTITY_REQUIRED, result, loc)
        check_artifact_id_entity(fm, result, loc)
        check_artifact_type(fm, self._runtime_catalogs.ontology.all_entity_type_names(), "entity type", result, loc)
        check_entity_specialization(fm, self._runtime_catalogs.specializations, result, loc)
        check_enum(fm, "status", VALID_STATUSES, result, loc)
        check_section(content, "§content", required=True, result=result, loc=loc)
        check_section(content, "§display", required=True, result=result, loc=loc)

        if is_internal_entity_type(str(fm.get("artifact-type", "")), self._runtime_catalogs.ontology):
            check_global_artifact_reference(fm, self.registry, result, loc)

        # Schema validation keys off the *governing* repo (its ``.arch-repo/schemata``),
        # which the caller supplies when verifying proposed content in a temp path. Falling
        # back to the file's on-disk location keeps in-repo verification unchanged.
        repo_root = schema_repo_root if schema_repo_root is not None else self._repo_root_for_path(path)
        if repo_root is not None:
            check_frontmatter_schema(fm, repo_root, "entity", result, loc)
            check_attribute_schema(content, fm, repo_root, result, loc,
                specialization_catalog=self._runtime_catalogs.specializations,
                profile_registry=self._runtime_catalogs.profiles)

        check_module_source_path(content, path, result, loc)

        return result

    def verify_outgoing_file(self, path: Path) -> VerificationResult:
        return verify_outgoing(
            path, registry=self.registry, catalogs=self._runtime_catalogs,
            scope=self._scope_for_path(path), repo_root=self._repo_root_for_path(path),
        )

    def verify_connection_file(self, path: Path) -> VerificationResult:
        if path.name.endswith(".outgoing.md"):
            return self.verify_outgoing_file(path)
        result = VerificationResult(path=path, file_type="connection")
        loc = str(path)
        content = read_file(path, result, loc)
        if content is None:
            return result
        fm = parse_frontmatter(content, result, loc)
        if fm is None:
            return result
        check_enum(fm, "status", VALID_STATUSES, result, loc)
        check_section(content, "§display", required=True, result=result, loc=loc)
        return result

    def verify_diagram_file(self, path: Path) -> VerificationResult:
        return self._verify_diagram_file(path, run_syntax_check=self.check_puml_syntax)

    def _verify_diagram_file(self, path: Path, *, run_syntax_check: bool) -> VerificationResult:
        result = VerificationResult(path=path, file_type="diagram")
        loc = str(path)
        content = read_file(path, result, loc)
        if content is None:
            return result
        fm = parse_puml_frontmatter(content, result, loc)
        if fm is None:
            return result

        check_required_fields(fm, DIAGRAM_REQUIRED, result, loc)
        check_diagram_artifact_type(fm, result, loc)
        check_enum(fm, "status", VALID_STATUSES, result, loc)

        scope = self._scope_for_path(path)
        if self.registry is not None:
            check_diagram_references_scoped(
                fm, self.registry, scope, result, loc,
                diagram_type_catalog=self._runtime_catalogs.diagram_types,
                derivation_catalog=self._runtime_catalogs.derivation)
            check_puml_relation_rules(
                content, fm, self.registry, scope, result, loc,
                runtime_catalogs=self._runtime_catalogs)
            module = check_viewpoint_for_diagram_type(
                fm, target_kind="diagram", runtime_catalogs=self._runtime_catalogs,
                registry=self.registry, registry_snapshot=self._registry_snapshot, result=result, loc=loc)
            candidate = self._candidate_repo
            if candidate is not None and module is not None:
                run_diagram_contributions(
                    module=module, candidate=candidate, fm=fm, registry=self.registry,
                    scope=scope, runtime_catalogs=self._runtime_catalogs, result=result, loc=loc,
                )
        else:
            result.issues.append(Issue(
                Severity.WARNING, "W002",
                "No ArtifactRegistry provided; entity/connection reference checks skipped", loc,
            ))

        check_puml_structure(content, fm, result, loc)
        check_edge_label_overrides(content, fm, result, loc)

        repo_root = self._repo_root_for_path(path)
        if repo_root is not None:
            check_frontmatter_schema(fm, repo_root, "diagram", result, loc)

        if run_syntax_check:
            result.issues.extend(self._puml_syntax.check_one(path, loc))
        return result

    def verify_matrix_diagram_file(self, path: Path) -> VerificationResult:
        result = VerificationResult(path=path, file_type="diagram")
        loc = str(path)
        content = read_file(path, result, loc)
        if content is None:
            return result
        fm = parse_frontmatter(content, result, loc)
        if fm is None:
            return result

        check_required_fields(fm, DIAGRAM_REQUIRED, result, loc)
        check_diagram_artifact_type(fm, result, loc)
        check_enum(fm, "status", VALID_STATUSES, result, loc)

        scope = self._scope_for_path(path)
        if self.registry is not None:
            check_diagram_references_scoped(
                fm, self.registry, scope, result, loc,
                diagram_type_catalog=self._runtime_catalogs.diagram_types,
                derivation_catalog=self._runtime_catalogs.derivation,
            )
            check_viewpoint_for_diagram_type(
                fm, target_kind="matrix", runtime_catalogs=self._runtime_catalogs,
                registry=self.registry, registry_snapshot=self._registry_snapshot, result=result, loc=loc)
        else:
            result.issues.append(Issue(
                Severity.WARNING, "W002",
                "No ArtifactRegistry provided; entity/connection reference checks skipped", loc,
            ))

        check_matrix_markdown_shape(fm, content, result, loc)
        return result

    def verify_all(self, repo_path: Path, *, include_diagrams: bool = True) -> list[VerificationResult]:
        return self.verify_all_reporting_pass_mode(repo_path, include_diagrams=include_diagrams)[1]

    def pending_full_pass_reason(self, repo_path: Path, *, include_diagrams: bool = True) -> str | None:
        return pending_full_pass_reason(
            incremental=self._incremental,
            has_registry=self.registry is not None,
            repo_path=repo_path,
            include_diagrams=include_diagrams,
        )

    def count_verifiable_files(self, repo_path: Path, *, include_diagrams: bool = True) -> int:
        return count_verifiable_files(
            inventory=self._inventory, repo_path=repo_path, include_diagrams=include_diagrams
        )

    def verify_all_reporting_pass_mode(
        self, repo_path: Path, *, include_diagrams: bool = True
    ) -> tuple[str, list[VerificationResult]]:
        """Verify everything, and say which pass produced the answer.

        `full` re-verifies every file and takes minutes on a cold cache;
        `incremental-cached` returns a stored answer in seconds. Returned rather than held
        on the instance: verifiers are cached per repository-root set and shared between
        concurrent requests, so an attribute would report another request's pass.
        """
        cfg = load_runtime_config()
        if cfg.mode == "incremental":
            return self._verify_all_incremental(repo_path, include_diagrams=include_diagrams, cfg=cfg)
        return "full", self._verify_all_full(repo_path, include_diagrams=include_diagrams)

    def verify_paths(
        self,
        repo_path: Path,
        *,
        changed_paths: list[Path],
        verification_scope: Literal["changed", "impacted", "full"] = "impacted",
        include_diagrams: bool = True,
    ) -> list[VerificationResult]:
        if verification_scope == "full":
            return self._verify_all_full(repo_path, include_diagrams=include_diagrams)

        inv = self._inventory.build(repo_path, include_diagrams=include_diagrams)
        relpaths = {inv.path_to_rel[path.resolve()] for path in changed_paths if path.resolve() in inv.path_to_rel}
        if not relpaths:
            return []

        selected = relpaths if verification_scope == "changed" else expand_impacted_paths(inv, relpaths)
        results = self._verify_inventory_subset(inv, selected)

        doc_files = self._inventory.filter_doc_files(repo_path, list(changed_paths))
        results.extend(self._scheduler.run(self.verify_document_file, doc_files))
        return results

    def _verify_all_full(self, repo_path: Path, *, include_diagrams: bool) -> list[VerificationResult]:
        inv = self._inventory.build(repo_path, include_diagrams=include_diagrams)
        results = self._verify_inventory_subset(inv, set(inv.ordered_paths))
        doc_files = self._inventory.list_doc_files(repo_path)
        results.extend(self._scheduler.run(self.verify_document_file, doc_files))
        repo_result = run_repository_contributions(
            candidate=self._candidate_repo, runtime_catalogs=self._catalogs, repo_path=repo_path
        )
        if repo_result is not None:
            results.append(repo_result)
        return results

    def _verify_all_incremental(
        self,
        repo_path: Path,
        *,
        include_diagrams: bool,
        cfg: VerifierRuntimeConfig,
    ) -> tuple[str, list[VerificationResult]]:
        return run_incremental_pass(
            IncrementalPassContext(
                inventory=self._inventory,
                incremental=self._incremental,
                has_registry=self.registry is not None,
                verify_full=self._verify_all_full,
                verify_subset=self._verify_inventory_subset,
                verify_documents=self._verify_documents,
            ),
            repo_path,
            include_diagrams=include_diagrams,
            cfg=cfg,
        )

    def _verify_documents(self, repo_path: Path) -> list[VerificationResult]:
        return self._scheduler.run(self.verify_document_file, self._inventory.list_doc_files(repo_path))

    def _verify_inventory_subset(self, inv: FileInventory, relpaths: set[str]) -> list[VerificationResult]:
        if self.registry is not None:
            _ = self.registry.entity_ids()
            _ = self.registry.connection_ids()
        entity_files = [inv.rel_to_path[r] for r in inv.entity_relpaths if r in relpaths]
        connection_files = [inv.rel_to_path[r] for r in inv.connection_relpaths if r in relpaths]
        diagram_files = [inv.rel_to_path[r] for r in inv.diagram_puml_relpaths if r in relpaths]
        matrix_files = [inv.rel_to_path[r] for r in inv.diagram_matrix_relpaths if r in relpaths]

        out: list[VerificationResult] = []
        out.extend(self._scheduler.run(self.verify_entity_file, entity_files))
        out.extend(self._scheduler.run(self.verify_connection_file, connection_files))

        diagram_results = self._scheduler.run(
            lambda path: self._verify_diagram_file(path, run_syntax_check=False),
            diagram_files,
            max_workers=4,
        )
        if self.check_puml_syntax and diagram_results:
            issues_by_path = self._puml_syntax.check_batch([r.path for r in diagram_results])
            for d in diagram_results:
                d.issues.extend(issues_by_path.get(d.path, []))
        out.extend(diagram_results)
        out.extend(self._scheduler.run(self.verify_matrix_diagram_file, matrix_files))

        by_path = {r.path: r for r in out}
        return [
            by_path[inv.rel_to_path[r]] for r in inv.ordered_paths if r in relpaths and inv.rel_to_path[r] in by_path
        ]

    def verify_document_file(self, path: Path) -> VerificationResult:
        return verify_document(path, registry=self.registry, catalogs=self._runtime_catalogs)

    def _scope_for_path(self, path: Path) -> Literal["enterprise", "engagement", "unknown"]:
        if self.registry is not None:
            return self.registry.scope_for_path(path)
        from src.domain.repository.repo_scope import infer_repo_scope  # noqa: PLC0415

        return infer_repo_scope(path)


__all__ = [
    "ArtifactRegistry",
    "ArtifactVerifier",
    "Issue",
    "Severity",
    "VerificationResult",
    "entity_id_from_path",
]
