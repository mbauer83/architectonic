"""The ranked scales assurance assessments are rated on — defined once.

Two five-point scales recur across the assurance methods, and both are ordinal: their members
are ordered, but the distance between adjacent members is unknown. They are written out here so
that every schema, form and query reads the same members in the same order. Two copies of one
scale is how vocabularies drift, and a drifted scale is worse than a missing one — it compares
without complaining.

Five points rather than the ten of some FMEA handbooks: a second scale system inside one store
costs more than a documented deviation, and the existing risk ratings are already five-point.

**Consequence severity** answers *how bad is the outcome*. It rates the loss, so it is the same
question whether it is reached from a risk assessment or along a hazard chain — which is why one
scale serves both, and why nobody should later reconcile two of them.

**Likelihood** answers *how often*. It is deliberately not derived from anything: no measurement
in this repository estimates a rate, and a scale that looks computed but is not would carry more
authority than it earns.
"""

from __future__ import annotations

#: Ascending severity of outcome. Index = rank.
CONSEQUENCE_SEVERITY_SCALE: tuple[str, ...] = (
    "negligible",
    "minor",
    "moderate",
    "major",
    "catastrophic",
)

#: Ascending frequency of occurrence. Index = rank.
LIKELIHOOD_SCALE: tuple[str, ...] = (
    "rare",
    "unlikely",
    "possible",
    "likely",
    "almost-certain",
)
