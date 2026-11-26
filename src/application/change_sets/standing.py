"""Where each operation of a set stands against the model as it is now.

Computed on every read and never stored: a standing is a fact about a set *and* a model, and storing
it would be storing an answer whose question keeps changing. Four positions, and telling them apart
is what separates "this set is wrong" from "the model moved":

* **applies** — the model is as the operation expected, or has not been shown to differ.
* **already-there** — the model already says what the operation asks. Nothing to do, and not a
  conflict: reporting it as one would ask an author to resolve their own accepted work.
* **drifted** — what the operation would replace is neither what it was written against nor what it
  asks for. Someone put a value there after the author last looked, and applying would overwrite it.
* **conflicting** — the operation has nothing to apply to, or what it would produce is refused.

An edit's standing also says what the model holds where it writes (`holds`), so a reader of a dry run sees
what applying it replaces, not only what it was written against.

**Drift is the rebase's rule, not a second one.** `has_moved` asks `moved_since`, which is what a
proposed change is rebased by. An operation and a proposal holding the same three values get the
same answer.

**Verification is injected.** Whether an applied operation would still verify is the verifier's to
say, and it is handed in as `would_refuse` exactly as the rebase is handed its replay — so standing
is decidable against records. The refusal is carried verbatim: it is the sentence the author acts
on, and a paraphrase here would be a second vocabulary for it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias, get_args

from src.application.change_sets.base import (
    BaseRevision,
    has_moved,
    record_revision,
    says_the_same,
)
from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.composition import compose
from src.application.change_sets.operations import (
    AddConnection,
    CreateEntity,
    EditConnection,
    EditEntity,
    Operation,
    RemoveConnection,
    RemoveEntity,
)
from src.application.change_sets.ordering import application_order
from src.application.change_sets.reading import FieldValues, ModelReading
from src.application.modeling.edit_field_catalogue import KEYED, ArtifactKind
from src.application.modeling.edit_field_values import comparable

#: Where one operation stands against the model as it is now.
Standing: TypeAlias = Literal["applies", "already-there", "drifted", "conflicting"]

#: The closed set, so a summary iterates the positions rather than restating them.
STANDINGS: tuple[Standing, ...] = get_args(Standing)

#: Whether applying one operation would be refused: the refusal, or None when it would verify.
WouldRefuse: TypeAlias = Callable[[Operation], str | None]


@dataclass(frozen=True, slots=True)
class HeldValue:
    """What the model holds at the one place an edit writes: what applying it would replace."""

    value: Any


@dataclass(frozen=True, slots=True)
class OperationStanding:
    """One operation's position, and the sentence an author reads about it."""

    operation: Operation
    standing: Standing
    reason: str
    #: For an edit whose field the model can be read at, what it holds there now; None otherwise.
    holds: HeldValue | None = None


def standing_of(
    change_set: ChangeSet,
    reading: ModelReading,
    *,
    beneath: Sequence[ChangeSet] = (),
    would_refuse: WouldRefuse = lambda _operation: None,
) -> tuple[OperationStanding, ...]:
    """Each operation's standing, in the order the set would be applied.

    A set read on top of others is judged against the model *with the lower sets applied*: that is
    the state it was written on, and judging it against the bare model would report every use of
    what a lower set creates as a conflict.
    """
    operations = application_order(change_set, beneath=beneath)
    lower = compose(beneath[-1], reading, beneath=beneath[:-1]) if beneath else reading
    created = frozenset(change_set.created)
    return tuple(_judged(operation, lower, created, would_refuse) for operation in operations)


def _judged(
    operation: Operation, reading: ModelReading, created: frozenset[str], would_refuse: WouldRefuse
) -> OperationStanding:
    standing, reason = _against(operation, reading, created)
    holds = _held(operation, reading)
    if standing == "applies" and (refusal := would_refuse(operation)) is not None:
        return OperationStanding(operation, "conflicting", refusal, holds)
    return OperationStanding(operation, standing, reason, holds)


