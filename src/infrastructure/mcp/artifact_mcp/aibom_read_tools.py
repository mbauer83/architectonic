"""Model-derived AIBOM read tools on arch-repo-read (PLAN Stream E / WU-E1).

These are ARCHITECTURE reads — they derive the ML-BOM and its coverage from the public model
(entities carrying AI specializations + their relations), touching no confidential assurance
store. They live on arch-repo-read, not the assurance MCP, for the same reason the plan put
*marking* on arch-repo-write: it is an architecture operation. Both share the one application
service the REST endpoints call, so a request seeing the same repo yields the same body.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.infrastructure.mcp.artifact_mcp.context import repo_cached, resolve_repo_roots, roots_key
from src.infrastructure.mcp.artifact_mcp.tool_annotations import READ_ONLY


def _catalogs():
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry  # noqa: PLC0415

    return build_runtime_catalogs(get_module_registry())


def register_aibom_read_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        name="artifact_aibom_export",
        title="Artifact AIBOM: Export ML-BOM",
        description=(
            "Emit a CycloneDX 1.6 ML-BOM DERIVED from the architecture model: every entity "
            "carrying an AI specialization (ai-model, ai-agent, ai-inference-service, "
            "ai-dataset, ai-prompt-asset, ai-vector-store, ai-runtime, ai-tool-interface) "
            "becomes a component, with its authored model card, dataset/governance links "
            "resolved from connections, and a dependency graph between AI components. The "
            "model is the source of truth — no component list is passed in. The response also "
            "carries the coverage report. Seal the emitted BOM via assurance_seal_baseline."
        ),
        annotations=READ_ONLY,
        structured_output=True,
    )
    def artifact_aibom_export(*, notes: str = "", repo_root: str | None = None) -> dict[str, object]:
        from src.infrastructure.assurance.aibom_service import export_model_derived_aibom  # noqa: PLC0415

        roots = resolve_repo_roots(repo_scope="engagement", repo_root=repo_root, repo_preset=None, enterprise_root=None)
        return export_model_derived_aibom(repo_cached(roots_key(roots)), roots[0], _catalogs(), notes=notes)

    @mcp.tool(
        name="artifact_aibom_coverage",
        title="Artifact AIBOM: Coverage",
        description=(
            "Per-AI-component AIBOM coverage over the architecture model: blocking gaps "
            "(missing required attributes, missing dataset linkage, missing governance edge) "
            "vs advisory gaps (missing recommended attributes), plus repo-wide derivation "
            "roles that no connection type is bound to. Answers 'what is missing for a valid "
            "AIBOM' without emitting the document."
        ),
        annotations=READ_ONLY,
        structured_output=True,
    )
    def artifact_aibom_coverage(*, repo_root: str | None = None) -> dict[str, object]:
        from src.infrastructure.assurance.aibom_service import aibom_coverage_report  # noqa: PLC0415

        roots = resolve_repo_roots(repo_scope="engagement", repo_root=repo_root, repo_preset=None, enterprise_root=None)
        return aibom_coverage_report(repo_cached(roots_key(roots)), roots[0], _catalogs())
