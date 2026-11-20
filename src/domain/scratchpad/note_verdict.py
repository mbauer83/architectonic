"""What the canvas may say about a note, in the vocabulary it already uses for a link.

A link has a verdict: the ontology refuses it, a specialization narrows it, or it is permitted. A
note is judged the same way and answers in the same shape — `LinkVerdict`, served on the note where
a link's is served on the link — so there is one channel a client reads and one wording a person
learns. A note that nothing is said about is `unverified`, exactly as an undecided link is.

Two tiers again. A finding that **blocks** stops a lift and reads as `refused`; one that does not is
`narrowed` and is carried into the plan as a warning. Which a finding is, is decided where it is
made: an area narrows and so only ever warns.

**What an area permits.** An area declares the domains it holds, and may name element types and
document types outright. The types it names win; otherwise its types are those of its domains; and
an area that declares nothing — like a note in no area at all — permits everything. This reads the
stored declaration as it is; nothing is added to the file for it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from src.domain.scratchpad.link_verdict import UNVERIFIED, LinkVerdict
from src.domain.scratchpad.parts import Area, Note


@dataclass(frozen=True, slots=True)
class NoteFinding:
    """One thing worth saying about a note, and whether it stops a lift."""

    message: str
    blocks: bool = False
    code: str = ""
    #: The area whose declaration narrowed the note, when that is what this is.
    narrowed_by: str = ""


def area_narrowing(
    note: Note, area: Area | None, *, domain_of: Callable[[str], str | None]
) -> NoteFinding | None:
    """The warning for a note decided as something its area does not hold, or `None`.

    Never a refusal: the type is one the meta-ontology declares, and an area is a configured scope
    over it. Where the area is asked about a level it says nothing on — a note narrowed only to a
    domain, in an area that names types and no domains — there is nothing to say.
    """
    if area is None:
        return None
    outside = _outside(note, area, domain_of)
    if not outside:
        return None
    return NoteFinding(
        message=(
            f"Area '{area.label or area.id}' holds {_held(area)}; {outside} is outside what it "
            "permits. The choice is still valid — move the note, change it, or accept the warning."
        ),
        narrowed_by=area.id,
    )


def _outside(note: Note, area: Area, domain_of: Callable[[str], str | None]) -> str:
    """What the note has decided that the area does not hold, named, or the empty string."""
    if note.destination == "document":
        permitted = area.permitted_document_types
        return note.document_type if note.document_type and permitted and (
            note.document_type not in permitted
        ) else ""
    if note.element_type:
        if area.permitted_element_types:
            return "" if note.element_type in area.permitted_element_types else note.element_type
        domain = domain_of(note.element_type)
        within = not area.permitted_domains or domain is None or domain in area.permitted_domains
        return "" if within else note.element_type
    if note.domain and area.permitted_domains and note.domain not in area.permitted_domains:
        return note.domain
    return ""


def _held(area: Area) -> str:
    declared = area.permitted_element_types or area.permitted_domains or area.permitted_document_types
    return ", ".join(declared)


def note_verdict(findings: Iterable[NoteFinding]) -> LinkVerdict:
    """Every finding about one note, as the single verdict the note is served with.

    Blocking findings lead, because they are what must be acted on; the kind and the code are the
    first one's. A person reads one message per note, so the sentences are joined rather than
    ranked away.
    """
    ordered = sorted(findings, key=lambda finding: not finding.blocks)
    if not ordered:
        return UNVERIFIED
    leading = ordered[0]
    return LinkVerdict(
        kind="refused" if leading.blocks else "narrowed",
        code=leading.code,
        message=" ".join(finding.message for finding in ordered),
        narrowed_by=next((finding.narrowed_by for finding in ordered if finding.narrowed_by), ""),
    )
