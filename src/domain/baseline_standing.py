"""How an artifact stands relative to the enterprise baseline, as a closed value on the record.

The product must be able to answer, wherever an artifact is read: *is what I am looking at the
enterprise baseline, or does it carry local changes not yet accepted upstream — and which parts?*

**Not called provenance.** This codebase already uses that word for three unrelated facts: which
analysis produced an assurance node, which source won a deployment layout field
(`deployment/layout.py`), and what a viewpoint fork descends from (`viewpoints/viewpoint_lineage.py`).
A fourth meaning would make the word carry none of them.

**Not a boolean.** A flag can say *that* something is proposed and never *which parts*, and the
codebase has already run that experiment: `is_global` is one predicate with one owner, but the
decision to emit it is spelled at ten call sites and the three search serialisers disagree — two of
them omit it, which the contract permits because it is declared `bool | None = None`. So this is a
closed union, matched exhaustively, and it is a non-optional field wherever it is carried.

**The condition is derived, never stored.** `stale` and `conflicting` are facts about a proposal
*and* the baseline it was written against, so they can change without the proposal changing. Storing
one is storing a conclusion that goes out of date silently.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias, get_args

#: Whether a proposal still applies cleanly to the baseline it names. Derived on every read from the
#: proposal and the current enterprise state; never persisted.
ChangeCondition: TypeAlias = Literal["current", "stale", "conflicting"]

CHANGE_CONDITIONS: tuple[str, ...] = get_args(ChangeCondition)

#: The discriminator a payload carries, so a client can match on the same two arms.
BASELINE_KIND = "enterprise-baseline"
PROPOSED_KIND = "proposed"


class ImpossibleStanding(ValueError):
    """A standing that cannot describe a real artifact."""


@dataclass(frozen=True, slots=True)
class EnterpriseBaseline:
    """What is being read is exactly the enterprise baseline: no local change is pending against it.

    Carries no fields on purpose. "Which parts differ" has one truthful answer here — none — and a
    field holding it would be a place for the answer to be wrong.
    """

    def to_mapping(self) -> Mapping[str, object]:
        return {"kind": BASELINE_KIND}

    def __str__(self) -> str:
        return "enterprise baseline"


@dataclass(frozen=True, slots=True)
class Proposed:
    """The baseline plus local changes that have not been accepted upstream.

    `changed_fields` is what makes this answerable at field granularity: a reader of a proposed
    artifact can see that its `name` is the baseline's and its `description` is not.
    """

    proposal_ids: tuple[str, ...]
    changed_fields: tuple[str, ...]
    base_revision: str
    condition: ChangeCondition

    def __post_init__(self) -> None:
        if not self.proposal_ids:
            raise ImpossibleStanding(
                "a proposed standing names no proposal; an artifact with nothing pending against it "
                "is EnterpriseBaseline, which is a different arm rather than an empty one"
            )
        if not self.changed_fields:
            raise ImpossibleStanding(
                f"proposal {self.proposal_ids[0]} changes no field; a proposal with no recorded edit "
                "cannot be reviewed, so it is refused where it would be constructed"
            )
        if not self.base_revision:
            raise ImpossibleStanding(
                f"proposal {self.proposal_ids[0]} names no base revision; without one there is "
                "nothing to decide staleness or integration against"
            )
        if self.condition not in CHANGE_CONDITIONS:
            raise ImpossibleStanding(
                f"{self.condition!r} is not a change condition; expected one of "
                f"{', '.join(CHANGE_CONDITIONS)}"
            )

    def to_mapping(self) -> Mapping[str, object]:
        return {
            "kind": PROPOSED_KIND,
            "proposal_ids": list(self.proposal_ids),
            "changed_fields": list(self.changed_fields),
            "base_revision": self.base_revision,
            "condition": self.condition,
        }

    def __str__(self) -> str:
        fields = ", ".join(self.changed_fields)
        proposals = ", ".join(self.proposal_ids)
        suffix = "" if self.condition == "current" else f", {self.condition}"
        return f"proposed ({fields}; {proposals}{suffix})"


#: One artifact's standing. Two arms, matched exhaustively — a third would be a fact about the
#: baseline the domain does not currently have.
BaselineStanding: TypeAlias = EnterpriseBaseline | Proposed

#: The value a read carries when nothing is pending. Shared rather than reconstructed: the arm holds
#: no fields, so every instance is the same value.
BASELINE: BaselineStanding = EnterpriseBaseline()


def standing_from_mapping(payload: Mapping[str, object]) -> BaselineStanding:
    """Read back what `to_mapping` wrote, for the round trip a client performs over the wire.

    Stated over what the encoding *permits*, not over what the writer emits today: an unrecognised
    kind is refused rather than silently read as the baseline, which is the reading that would make
    a proposed artifact look accepted.
    """
    match payload.get("kind"):
        case k if k == BASELINE_KIND:
            return EnterpriseBaseline()
        case k if k == PROPOSED_KIND:
            return Proposed(
                proposal_ids=tuple(str(p) for p in _sequence(payload, "proposal_ids")),
                changed_fields=tuple(str(f) for f in _sequence(payload, "changed_fields")),
                base_revision=str(payload.get("base_revision", "")),
                condition=_condition(payload.get("condition")),
            )
        case other:
            raise ImpossibleStanding(
                f"{other!r} is not a baseline standing; expected {BASELINE_KIND} or {PROPOSED_KIND}"
            )


def _sequence(payload: Mapping[str, object], key: str) -> tuple[object, ...]:
    value = payload.get(key)
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ImpossibleStanding(f"{key} must be a list of ids, got {value!r}")
    return tuple(value)


def _condition(value: object) -> ChangeCondition:
    match value:
        case "current" | "stale" | "conflicting":
            return value
        case other:
            raise ImpossibleStanding(
                f"{other!r} is not a change condition; expected one of {', '.join(CHANGE_CONDITIONS)}"
            )