def _held(operation: Operation, reading: ModelReading) -> HeldValue | None:
    """What the model holds where *operation* writes, if it is an edit of a field the model can be read at."""
    match operation:
        case EditEntity(target=target):
            kind: ArtifactKind = "entity"
            current = reading.entity(target)
        case EditConnection(address=address):
            kind = "connection"
            current = reading.connection(address)
        case _:
            return None
    if current is None or operation.field not in current:
        return None
    return HeldValue(_addressed(kind, current, operation))


def _against(
    operation: Operation, reading: ModelReading, created: frozenset[str]
) -> tuple[Standing, str]:
    match operation:
        case CreateEntity(artifact_id=artifact_id, fields=fields):
            existing = reading.entity(artifact_id) if artifact_id else None
            return _new("entity", str(artifact_id), fields, existing)
        case EditEntity(target=target):
            return _edited("entity", target, operation, reading.entity(target))
        case RemoveEntity(target=target, base=base):
            return _removed(target, base, reading.entity(target))
        case AddConnection(address=address, fields=fields):
            missing = [
                end for end in address.endpoints
                if end not in created and reading.entity(end) is None
            ]
            if missing:
                return "conflicting", (
                    f"{' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} not in the "
                    f"model, so the connection {address} has nothing to join."
                )
            return _new("connection", str(address), fields, reading.connection(address))
        case EditConnection(address=address):
            return _edited("connection", str(address), operation, reading.connection(address))
        case RemoveConnection(address=address, base=base):
            return _removed(str(address), base, reading.connection(address))


def _new(
    kind: ArtifactKind, subject: str, stated: Mapping[str, Any], existing: FieldValues | None
) -> tuple[Standing, str]:
    """A create or an add: fine unless what it would create is already there."""
    if existing is None:
        return "applies", f"creates a new {kind}."
    differing = sorted(
        name for name, value in stated.items()
        if name in existing and comparable(existing[name]) != comparable(value)
    )
    if differing:
        return "conflicting", (
            f"{subject} already exists and says something else in {', '.join(differing)}. To "
            "change it, edit it; a create cannot replace what is there."
        )
    return "already-there", f"{subject} already exists and says what this operation states."


def _edited(
    kind: ArtifactKind,
    subject: str,
    edit: EditEntity | EditConnection,
    current: FieldValues | None,
) -> tuple[Standing, str]:
    if current is None:
        return "conflicting", (
            f"{subject} is not in the model any more, so this edit has nothing to apply to."
        )
    if edit.field not in current:
        return "applies", (
            f"{edit.claim} cannot be read here, so nothing shows it has moved."
        )
    now = _addressed(kind, current, edit)
    if says_the_same(edit.base, now, edit.value):
        return "already-there", f"{edit.claim} already says what this edit asks for."
    if has_moved(edit.base, current=now, proposed=edit.value):
        return "drifted", (
            f"{edit.claim} changed since this edit was written, so applying it would overwrite a "
            "value its author has not seen. To keep what the model says, drop the edit; to replace "
            "it, make the edit again against the model as it stands now."
        )
    return "applies", f"{edit.claim} is as this edit expected."


def _addressed(kind: ArtifactKind, current: FieldValues, edit: EditEntity | EditConnection) -> Any:
    """What the model holds at the one place the edit addresses."""
    held = current[edit.field]
    if edit.field not in KEYED[kind]:
        return held
    return held.get(str(edit.key)) if isinstance(held, Mapping) else None


def _removed(
    subject: str, base: BaseRevision, current: FieldValues | None
) -> tuple[Standing, str]:
    if current is None:
        return "already-there", f"{subject} is already gone."
    if record_revision(current) != base.revision:
        return "drifted", (
            f"{subject} changed since its removal was written, so removing it would discard "
            "content its author has not seen. Read it again, and remove it against what it says "
            "now if it should still go."
        )
    return "applies", f"{subject} is as it was when its removal was written."
