"""Fetch, validate, and filter a guidance-cache source document for arch-import-guidance.
Fetching and the top-level schema live here; per-alias placement validation against the target
module is :mod:`src.domain.guidance.guidance_document`, and CLI wiring is
``src/infrastructure/cli/arch_import_guidance.py``.
"""

from __future__ import annotations

import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast
from urllib.parse import urlparse

from src.domain.guidance.guidance import GUIDANCE_FORMAT
from src.domain.guidance.guidance_document import filter_document
from src.domain.guidance.guidance_hierarchy_source import resolve_guidance_hierarchy
from src.domain.modules.module_registry import ModuleRegistry
from src.infrastructure.app_bootstrap import resolve_meta_ontology_module

_MAX_SOURCE_BYTES = 5_000_000
_FETCH_TIMEOUT_S = 10.0
# The workspace section imports to its own cache file rather than under an alias, so it reuses the
# per-alias writer under this reserved name.
WORKSPACE_ALIAS = "workspace"


class GuidanceImportError(Exception):
    """Raised for any fetch, schema, or (in --strict mode) key-validation failure."""


@dataclass(frozen=True)
class GuidanceImportSummary:
    """One meta-ontology alias's outcome, in the shape written to the provenance sidecar."""

    alias: str
    matched_keys: tuple[str, ...] = ()
    unmatched_keys: tuple[str, ...] = field(default_factory=tuple)
    filtered_document: dict[str, object] = field(default_factory=dict)


def fetch_source(source: str, *, allow_http: bool) -> bytes:
    """Fetch ``source`` (an https/http URL or local path). HTTPS-only unless ``allow_http``.

    Enforces a timeout and a size cap; never trusts a Content-Length header alone.
    """
    parsed = urlparse(source)
    if parsed.scheme in ("http", "https"):
        if parsed.scheme == "http" and not allow_http:
            raise GuidanceImportError(f"refusing plain-HTTP source {source!r} — pass --allow-http to override")
        req = urllib.request.Request(source, headers={"User-Agent": "arch-import-guidance/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_S) as resp:  # noqa: S310
                data = resp.read(_MAX_SOURCE_BYTES + 1)
        except OSError as exc:
            raise GuidanceImportError(f"failed to fetch {source!r}: {exc}") from exc
    else:
        path = Path(source)
        if not path.is_file():
            raise GuidanceImportError(f"source file not found: {source}")
        data = path.read_bytes()

    if len(data) > _MAX_SOURCE_BYTES:
        raise GuidanceImportError(f"source {source!r} exceeds the {_MAX_SOURCE_BYTES}-byte size cap")
    return data


def validate_schema(data: object) -> dict[str, object]:
    """Validate the top-level guidance-document shape; raise on anything else.

    A document must carry at least one of ``meta_ontologies`` (a mapping of per-alias guidance
    trees) or ``workspace`` (one alias-independent, workspace-scope text); either may be present
    alone.
    """
    if not isinstance(data, dict):
        raise GuidanceImportError("guidance document must be a YAML mapping")
    fmt = data.get("guidance_format")
    if fmt != GUIDANCE_FORMAT:
        raise GuidanceImportError(
            f"unsupported guidance_format {fmt!r} (expected {GUIDANCE_FORMAT}). "
            "Only the latest format is imported; migrate an already-imported older cache with "
            "`arch-repair upgrade`."
        )
    meta_ontologies = data.get("meta_ontologies")
    workspace = data.get("workspace")
    if meta_ontologies is not None and not isinstance(meta_ontologies, dict):
        raise GuidanceImportError("'meta_ontologies' must be a mapping when present")
    if workspace is not None and not isinstance(workspace, str):
        raise GuidanceImportError(
            "'workspace' must be a single guidance text (a string) when present — the workspace "
            "level has no sub-nodes to key text by"
        )
    if not isinstance(meta_ontologies, dict) and not isinstance(workspace, str):
        raise GuidanceImportError("guidance document must contain at least one of 'meta_ontologies' or 'workspace'")
    return data


def select_aliases(data: dict[str, object], module: str | None) -> dict[str, object]:
    """Return the requested alias's data, or every alias present when ``module`` is omitted.

    ``data`` must already have passed :func:`validate_schema`. ``meta_ontologies`` may be absent
    (a workspace-only document), in which case there are no aliases to import here — the workspace
    section is written separately by ``run_import``.
    """
    meta_ontologies = cast(dict[str, object], data.get("meta_ontologies") or {})
    if module is None:
        return meta_ontologies
    if module not in meta_ontologies:
        raise GuidanceImportError(f"module alias {module!r} not present in source document")
    return {module: meta_ontologies[module]}


def filter_workspace_section(workspace_data: object, *, strict: bool) -> GuidanceImportSummary:
    """Validate the top-level ``workspace:`` text. There is no module to validate it against — the
    workspace level sits above every meta-ontology — so the only rule is that it says something.

    Returns a summary whose ``filtered_document`` is the workspace cache to write
    (``alias="workspace"`` so the standard cache/sidecar writer targets ``workspace.guidance.yaml``);
    ``--strict`` aborts on a blank text rather than writing an empty cache.
    """
    context = workspace_data.strip() if isinstance(workspace_data, str) else ""
    if not context:
        if strict:
            raise GuidanceImportError("workspace guidance is empty (--strict)")
        return GuidanceImportSummary(
            alias=WORKSPACE_ALIAS,
            unmatched_keys=(WORKSPACE_ALIAS,),
            filtered_document={"guidance_format": GUIDANCE_FORMAT, "workspace": ""},
        )
    return GuidanceImportSummary(
        alias=WORKSPACE_ALIAS,
        matched_keys=(WORKSPACE_ALIAS,),
        filtered_document={"guidance_format": GUIDANCE_FORMAT, "workspace": context},
    )


def filter_alias_document(
    alias: str, alias_data: object, registry: ModuleRegistry, *, strict: bool
) -> GuidanceImportSummary:
    """Validate one alias's guidance tree against the active registry's module: every node must be
    a declared node of the level below its parent, every entity type must sit under the node the
    module declares as its parent, connection types must sit at the root, and every specialization
    slug must exist in the module's catalog.

    Unknown or misplaced keys are listed and dropped from the filtered document, unless ``strict``
    is set, in which case any one of them aborts the whole import.
    """
    om = resolve_meta_ontology_module(alias, registry)
    if om is None:
        raise GuidanceImportError(f"module alias {alias!r} is not a registered, active ontology")
    if not isinstance(alias_data, dict):
        raise GuidanceImportError(f"guidance entry for {alias!r} must be a mapping")

    filtered = filter_document(om, resolve_guidance_hierarchy(om, alias=alias), alias_data, alias=alias)
    if filtered.unmatched and strict:
        raise GuidanceImportError(f"unknown guidance keys for {alias!r} (--strict): {sorted(filtered.unmatched)}")

    return GuidanceImportSummary(
        alias=alias,
        matched_keys=tuple(filtered.matched),
        unmatched_keys=tuple(filtered.unmatched),
        filtered_document={
            "guidance_format": GUIDANCE_FORMAT,
            "meta_ontologies": {alias: filtered.content},
        },
    )
