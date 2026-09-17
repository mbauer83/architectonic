"""The update as a resumable sequence of phases, and the record that survives between them (pure).

`--commit` runs in two processes: the installed version up to `environment_synced`, and the new
version from there, because the new version's migration and backend can only be run by the new code.
The journal is what both processes read, in the shape `RepairState` gives `git-repair`: a closed
phase literal, one transition per step, and validation on load so a journal written by one version and
read by another fails by name rather than by surprise.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from typing import Literal, get_args

from src.application.software_update.installation import (
    BackendObservation,
    CheckoutMove,
    DependencySelection,
    GuiProvisioning,
)

UpdatePhase = Literal[
    "planned",
    "backend_stopped",
    "checkout_moved",
    "environment_synced",
    "gui_installed",
    "assets_reconciled",
    "migrated",
    "backend_started",
    "store_authorized",
    "verified",
]

PHASE_ORDER: tuple[UpdatePhase, ...] = (
    "planned",
    "backend_stopped",
    "checkout_moved",
    "environment_synced",
    "gui_installed",
    "assets_reconciled",
    "migrated",
    "backend_started",
    "store_authorized",
    "verified",
)

#: Nothing on disk changes before this phase; every verification and the rehearsal come before it.
FIRST_WRITING_PHASE: UpdatePhase = "backend_stopped"

#: The last phase the installed version runs; the new version resumes after it.
HANDOVER_PHASE: UpdatePhase = "environment_synced"

JOURNAL_FORMAT = 1

_CHECKOUT_MOVES: tuple[CheckoutMove, ...] = get_args(CheckoutMove)
_GUI_PROVISIONINGS: tuple[GuiProvisioning, ...] = get_args(GuiProvisioning)


class JournalInvalid(ValueError):
    """A journal that another version wrote, or one whose phases are out of order."""


@dataclass(frozen=True)
class PreviousState:
    """What to put back: the checkout, the backend and the store as they were."""

    version: str
    commit: str
    branch: str | None
    backend: BackendObservation
    store_held_open: bool


@dataclass(frozen=True)
class TargetRelease:
    version: str
    tag: str
    commit: str
    gui_bundle: str | None
    #: The digest the bundle was verified against before the handover; the new version checks the
    #: bytes it installs against it, because they crossed a process boundary on disk.
    gui_bundle_sha256: str | None = None


@dataclass(frozen=True)
class UpdateJournal:
    format: int
    started_at: str
    previous: PreviousState
    target: TargetRelease
    selection: DependencySelection
    checkout_move: CheckoutMove
    gui: GuiProvisioning
    #: The last phase that completed.
    phase: UpdatePhase
    #: The command the new version is re-executed with, recorded so a resume cannot guess it.
    resume_command: tuple[str, ...]
    #: The phase whose action has begun and not yet completed; a rollback reverses it too, because a
    #: process can die between the action and the record of it.
    in_flight: UpdatePhase | None = None
    #: The data upgrade's safety point, once phase 7 has taken it; None before.
    checkpoint_set: str | None = None
    #: Whether phase 7 committed anything — what decides if rollback must restore the checkpoint.
    migration_committed: bool = False
    notes: tuple[str, ...] = ()
    #: Which deployment the actions belong to, and the compose file when it is a compose host — the
    #: resumed process must drive the same deployment the commit observed.
    deployment: str = "local-checkout"
    compose_file: str | None = None

    def begin(self, phase: UpdatePhase) -> UpdateJournal:
        """The journal with `phase` in flight; only the next phase in order can begin."""
        if PHASE_ORDER.index(phase) != PHASE_ORDER.index(self.phase) + 1:
            raise JournalInvalid(f"cannot begin {phase!r} after {self.phase!r}")
        return replace(self, in_flight=phase)

    def advance(self, phase: UpdatePhase) -> UpdateJournal:
        """The journal one phase on; only the next phase in order is accepted."""
        if PHASE_ORDER.index(phase) != PHASE_ORDER.index(self.phase) + 1:
            raise JournalInvalid(f"cannot advance from {self.phase!r} to {phase!r}")
        return replace(self, phase=phase, in_flight=None)

    @property
    def next_phase(self) -> UpdatePhase | None:
        index = PHASE_ORDER.index(self.phase) + 1
        return PHASE_ORDER[index] if index < len(PHASE_ORDER) else None

    def reached(self, phase: UpdatePhase) -> bool:
        return PHASE_ORDER.index(self.phase) >= PHASE_ORDER.index(phase)

    @property
    def handed_over(self) -> bool:
        """Whether the phases the installed version owns are done and the new version takes over."""
        return self.reached(HANDOVER_PHASE)

    @property
    def complete(self) -> bool:
        return self.phase == "verified"

    def phases_to_reverse(self) -> tuple[UpdatePhase, ...]:
        """The writing phases reached or begun, latest first — the order a rollback undoes them in."""
        last = self.in_flight or self.phase
        reached = PHASE_ORDER[PHASE_ORDER.index(FIRST_WRITING_PHASE) : PHASE_ORDER.index(last) + 1]
        return tuple(reversed(reached))

    def touched(self, phase: UpdatePhase) -> bool:
        """Whether `phase` completed or was begun — either way its effects may be on disk."""
        return phase in self.phases_to_reverse()

    def to_mapping(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> UpdateJournal:
        if data.get("format") != JOURNAL_FORMAT:
            raise JournalInvalid(f"journal format {data.get('format')!r} is not {JOURNAL_FORMAT}")
        phase = data.get("phase")
        if phase not in PHASE_ORDER:
            raise JournalInvalid(f"journal names an unknown phase {phase!r}")
        in_flight = data.get("in_flight")
        if in_flight is not None and in_flight not in PHASE_ORDER:
            raise JournalInvalid(f"journal names an unknown phase in flight {in_flight!r}")
        try:
            previous = _mapping(data["previous"])
            backend = _mapping(previous["backend"])
            target = _mapping(data["target"])
            selection = _mapping(data["selection"])
            journal = cls(
                format=JOURNAL_FORMAT,
                started_at=str(data["started_at"]),
                previous=PreviousState(
                    version=str(previous["version"]),
                    commit=str(previous["commit"]),
                    branch=_optional_str(previous.get("branch")),
                    backend=BackendObservation(
                        running=bool(backend["running"]),
                        pid=_optional_int(backend.get("pid")),
                        port=_optional_int(backend.get("port")),
                        detached=None if backend.get("detached") is None else bool(backend["detached"]),
                        flags=_strings(backend.get("flags", ())),
                        unhealthy=bool(backend.get("unhealthy", False)),
                    ),
                    store_held_open=bool(previous["store_held_open"]),
                ),
                target=TargetRelease(
                    version=str(target["version"]),
                    tag=str(target["tag"]),
                    commit=str(target["commit"]),
                    gui_bundle=_optional_str(target.get("gui_bundle")),
                    gui_bundle_sha256=_optional_str(target.get("gui_bundle_sha256")),
                ),
                selection=DependencySelection(_strings(selection["groups"]), _strings(selection["extras"])),
                checkout_move=_member(data["checkout_move"], _CHECKOUT_MOVES),
                gui=_member(data["gui"], _GUI_PROVISIONINGS),
                phase=_member(phase, PHASE_ORDER),
                resume_command=_strings(data["resume_command"]),
                in_flight=None if in_flight is None else _member(in_flight, PHASE_ORDER),
                checkpoint_set=_optional_str(data.get("checkpoint_set")),
                migration_committed=bool(data.get("migration_committed", False)),
                notes=_strings(data.get("notes", ())),
                deployment=str(data.get("deployment", "local-checkout")),
                compose_file=_optional_str(data.get("compose_file")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise JournalInvalid(f"journal is missing or misspells a field: {exc}") from exc
        return journal


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"expected a mapping, got {type(value).__name__}")
    return dict(value)


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        raise TypeError(f"expected a list, got {type(value).__name__}")
    return tuple(str(item) for item in value)


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, int):
        return value
    raise TypeError(f"expected an integer, got {type(value).__name__}")


def _member[T](value: object, members: tuple[T, ...]) -> T:
    """The member of a closed set that `value` spells, or a TypeError the loader turns into JournalInvalid."""
    for member in members:
        if member == value:
            return member
    raise TypeError(f"{value!r} is not one of {members}")
