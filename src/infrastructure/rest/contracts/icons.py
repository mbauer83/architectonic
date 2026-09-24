"""Response contracts of the icon library.

An icon is described by what a picker chooses by — its name, what it applies to, its tags, whose mark
it is — and never carries its picture: that is its own subresource, served as bytes.
"""

from __future__ import annotations

from typing import Literal

from src.infrastructure.rest.contracts.baseline_standing import BaselineStandingContract
from src.infrastructure.rest.contracts.wire_shape import Closed


class IconSummary(Closed):
    artifact_id: str
    name: str
    attribution: str
    #: Type and specialization names it may be shown on; empty means any element.
    applies_to: list[str]
    default_style: Literal["badge", "figure"]
    tags: list[str]
    status: Literal["active", "retired"]
    source_format: Literal["svg", "png", "jpeg", "webp"]
    width: int
    height: int
    render_digest: str
    #: Held by the enterprise library rather than this engagement's.
    is_global: bool
    #: How it stands against the enterprise baseline. Nothing is proposed against an icon — its picture
    #: never changes under its id — so this is the baseline, stated rather than left for a reader to infer.
    baseline_standing: BaselineStandingContract


class IconListResponse(Closed):
    """The icons a picker offers for the question asked, and how many there are."""

    total: int
    items: list[IconSummary]
