"""Stamp the persisted ``selection_mode`` onto pre-change viewpoint definitions.

Scope and query are ALTERNATIVE selection mechanisms; exactly one is active. Pre-change
definitions carry no mode, so this step stamps one mechanically wherever the layers
cannot disagree: scope-only → ``scope``; query-only and dual-EQUIVALENT (the query is the
scope's mechanical translation) → ``query``. A dual-DIVERGENT definition selects two
different populations, so its mode is never guessed: the operator states it with
``--resolve-selection <slug>=scope|query`` (a resolution writes ONLY ``selection_mode``,
never a semantic conversion of either layer). Any divergent definition left unresolved
makes the whole commit run exit with the distinct unresolved-migration status and write
nothing anywhere (``blocks_commit``). Re-running on a migrated deployment is a no-op.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Literal

import yaml  # type: ignore[import-untyped]

from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding
from src.domain.viewpoints.viewpoint_parsing import viewpoint_catalog_from_mapping
from src.domain.viewpoints.viewpoint_scope_query import classify_selection_layers
from src.domain.viewpoints.viewpoint_serialization import viewpoint_catalog_to_mapping
from src.domain.viewpoints.viewpoint_summary import render_query_summary
from src.domain.viewpoints.viewpoints import ViewpointCatalog, ViewpointDefinition
from src.domain.yaml_documents import parse_yaml

_PATH = ".arch-repo/viewpoints.yaml"

SelectionMode = Literal["scope", "query"]


def _parsed_catalog(view: RepoUpgradeView) -> ViewpointCatalog | None:
    content = view.read_text(_PATH)
    if content is None:
        return None
    try:
        loaded: object = parse_yaml(content) or {}
        if not isinstance(loaded, Mapping):
            return None
        return viewpoint_catalog_from_mapping(loaded)
    except Exception:  # noqa: BLE001 — a malformed file is the declaration scan step's finding
        return None


def _mechanical_mode(definition: ViewpointDefinition) -> SelectionMode | None:
    """The mode a definition can be stamped with WITHOUT choosing between disagreeing
    populations — ``None`` for the dual-divergent class, which needs an explicit choice."""
    layer_class = classify_selection_layers(definition)
    if layer_class == "scope-only":
        return "scope"
    if layer_class in ("query-only", "dual-equivalent"):
        return "query"
    return None


def _both_populations(definition: ViewpointDefinition) -> str:
    scope_types = (
        ", ".join(sorted(definition.scope.entity_types)) if definition.scope.entity_types is not None else "(all types)"
    )
    query_text = render_query_summary(definition.query) if definition.query is not None else "(no query)"
    return f"scope selects [{scope_types}]; query selects: {query_text}"


class ViewpointSelectionModeStampStep:
    id = "viewpoint-selection-mode-stamp"
    version = 1
    description = f"Stamp the active selection_mode (scope|query) on definitions in {_PATH}"
    scanned_surface: ScannedSurface = "customizations"

    def __init__(self, resolutions: Mapping[str, SelectionMode] | None = None) -> None:
        self._resolutions: dict[str, SelectionMode] = dict(resolutions or {})

    def _stamped_mode(self, definition: ViewpointDefinition) -> SelectionMode | None:
        resolved = self._resolutions.get(definition.slug)
        return resolved if resolved is not None else _mechanical_mode(definition)

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        catalog = _parsed_catalog(view)
        if catalog is None:
            return []
        findings: list[UpgradeFinding] = []
        for definition in catalog.entries:
            if definition.selection_mode is not None:
                continue
            mode = self._stamped_mode(definition)
            if mode is None:
                findings.append(
                    UpgradeFinding(
                        step_id=self.id,
                        finding_id=f"unresolved-selection:{definition.slug}",
                        location=_PATH,
                        description=(
                            f"viewpoint '{definition.slug}' carries DIVERGENT scope and query layers — "
                            f"{_both_populations(definition)} — and no --resolve-selection choice was supplied"
                        ),
                        severity="error",
                        auto_migratable=False,
                        manual_instructions=(
                            f"re-run with --resolve-selection {definition.slug}=scope or "
                            f"--resolve-selection {definition.slug}=query (writes ONLY selection_mode)"
                        ),
                        blocks_commit=True,
                    )
                )
                continue
            resolved_note = " (operator-resolved)" if definition.slug in self._resolutions else ""
            findings.append(
                UpgradeFinding(
                    step_id=self.id,
                    finding_id=f"selection-mode:{definition.slug}",
                    location=_PATH,
                    description=(
                        f"viewpoint '{definition.slug}' predates selection modes; its active layer is "
                        f"mode '{mode}'{resolved_note}"
                    ),
                    severity="warning",
                    auto_migratable=True,
                    rewrite_summary=f"stamp selection_mode: {mode} — no layer is semantically converted",
                )
            )
        return findings

    def apply(
        self,
        view: RepoUpgradeView,
        writer: RepoUpgradeWriter,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        catalog = _parsed_catalog(view)
        if catalog is None:
            return [
                AppliedFinding(finding=finding, outcome="error", detail="file no longer parses")
                for finding in findings
            ]
        stamped: list[ViewpointDefinition] = []
        for definition in catalog.entries:
            if definition.selection_mode is not None:
                stamped.append(definition)
                continue
            mode = self._stamped_mode(definition)
            if mode is None:
                # A divergent definition without a resolution: the workspace-level gate
                # exits before apply ever runs, so reaching this means the gate was
                # bypassed — refuse the whole file rather than write a partial stamp.
                return [
                    AppliedFinding(
                        finding=finding, outcome="error", detail="unresolved divergent definition present"
                    )
                    for finding in findings
                ]
            stamped.append(_with_mode(definition, mode))
        mapping = viewpoint_catalog_to_mapping(ViewpointCatalog(entries=tuple(stamped)))
        writer.write_text(_PATH, str(yaml.safe_dump(mapping, sort_keys=False)))
        return [AppliedFinding(finding=finding, outcome="applied") for finding in findings]


def _with_mode(definition: ViewpointDefinition, mode: SelectionMode) -> ViewpointDefinition:
    return replace(definition, selection_mode=mode)
