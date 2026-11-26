"""How an ontology relates what a candidate writes when it is applied as a target state.

A target state puts a candidate in the model beside the baseline: a "(target)" copy of each element it
changes, traced to its original, and a plateau for each state holding the elements of that state. Which
relation traces and which holds is the ontology's vocabulary, not the change-set core's: ArchiMate has
no trace relation and uses an association, which every pair of its elements may have, and holds by
aggregation. An ontology that declares nothing cannot express a target state, and saying so is the
honest answer rather than borrowing another ontology's names.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class TargetStateRelations:
    """The connection types a target state is written with, as the ontology that declares them names them."""

    #: What traces a "(target)" copy to its original, and a gap to the plateaus it is between.
    trace: str
    #: How a plateau holds the elements of its state.
    holds: str

    @classmethod
    def from_mapping(
        cls, data: Mapping[str, object], *, named: Callable[[str], str] = str,
    ) -> TargetStateRelations | None:
        """The `target_state_relations` block of an ontology's connection data; None where it declares none.

        *named* turns a name as the file spells it into the connection type's full name.
        """
        block = data.get("target_state_relations")
        if not isinstance(block, Mapping):
            return None
        trace, holds = block.get("trace"), block.get("holds")
        if not isinstance(trace, str) or not isinstance(holds, str):
            raise ValueError("target_state_relations names a `trace` and a `holds` connection type")
        return cls(trace=named(trace), holds=named(holds))
