from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

RepairPhase = Literal[
    "initialized",
    "fetched",
    "staged",
    "committed",
    "repair_pushed",
    "production_pushed",
    "complete",
]


@dataclass(frozen=True)
class RepairState:
    original_branch: str
    repair_branch: str
    phase: RepairPhase

    def validate(self, requested_repair_branch: str) -> None:
        if self.original_branch.startswith("repair/"):
            raise ValueError("Recorded original branch is a repair branch")
        if self.repair_branch != requested_repair_branch:
            raise ValueError(
                f"Repair branch mismatch: state={self.repair_branch} "
                f"requested={requested_repair_branch}"
            )

    def at(self, phase: RepairPhase) -> RepairState:
        return replace(self, phase=phase)
