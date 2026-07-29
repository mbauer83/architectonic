"""The assurance module's own requirement of a diagram type it projects.

A derived assurance diagram belongs to *an analysis*, not to the store as a whole: there is one
control structure per STPA and one matrix per FMEA. So a second FMEA needs somewhere to put its
matrix, and keyed by type alone there is one slot per type for the entire store and it has nowhere.

This protocol is declared here, beside `ANALYSIS_METHODS`, rather than on the generic
`StoreGraphProjectingDiagramType` capability. That capability says only that a type draws from a
live graph instead of a file, which is true of any module with a store behind it; *which analysis
method* the drawing belongs to is assurance vocabulary, and the common ontology protocol must not
name it. A module that later projects its own store declares its own scoping in its own terms.

Structural, so a diagram type opts in simply by declaring the property — no base class to inherit
and no registry to keep in step.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class AnalysisScopedDiagramType(Protocol):
    """A diagram type that draws the work of one or more assurance analysis methods."""

    @property
    def analysis_methods(self) -> frozenset[str]:
        """Methods from `ANALYSIS_METHODS` whose work this diagram draws (e.g. STPA, CAST)."""
        ...
