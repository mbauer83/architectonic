"""Generic view-projection contracts for model-backed diagram views.

display_class and role are OPAQUE to generic code. The diagram-type module
assigns them; generic code forwards them verbatim. This module must never
branch on those values — it treats them as plain, uninterpreted strings.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from src.domain.relationships.derivation_types import ModelQuery
    from src.domain.viewpoints.view_derivations import ViewDerivation


@dataclass(frozen=True)
class ProjectedViewItem:
    """One model entity projected into a diagram view, ready for display.

    display_class and role are opaque to generic code: the diagram-type module
    assigns them; generic code forwards them verbatim.
    """

    entity_id: str
    name: str
    display_class: str
    role: str
    excluded: bool = False


@dataclass(frozen=True)
class ViewProjectionResult:
    """What a diagram-type module returns for a model-backed view.

    derivation carries the normalized, persistable spec. items is the
    already-classified projection for the preview checklist. Both are
    produced by one engine run and cannot disagree.
    """

    derivation: ViewDerivation
    items: tuple[ProjectedViewItem, ...]


@runtime_checkable
class ViewProjector(Protocol):
    """Capability protocol for diagram types that derive a model-backed view.

    Separate from DiagramTypeModule (SRP: type declaration vs view projection).
    A diagram-type module opts in by implementing project_view; the preview
    service discovers it via isinstance and stays diagram-type-agnostic.
    """

    def project_view(
        self,
        diagram_type: str,
        diagram_entities: Mapping[str, object],
        query: ModelQuery,
    ) -> ViewProjectionResult | None: ...
