"""How an assurance constraint has been dealt with — defined once.

A constraint's disposition names the strategy that answers it. The vocabulary is the
hierarchy of controls, strongest first: removing the possibility beats designing it out,
which beats controlling it with evidence, which beats arguing the residue is as low as
reasonably practicable, which beats simply accepting it. Because the order is a
preference ranking rather than a magnitude, it is declared ordinal and compared by rank,
never averaged.

Two things this vocabulary is deliberately not:

* It is not ISO 31000 risk treatment. `mitigate`, `transfer` and `avoid` name what an
  organisation does about a *risk* and live on a risk's `treatment` attribute. They once
  appeared here as well — the likely route being the near-homograph `accepted`/`accept` —
  which put one field in two vocabularies at once.
* It is not the VEX status of a vulnerability finding, which answers an unrelated
  question about a component and is spelled `vex_status`.

Absence is meaningful: a constraint with no disposition has no strategy decided yet. That
state is the empty field rather than a token, so "undecided" cannot be mistaken for a
decision, and every listed value is something somebody chose.

Consolidating this matters beyond tidiness. The safety-subordination safeguard fires on an
exact match against `accepted`, so every variant spelling that reached the store slipped
past it — a safety control that failed open. Writes are validated against this module so a
further spelling cannot be stored.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConstraintDisposition:
    """One strategy for answering an assurance constraint."""

    slug: str
    """Persisted value of a constraint's `disposition`."""
    label: str
    """Reader-facing wording."""
    meaning: str
    """What claiming this commits the author to."""


ELIMINATED = ConstraintDisposition(
    slug="eliminated",
    label="Eliminated",
    meaning="The hazardous condition cannot arise, because whatever gave rise to it is gone.",
)
PREVENTED_BY_DESIGN = ConstraintDisposition(
    slug="prevented-by-design",
    label="Prevented by design",
    meaning="The condition can arise, but the design makes the unsafe outcome structurally impossible.",
)
CONTROLLED_WITH_EVIDENCE = ConstraintDisposition(
    slug="controlled-with-evidence",
    label="Controlled with evidence",
    meaning="A control is in place and evidence shows it works. Claiming this requires that evidence.",
)
ALARP_JUSTIFIED = ConstraintDisposition(
    slug="alarp-justified",
    label="ALARP-justified",
    meaning="Residual exposure remains and is argued to be as low as reasonably practicable.",
)
ACCEPTED = ConstraintDisposition(
    slug="accepted",
    label="Accepted",
    meaning=(
        "The exposure is carried as it stands. Rejected for safety and security constraints, "
        "where accepting is how an obligation gets priced away."
    ),
)

#: Strongest first. Declared ordinal, so "dispositioned weaker than controlled-with-evidence"
#: is a comparison rather than an inspection.
CONSTRAINT_DISPOSITIONS: tuple[ConstraintDisposition, ...] = (
    ELIMINATED,
    PREVENTED_BY_DESIGN,
    CONTROLLED_WITH_EVIDENCE,
    ALARP_JUSTIFIED,
    ACCEPTED,
)

CONSTRAINT_DISPOSITION_SLUGS: tuple[str, ...] = tuple(d.slug for d in CONSTRAINT_DISPOSITIONS)

#: Spellings that once reached the store and mean "nothing decided yet", which this
#: vocabulary expresses as the empty field.
_ABSENCE_SPELLINGS: frozenset[str] = frozenset({"", "open", "none"})


def is_absent(slug: str | None) -> bool:
    """True when the value states that no strategy has been decided."""
    return slug is None or slug.strip().lower() in _ABSENCE_SPELLINGS


def is_known(slug: str) -> bool:
    """True when the value is a member of the vocabulary."""
    return slug in CONSTRAINT_DISPOSITION_SLUGS


def rank(slug: str) -> int | None:
    """Position in the hierarchy of controls, 0 strongest; None when unrecognised.

    An unrecognised value has no rank rather than the weakest one: a value this software
    does not know is not thereby the worst case, and ranking it as such would be an
    invented fact.
    """
    return next((i for i, d in enumerate(CONSTRAINT_DISPOSITIONS) if d.slug == slug), None)


def label_for(slug: str) -> str:
    """The reader-facing wording for a slug, or the slug itself when unrecognised."""
    return next((d.label for d in CONSTRAINT_DISPOSITIONS if d.slug == slug), slug)


@dataclass(frozen=True)
class DispositionRejection:
    """A write carrying a value outside the vocabulary."""

    value: str
    message: str


def accept_written_value(value: str | None) -> str | DispositionRejection | None:
    """Normalise a written disposition, or reject it.

    ``None`` means "leave the field as it is"; an absence spelling normalises to the empty
    field, which is how "undecided" is stored. Anything else must be a member of the
    vocabulary — an unrecognised value is refused rather than stored, because a stored
    variant is invisible to every rule that matches on an exact token.
    """
    if value is None:
        return None
    stripped = value.strip()
    if is_absent(stripped):
        return ""
    if is_known(stripped):
        return stripped
    return DispositionRejection(
        value=value,
        message=(
            f"unknown disposition {value!r}; valid: {', '.join(CONSTRAINT_DISPOSITION_SLUGS)}, "
            "or leave it empty while no strategy has been decided"
        ),
    )
