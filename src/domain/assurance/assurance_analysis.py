"""Domain vocabulary for the assurance analysis aggregate.

An analysis is the aggregate root for a unit of STPA/CAST/GRC work. These
constants define its controlled vocabulary; they are pure domain facts with no
storage or transport dependency, so both the application use cases and the
infrastructure store adapters import them from here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, TypeAlias, get_args

# Analysis methods. STPA covers STPA and STPA-Sec; CAST is incident analysis;
# GRC is governance/risk/compliance; FMEA is per-component failure-mode analysis, which attaches
# to the hazards an STPA analysis already produced rather than restating them.
AnalysisMethod: TypeAlias = Literal["STPA", "CAST", "GRC", "FMEA"]

# Lifecycle states of an analysis.
AnalysisStatus: TypeAlias = Literal["draft", "active", "completed", "archived"]

#: The runtime tuples the use cases validate against, derived from the types rather than repeated
#: beside them. Both spellings are needed — a use case checks membership at run time and a response
#: contract needs the vocabulary at type level — and written twice they drift: the wire would keep
#: publishing a method the domain had retired, or reject one it had added.
ANALYSIS_METHODS: tuple[AnalysisMethod, ...] = get_args(AnalysisMethod)
ANALYSIS_STATUSES: tuple[AnalysisStatus, ...] = get_args(AnalysisStatus)

# Fields a caller may change after creation. Method and architecture anchor are
# immutable — changing either would re-scope the whole aggregate.
#: Fields an analysis exposes to editing. `group_id` is here because filing is a decision made
#: after the fact — an analysis is worth recording before anyone settles where it belongs — and
#: refiling must not require rebuilding it. `method` is deliberately absent: the method decides
#: which node types the analysis may author, so changing it would silently orphan its contents.
ANALYSIS_UPDATABLE: frozenset[str] = frozenset({"name", "status", "tlp", "group_id"})

#: Fields an analysis may acquire once and then never change. `architecture_anchor_id` is optional at
#: creation, so an analysis can exist without one — and while it was merely *immutable*, "optional"
#: was unusable after the fact: nothing could ever fill it, and recreating the analysis was barred
#: too, because provenance is immutable and its nodes cannot be re-filed under a replacement.
#:
#: The distinction the immutability was really making is between *moving* an anchor and *filling*
#: one. Moving it rewrites what the analysis was scoped to, and every finding under it was reached
#: against the old subject. Filling one that was never set rewrites nothing. Only that transition is
#: open.
ANALYSIS_FILLABLE_ONCE: frozenset[str] = frozenset({"architecture_anchor_id"})


def analysis_field_value(record: Mapping[str, object], field: str) -> str:
    """The value *record* carries for *field*, normalised — empty where it carries none.

    Absent, empty and whitespace all read as empty, so a record from a store that never wrote the
    column is not a record with an anchor. One accessor rather than a separate is-set predicate: the
    fill rule needs to know whether the field is set, the refusal needs to name what it is set to,
    and two spellings of "normalised current value" would be the same read written twice.
    """
    return str(record.get(field) or "").strip()


def permitted_analysis_updates(
    record: Mapping[str, object], attrs: Mapping[str, object]
) -> dict[str, object]:
    """The subset of *attrs* an update may apply to *record*.

    One decision procedure, because there are two appliers — the file stores rewrite a record, the
    SQLCipher store builds an UPDATE — and the rule written twice would let one backend accept what
    the other refused. A fill-once field is admitted only into an empty one, and only with a value:
    clearing is a move to nothing, which is still a move.
    """
    permitted: dict[str, object] = {}
    for key, value in attrs.items():
        if key in ANALYSIS_UPDATABLE:
            permitted[key] = value
        elif key in ANALYSIS_FILLABLE_ONCE and not analysis_field_value(record, key):
            if str(value or "").strip():
                permitted[key] = value
    return permitted
