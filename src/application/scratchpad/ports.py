"""What the scratchpad application layer needs from storage, and nothing more.

Three operations, because three is what the aggregate supports: a scratchpad is loaded whole,
saved whole, and listed by its metadata. There is no partial read and no partial write, which is
the same decision the REST surface makes for the same reason — the root enforces the invariants,
and a partial update cannot be validated without loading the whole thing anyway.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.application.scratchpad.lift import LiftPlan, LiftReceipt, LiftTarget
from src.domain.scratchpad import Scratchpad


@dataclass(frozen=True, slots=True)
class ScratchpadSummary:
    """What a list needs: enough to choose one, never the notes themselves."""

    artifact_id: str
    name: str
    description: str
    status: str
    version: str
    group: str
    meta_ontology: str
    note_count: int


class ScratchpadNotFoundError(LookupError):
    """No scratchpad with that id. Distinct from a refusal, so callers can answer 404."""


class ScratchpadVersionConflictError(RuntimeError):
    """The stored version is not the one the writer read.

    Optimistic concurrency, resolved by reloading: a scratchpad is a document two people may have
    open, and a last-write-wins save would silently discard an afternoon of the other one's work.
    """

    def __init__(self, artifact_id: str, expected: str, actual: str) -> None:
        super().__init__(
            f"scratchpad {artifact_id!r} has moved on: you wrote against version {expected!r}, "
            f"the store holds {actual!r}. Reload and re-apply."
        )
        self.artifact_id = artifact_id
        self.expected = expected
        self.actual = actual


class ScratchpadRepositoryPort(Protocol):
    """Load, save, list, delete. Implemented in infrastructure over YAML files."""

    def list_scratchpads(self, *, group: str | None = None, status: str | None = None) -> list[ScratchpadSummary]:
        ...

    def load(self, artifact_id: str) -> Scratchpad:
        """Raise `ScratchpadNotFoundError` if there is none."""
        ...

    def group_of(self, artifact_id: str) -> str:
        """Which collection this scratchpad currently sits in.

        Declared here rather than discovered on the implementation, because `save` requires a group
        and every edit of an existing scratchpad has to name the one it already has. Without it a
        caller either guesses — silently re-homing a scratchpad on every edit — or reaches past the
        port to ask the concrete repository, which is the coupling the port exists to prevent.
        """
        ...

    def save(self, scratchpad: Scratchpad, *, group: str, expected_version: str | None = None) -> Scratchpad:
        """Write the aggregate whole, returning what is stored — including its version.

        `expected_version` is the version the writer read. `None` means "this is a create"; a
        mismatch raises `ScratchpadVersionConflictError` rather than overwriting.

        The version returned is the store's. A caller's document may carry one — it is what that
        caller read — and it is not a claim about what the store now holds.

        **Storing what is already stored is not a write**, so it moves no version: the returned
        aggregate is what was passed in, and no other writer's token is invalidated. Callers that
        count writes should expect a save of unchanged content to be one of these.
        """
        ...

    def delete(self, artifact_id: str) -> None:
        ...


class LiftWriterPort(Protocol):
    """The write path a lift goes through, and the group registry it resolves its target against.

    Declared here because the application layer plans a lift and must not perform one: execution is
    `artifact_bulk_write` — one operation, one refusal vocabulary, the same verified write path as
    every other authoring — and that lives in infrastructure. There is deliberately no second route
    into the model, which is the property ADR@1783406851 exists to protect.
    """

    def resolve_target(self, group: str) -> LiftTarget:
        """What the named model-project is today: whether it exists, and what it declares.

        Answering rather than refusing for an unknown group is deliberate — a lift may create one,
        and the plan says so before anything is written.
        """
        ...

    def execute(self, plan: LiftPlan, *, meta_ontology: str, dry_run: bool) -> LiftReceipt:
        """Perform the plan as one transaction, creating the target project if it is new.

        *meta_ontology* is the scratchpad's, carried so a project this lift creates declares the
        vocabulary its content is in rather than inheriting whatever the repository defaults to.
        """
        ...
