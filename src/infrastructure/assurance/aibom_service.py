"""The one application entry point every AIBOM surface calls (PLAN Stream E).

Wires the pieces — shipped role bindings + repo override, per-specialization schema levels,
the pure projection, and the ML-BOM builder — into two serialized results: the model-derived
CycloneDX ML-BOM and the coverage report. REST and MCP both call these, so a request that
sees the same repo produces the same body (the parity convention). Reads the PUBLIC
architecture model only — no confidential assurance store is touched, so it is un-gated.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.application.aibom_projection import ModelReader, aibom_schema_levels, project_aibom
from src.application.aibom_role_loading import resolve_aibom_role_bindings
from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.assurance.mlbom_builder import build_mlbom
from src.ontologies.archimate_4._loader import _PACKAGE_DIR as _ARCHIMATE_DIR
from src.ontologies.archimate_4._yaml_data import load_module_aibom_roles


def _projection(search: ModelReader, repo_root: Path, catalogs: RuntimeCatalogs):
    bindings = resolve_aibom_role_bindings(repo_root, load_module_aibom_roles(_ARCHIMATE_DIR))
    required, recommended = aibom_schema_levels(repo_root, catalogs)
    return project_aibom(
        search, bindings, required_by_spec=required, recommended_by_spec=recommended
    ), bindings


def export_model_derived_aibom(
    search: ModelReader, repo_root: Path, catalogs: RuntimeCatalogs, *, notes: str = ""
) -> dict[str, Any]:
    """The CycloneDX 1.6 ML-BOM derived from the model, plus the component count and the
    coverage report (so a caller sees, in one response, what was emitted and what is missing)."""
    projection, _ = _projection(search, repo_root, catalogs)
    return {
        "bom": build_mlbom(projection.components, notes=notes),
        "component_count": len(projection.components),
        "coverage": asdict(projection.coverage),
    }


def aibom_coverage_report(
    search: ModelReader, repo_root: Path, catalogs: RuntimeCatalogs
) -> dict[str, Any]:
    """The coverage report on its own — per-component gaps (blocking vs advisory) and the
    repo-wide unbound-role findings."""
    projection, _ = _projection(search, repo_root, catalogs)
    return asdict(projection.coverage)
