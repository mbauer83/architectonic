"""Domain vocabulary for the assurance analysis aggregate.

An analysis is the aggregate root for a unit of STPA/CAST/GRC work. These
constants define its controlled vocabulary; they are pure domain facts with no
storage or transport dependency, so both the application use cases and the
infrastructure store adapters import them from here.
"""

from __future__ import annotations

# Analysis methods. STPA covers STPA and STPA-Sec; CAST is incident analysis;
# GRC is governance/risk/compliance; FMEA is per-component failure-mode analysis, which attaches
# to the hazards an STPA analysis already produced rather than restating them.
ANALYSIS_METHODS: tuple[str, ...] = ("STPA", "CAST", "GRC", "FMEA")

# Lifecycle states of an analysis.
ANALYSIS_STATUSES: tuple[str, ...] = ("draft", "active", "completed", "archived")

# Fields a caller may change after creation. Method and architecture anchor are
# immutable — changing either would re-scope the whole aggregate.
#: Fields an analysis exposes to editing. `group_id` is here because filing is a decision made
#: after the fact — an analysis is worth recording before anyone settles where it belongs — and
#: refiling must not require rebuilding it. `method` is deliberately absent: the method decides
#: which node types the analysis may author, so changing it would silently orphan its contents.
ANALYSIS_UPDATABLE: frozenset[str] = frozenset({"name", "status", "tlp", "group_id"})
