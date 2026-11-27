"""Advice, reported apart from errors and warnings, by the status of the element it is about.

Two readings of the same findings. A *verify report* takes a pass's results and separates the advice
out of them: the results keep only what is wrong, and the advice is counted by status and listed —
in the default listing, only where the status says it should be (an active element's), so a draft's
heuristics are a count and not a wall of text. An *element reading* answers for one element, from the
index, what advice is open on it and what it has acknowledged — the entity page and the promotion dry
run ask that.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal, Protocol

from src.application.verification._issue_serialization import as_issue_dict
from src.application.verification._ordered_sequence_rule import element_sequence_advice, sequence_vocabulary
from src.application.verification.artifact_verifier_types import VerificationResult
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.relationships.ordered_sequences import Relation, SequenceGraph
from src.domain.verification_advice import (
    ACCEPTED_ADVICE_KEY,
    ADVICE_CODES,
    AcceptedAdvice,
    AdvicePresentation,
    accepted_advice_from_frontmatter,
    issue_presentation,
    issue_status,
    presentation_for,
)
from src.domain.verification_findings import Issue

#: Which advice a report lists. `by-status` follows each element's status; `all` lists every one.
AdviceListing = Literal["by-status", "all"]


@dataclass(frozen=True)
class VerifyReport:
    """A pass's results with advice taken out, and the advice on its own."""

    results: tuple[VerificationResult, ...]
    advice: tuple[Issue, ...]

    def listed(self, listing: AdviceListing) -> tuple[Issue, ...]:
        match listing:
            case "all":
                return self.advice
            case "by-status":
                return tuple(issue for issue in self.advice if issue_presentation(issue) == "listed")

    def advice_by_status(self) -> dict[str, int]:
        return dict(sorted(Counter(issue_status(issue) for issue in self.advice).items()))

    def advice_payload(self, listing: AdviceListing) -> list[dict[str, Any]]:
        return [as_issue_dict(issue) for issue in self.listed(listing)]


def verify_report(results: Iterable[VerificationResult]) -> VerifyReport:
    """Separate the advice out of *results*. A result left with nothing to say keeps its place only
    if it is invalid; the advice moves to the report's own section."""
    held = tuple(results)
    return VerifyReport(
        results=tuple(replace(r, issues=[i for i in r.issues if i.severity != "advice"]) for r in held),
        advice=tuple(issue for r in held for issue in r.advice),
    )


class OutboundConnections(Protocol):
    """The two graph questions an element reading asks: what an element relates to, and what it is."""

    def get_entity(self, artifact_id: str) -> EntityRecord | None: ...

    def find_connections_for(
        self, entity_id: str, *, direction: Literal["any", "outbound", "inbound"] = "any", conn_type: str | None = None
    ) -> Sequence[ConnectionRecord]: ...


@dataclass(frozen=True)
class ElementAdvice:
    """What advice is open on one element, and what it has acknowledged."""

    open: tuple[Issue, ...]
    accepted: tuple[AcceptedAdvice, ...]
    #: How the open advice is to be shown, from the element's status — decided here, once, so a
    #: surface reads it rather than restating the policy.
    presentation: AdvicePresentation

    def as_payload(self) -> dict[str, Any]:
        return {
            "presentation": self.presentation,
            "open": [as_issue_dict(issue) for issue in self.open],
            "accepted": [
                {"code": a.code, "reason": a.reason, "title": ADVICE_CODES.get(a.code, "")} for a in self.accepted
            ],
        }


def element_advice(record: EntityRecord, graph: OutboundConnections, catalogs: Any) -> ElementAdvice:
    """The advice about *record*, read off the index through *graph*'s outbound connections."""

    def outgoing(source: str) -> tuple[Relation, ...]:
        return tuple(
            Relation(c.conn_type, c.source, c.target) for c in graph.find_connections_for(source, direction="outbound")
        )

    def type_of(artifact_id: str) -> str | None:
        found = graph.get_entity(artifact_id)
        return None if found is None else found.artifact_type

    finding = element_sequence_advice(record, SequenceGraph(outgoing, type_of), sequence_vocabulary(catalogs))
    return ElementAdvice(
        open=() if finding is None else (finding,),
        accepted=accepted_advice_from_frontmatter(record.extra.get(ACCEPTED_ADVICE_KEY)),
        presentation=presentation_for(record.status),
    )
