"""Group value types for the three independent artifact-grouping axes.

Groups are directory-based: membership is derived from the file path, never stored
in frontmatter. This module contains pure value types — no infrastructure imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

GroupAxis = Literal["model-project", "diagram-collection", "document-collection", "analysis-collection"]

UNCATEGORIZED = "uncategorized"
"""Uniform fallback group returned by group_fn when no group segment is present."""


@dataclass(frozen=True)
class GroupEntry:
    """A single group within one axis.

    slug   — directory name; the human-readable locator passed to tools.
    id     — stable opaque identifier (``GRP@epoch.random``); survives rename/tier-crossing.
    name   — display name; cheaply mutable without a file move.
    default — model-project axis only: the initially-selected group in the GUI.
    """

    slug: str
    id: str
    name: str
    description: str = ""
    order: int = 0
    archived: bool = False
    default: bool = False
    meta_ontology: str = ""           # model-project only: ontology framework restriction
    type_filter: tuple[str, ...] = ()  # diagram/document-collection only: allowed artifact types


@dataclass(frozen=True)
class GroupRegistry:
    """In-memory representation of .arch-repo/groups.yaml.

    Synthesised ``uncategorized`` entries are always present (guaranteed by loader).
    """

    model_projects: tuple[GroupEntry, ...] = field(default_factory=tuple)
    diagram_collections: tuple[GroupEntry, ...] = field(default_factory=tuple)
    document_collections: tuple[GroupEntry, ...] = field(default_factory=tuple)
    analysis_collections: tuple[GroupEntry, ...] = field(default_factory=tuple)

    def _by_axis(self, axis: GroupAxis) -> tuple[GroupEntry, ...]:
        if axis == "model-project":
            return self.model_projects
        if axis == "diagram-collection":
            return self.diagram_collections
        if axis == "analysis-collection":
            return self.analysis_collections
        return self.document_collections

    def find(self, axis: GroupAxis, slug: str) -> GroupEntry | None:
        for entry in self._by_axis(axis):
            if entry.slug == slug:
                return entry
        return None

    def list_axis(self, axis: GroupAxis, *, include_archived: bool = True) -> list[GroupEntry]:
        entries = list(self._by_axis(axis))
        if not include_archived:
            entries = [e for e in entries if not e.archived]
        return sorted(entries, key=lambda e: (e.order, e.slug))

    def default_model_project(self) -> GroupEntry | None:
        for entry in self.model_projects:
            if entry.default:
                return entry
        return None

    def is_valid_target(self, axis: GroupAxis, slug: str) -> bool:
        """Return True if slug is registered (existing folder check is infra-layer concern)."""
        return self.find(axis, slug) is not None
