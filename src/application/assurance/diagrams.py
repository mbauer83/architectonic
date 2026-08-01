"""The catalog of diagrams drawn from the live assurance store.

Every entry is derived from the registered diagram types rather than listed here: a type is on this
surface because it projects its content from a store graph, and it presents itself with the label and
description its own `config.yaml` declares. A hand-kept list would be a second place to state what
the types already state — which is how the bowtie renderer and the UCA guideword vocabulary drifted
apart from each other in the first place.

**An entry is one analysis crossed with one applicable type, not a type on its own.** A derived
diagram belongs to a unit of work: there is one control structure per STPA and one matrix per FMEA.
Keyed by type alone there is a single slot per type for the whole store, so a second FMEA has
nowhere to put its matrix and asking for "the" FMEA matrix means asking for a drawing of every
analysis at once — which is what "diagram rendering is unavailable" was reporting.

Each entry is therefore titled for its *analysis*; the type label is carried beside it. A reader
with three analyses open needs to know which one they are looking at, and the type is the thing
they already chose.
"""

from __future__ import annotations

from typing import Any

from src.domain.assurance.analysis_scoped_diagram import AnalysisScopedDiagramType
from src.domain.modules.catalogs import DiagramTypeCatalog


def assurance_surface_diagram_types(diagram_types: DiagramTypeCatalog) -> frozenset[str]:
    """Diagram-type keys whose content lives in the assurance store instead of the repository.

    File-backed listings skip these: there is no artifact on disk to list, open or group.
    """
    return diagram_types.store_projected_diagram_types()


def diagram_types_for_method(diagram_types: DiagramTypeCatalog, method: str) -> list[str]:
    """Store-projected type keys that draw the work of ``method``, sorted for a stable catalog.

    The affinity is each type's own declaration (`assurance.methods` in its config), asked for
    here rather than tabulated — a table would be a second statement of what the types say, and
    the two would drift the first time a method gained a diagram.
    """
    registered = diagram_types.all_diagram_types()
    return sorted(
        key for key in assurance_surface_diagram_types(diagram_types)
        if _draws_method(registered.get(key), method)
    )


def _draws_method(diagram_type: Any, method: str) -> bool:
    """A type that declares no analysis scope draws no analysis: it projects some other module's
    store, and this catalog is not the place it belongs."""
    if not isinstance(diagram_type, AnalysisScopedDiagramType):
        return False
    return method in diagram_type.analysis_methods


def assurance_surface_diagrams(
    diagram_types: DiagramTypeCatalog,
    analyses: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """One entry per visible analysis per applicable type, in the order the analyses arrive.

    ``analyses`` must already be exposure-filtered: an entry names its analysis, so an
    above-ceiling analysis appearing here would disclose both its existence and its method.
    """
    return [
        _entry(diagram_types, analysis, type_key)
        for analysis in analyses
        for type_key in diagram_types_for_method(diagram_types, str(analysis.get("method", "")))
    ]


def _entry(
    diagram_types: DiagramTypeCatalog,
    analysis: dict[str, Any],
    type_key: str,
) -> dict[str, str]:
    ui = diagram_types.all_diagram_types()[type_key].ui_config
    analysis_id = str(analysis.get("analysis_id", ""))
    return {
        # Composite and opaque: the pair is the identity of a derived diagram, and a client that
        # split it apart would be re-deriving a key it was handed.
        "diagram_id": f"{analysis_id}::{type_key}",
        "analysis_id": analysis_id,
        "analysis_name": str(analysis.get("name", "")),
        "method": str(analysis.get("method", "")),
        "diagram_type": type_key,
        "title": str(analysis.get("name", "")) or analysis_id,
        "type_label": ui.label,
        "description": ui.description,
    }
