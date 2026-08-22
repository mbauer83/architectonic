"""The flowchart connector pair, which is how a step drawn elsewhere is reached.

Where a step is arrived at from two nesting depths and no structured placement covers both, or where
a back edge closes a loop, the step is drawn once and marked with a connector; every later arrival
draws the matching mark and detaches. `label`/`goto` would say this more directly and does not work:
on the pinned PlantUML 1.2026.3 it parses without complaint and draws nothing that connects.

Kept apart from the walk so the walk does not also own naming the marks and counting the arrivals.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field


@dataclass
class Connectors:
    """Which steps are reached by a connector, and the mark each connector pair carries.

    Two passes: the first walk records the arrivals it cannot place structurally, in the order it
    meets them; the second names them and draws both halves of each pair. One extra pass is enough
    because a connector changes no control flow, so the second walk arrives at the same steps.
    """

    name_for: Mapping[str, str] = field(default_factory=dict)
    arrivals: list[str] = field(default_factory=list)

    def record(self, step_id: str) -> None:
        if step_id not in self.arrivals:
            self.arrivals.append(step_id)


def connector_names(arrivals: Sequence[str]) -> dict[str, str]:
    """One short mark per connector pair — `A`, `B`, … `AA` — in the order the walk meets them.

    Short because the mark is drawn inside a small circle, and a connector nobody can read at a
    glance is worse than none.
    """
    names: dict[str, str] = {}
    for index, step_id in enumerate(arrivals):
        mark = ""
        remaining = index
        while True:
            mark = chr(ord("A") + remaining % 26) + mark
            remaining = remaining // 26 - 1
            if remaining < 0:
                break
        names[step_id] = mark
    return names

def emit_arrival(connectors: Connectors, step_id: str, lines: list[str]) -> None:
    """Reach a step drawn elsewhere. `detach` is what keeps this from also drawing a dangling arrow."""
    connectors.record(step_id)
    mark = connectors.name_for.get(step_id)
    if mark:
        lines.append(f"({mark})")
        lines.append("detach")


def emit_entry(connectors: Connectors, step_id: str, lines: list[str]) -> None:
    mark = connectors.name_for.get(step_id)
    if mark:
        lines.append(f"({mark})")
