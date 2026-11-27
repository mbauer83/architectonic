"""A purpose line as a body states it — for REST and MCP alike, and in the viewpoint and diagram reads.

The wire mirror of `src.domain.purpose_lines`: an entry is prose, or `{ref: <artifact id>}`. Declared
once, below both transports as the other `*_wire` modules are, because the diagram replacement REST and
MCP share takes it and so it may not live among one transport's contracts. What the entries mean, and
whether they read, stays the domain's: the mixin hands them over as stated.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PurposeReferenceSpec(BaseModel):
    """An entry naming an element: a Stakeholder for `stakeholders`, the element stating it for `concerns`."""

    model_config = ConfigDict(extra="forbid")

    ref: str = Field(description="The artifact id of the element this entry refers to.")


#: One entry of a `stakeholders` or `concerns` list.
type PurposeEntrySpec = str | PurposeReferenceSpec


def entries_as_stated(entries: list[PurposeEntrySpec] | None) -> list[object] | None:
    """The entries in the plain form the domain reads; None (not stated) stays None."""
    if entries is None:
        return None
    return [entry if isinstance(entry, str) else entry.model_dump() for entry in entries]


class StatesPurposeLines(BaseModel):
    """A diagram write body that may say who the diagram is for and what it answers.

    Absent keeps what the diagram states (on a create: states none); an empty list clears that list, and
    the diagram then shows its viewpoint's.
    """

    stakeholders: list[PurposeEntrySpec] | None = Field(
        default=None, description="Who the diagram is for: prose, or {ref} to a stakeholder element."
    )
    concerns: list[PurposeEntrySpec] | None = Field(
        default=None,
        description="What the diagram answers: prose, or {ref} to the motivation element stating it.",
    )
