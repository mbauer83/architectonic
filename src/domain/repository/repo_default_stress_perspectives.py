"""Perspectives a stressor can be thought of from: shipped frameworks, each a list of guiding questions.

A thinking aid for whoever writes stressors, not a classification. Every question looks at the
environment an organisation lives in — markets, law, people, partners — and none names an element of
the architecture under analysis: which components a stressor hits is found in the walk, not given in
advance. A perspective's `kind` is what choosing it may put in a stressor's optional kind column.

This declaration is the one vocabulary of stressor kinds. A stressor may carry a kind outside it,
written freely; that kind is counted as written and stands for no perspective.

The frameworks are data. Another framework is one more entry here, and the workspace offers it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


def kind_of(written: str) -> str:
    """A kind as it is compared with a perspective's: trimmed, and in lower case."""
    return written.strip().lower()


def kinds_in_use(written: Iterable[str]) -> dict[str, int]:
    """How many stressors name each kind, kinds that `kind_of` matches counted as one.

    Each is labelled as it was first written, trimmed; an empty kind is no kind.
    """
    labels: dict[str, str] = {}
    counts: dict[str, int] = {}
    for kind in written:
        key = kind_of(kind)
        if not key:
            continue
        labels.setdefault(key, kind.strip())
        counts[key] = counts.get(key, 0) + 1
    return {labels[key]: count for key, count in counts.items()}


@dataclass(frozen=True)
class Perspective:
    """One angle to look from, and the question that opens it."""

    id: str
    name: str
    question: str

    @property
    def kind(self) -> str:
        """The value a stressor written from this perspective may carry as its kind."""
        return kind_of(self.name)


@dataclass(frozen=True)
class PerspectiveFramework:
    """A named, established way of scanning an organisation's environment."""

    id: str
    name: str
    perspectives: tuple[Perspective, ...]


def _framework(key: str, name: str, *perspectives: tuple[str, str]) -> PerspectiveFramework:
    return PerspectiveFramework(key, name, tuple(
        Perspective(f"{key}.{label.lower().replace(' ', '-')}", label, question) for label, question in perspectives
    ))


STRESS_PERSPECTIVES: tuple[PerspectiveFramework, ...] = (
    _framework(
        "pestle", "PESTLE",
        ("Political", "What if a change of government or policy withdraws a commitment the organisation relies on?"),
        ("Economic", "What if funding, prices or demand move sharply: a recession, inflation, a currency swing?"),
        ("Social", "What if what people expect, trust or are used to shifts: a scandal, a new habit, a new norm?"),
        ("Technological", "What if a technology the organisation relies on is withdrawn, superseded or "
                          "suddenly commonplace?"),
        ("Legal", "What if a law, a ruling or a contract term changes what may be done, where, or by whom?"),
        ("Environmental", "What if a climate, energy or resource event disrupts operations or changes what is "
                          "acceptable?"),
    ),
    _framework(
        "five-forces", "Five forces",
        ("New entrants", "What if a newcomer offers the same for a fraction of the price?"),
        ("Substitutes", "What if customers can meet the same need in an entirely different way?"),
        ("Buyer power", "What if a dominant customer dictates terms, or customers act together?"),
        ("Supplier power", "What if a key supplier raises prices, changes terms or stops supplying?"),
        ("Rivalry", "What if a competitor starts a price war or matches the core offer?"),
    ),
    _framework(
        "business-model-canvas", "Business model canvas",
        ("Customer segments", "What if the main customer segment shrinks, splits or moves away?"),
        ("Value propositions", "What if what customers value most stops being what the organisation offers?"),
        ("Channels", "What if the channel customers come through closes or changes its rules?"),
        ("Customer relationships", "What if customers expect a very different relationship: self-service, or "
                                   "far more personal?"),
        ("Revenue streams", "What if the main revenue stream dries up, or the pricing model has to change?"),
        ("Key resources", "What if a resource the organisation depends on is lost: data, people, capital, a "
                          "licence?"),
        ("Key activities", "What if an activity central to delivery has to stop, be outsourced or grow tenfold?"),
        ("Key partners", "What if a key partner withdraws, is acquired or becomes a competitor?"),
        ("Cost structure", "What if a major cost doubles, or has to be halved?"),
    ),
    _framework(
        "organisation", "Organisation & people",
        ("Key people", "What if the one person who knows how something works leaves tomorrow?"),
        ("Teams", "What if a team is reorganised, merged, moved or halved?"),
        ("Culture", "What if the way decisions are made changes: new leadership, a merger, a loss of trust?"),
    ),
)


def unwritten_perspectives(kinds: Iterable[str]) -> list[str]:
    """The perspectives no stressor is written from, by id, in the declaration's order.

    None while no stressor names a kind: the kind is optional, so an empty column says nothing about
    which perspectives are missing. A kind outside the declaration is allowed and stands for none.
    """
    used = {kind_of(kind) for kind in kinds} - {""}
    if not used:
        return []
    return [one.id for framework in STRESS_PERSPECTIVES for one in framework.perspectives if one.kind not in used]

