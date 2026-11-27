"""The purpose line a diagram shows — who it is for and what it answers — as the diagram read serves it."""

from __future__ import annotations

from src.infrastructure.rest.contracts.wire_nulls import NullsOmitted


class PurposeEntryShown(NullsOmitted):
    """One entry as a reader sees it: its words, and the element it refers to where it is a reference."""

    #: Prose as written, or the referenced element's name — its id where the repository no longer holds it.
    text: str
    #: The referenced element's artifact id. Absent for prose.
    ref: str | None = None


class DiagramPurposeResponse(NullsOmitted):
    """The lines shown on the diagram's page: its own, each list it does not state taken from its viewpoint."""

    stakeholders: list[PurposeEntryShown]
    concerns: list[PurposeEntryShown]
    #: The viewpoint supplying at least one shown list. Absent where both are the diagram's own.
    inherited_from: str | None = None
