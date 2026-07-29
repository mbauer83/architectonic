from __future__ import annotations

from typing import Protocol

from src.domain.repository.git_repair import RepairPhase, RepairState


class GitRepairPort(Protocol):
    def load_or_initialize(self, repair_branch: str) -> RepairState: ...
    def require_expected_upstream(self, state: RepairState) -> None: ...
    def fetch_original(self, state: RepairState) -> None: ...
    def prepare_repair_branch(self, state: RepairState) -> None: ...
    def stage_and_validate(self) -> None: ...
    def has_staged_changes(self) -> bool: ...
    def commit(self, message: str) -> None: ...
    def push_repair(self, state: RepairState) -> None: ...
    def promote_to_original(self, state: RepairState) -> None: ...
    def require_clean(self) -> None: ...
    def save(self, state: RepairState) -> None: ...


def execute_git_repair(
    port: GitRepairPort,
    *,
    repair_branch: str,
    message: str,
) -> RepairState:
    state = port.load_or_initialize(repair_branch)
    state.validate(repair_branch)
    port.require_expected_upstream(state)
    port.fetch_original(state)
    state = _record(port, state, "fetched")
    port.prepare_repair_branch(state)
    port.stage_and_validate()
    state = _record(port, state, "staged")
    if port.has_staged_changes():
        port.commit(message)
    state = _record(port, state, "committed")
    port.push_repair(state)
    state = _record(port, state, "repair_pushed")
    port.promote_to_original(state)
    state = _record(port, state, "production_pushed")
    port.require_clean()
    port.require_expected_upstream(state)
    return _record(port, state, "complete")


def _record(
    port: GitRepairPort,
    state: RepairState,
    phase: RepairPhase,
) -> RepairState:
    updated = state.at(phase)
    port.save(updated)
    return updated
