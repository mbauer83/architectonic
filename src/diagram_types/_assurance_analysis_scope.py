"""Which analysis methods a store-projected diagram type draws.

A derived assurance diagram belongs to *an analysis*, not to the store as a whole. There is one
FMEA matrix per FMEA, one control structure per STPA — so a second FMEA needs somewhere to put its
matrix, and until this scoping existed there was one slot per type globally and it had nowhere.

Which methods a type serves is the type's own knowledge, declared in its `config.yaml` beside its
label and description:

    assurance:
      methods: [STPA, CAST]

Declared rather than derived from the data. The tempting derivation — a type applies to an analysis
if projecting that analysis' graph yields anything — reads well and fails exactly where it matters:
a new FMEA has no failure modes yet, so its matrix would be absent from the catalog until somebody
authored a row, and the matrix is *where* you author rows.

Absence raises. A type that declared nothing would silently vanish from every analysis' catalog,
which looks identical to a store with no content in it.
"""

from __future__ import annotations

from typing import Any

from src.domain.assurance.assurance_analysis import ANALYSIS_METHODS


def analysis_methods_from(config: dict[str, Any]) -> frozenset[str]:
    """The analysis methods this diagram type draws, from its own config.

    Raises ValueError when the declaration is missing, empty, or names a method the assurance
    domain does not have — all three would otherwise show up as a diagram nobody can reach.
    """
    name = str(config.get("name") or "<unnamed>")
    declared = (config.get("assurance") or {}).get("methods")
    if not declared:
        raise ValueError(
            f"Store-projected diagram type {name!r} declares no `assurance.methods` in its "
            "config.yaml. A derived diagram is scoped to one analysis, so a type that names no "
            "method is unreachable from every analysis' catalog — which is indistinguishable "
            "from an empty store."
        )
    methods = frozenset(str(method) for method in declared)
    unknown = sorted(methods - set(ANALYSIS_METHODS))
    if unknown:
        raise ValueError(
            f"Diagram type {name!r} declares unknown analysis method(s) {unknown}. "
            f"Known methods are {', '.join(ANALYSIS_METHODS)}; add the method to the assurance "
            "domain vocabulary before a diagram type claims it."
        )
    return methods
