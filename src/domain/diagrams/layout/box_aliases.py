"""The alias a box carries on a picture, and which kind of box an alias says it is.

A diagram draws four kinds of box and only one of them is an element. The renderer computes the
other three and has to call them something, and what it calls them is the only thing a rendered
picture keeps of which is which: PlantUML draws every one as the same cluster. So the three spellings
are written here and read back here, by one module, and a round-trip test holds the pair.

An alias carrying none of the three markers is not decided here. It is an element's own alias when
the diagram holds an instance under it, and otherwise a box somebody wrote by hand — which is a
grouping an author made. Only the diagram knows which, so `box_kind` is told.
"""

from __future__ import annotations

import re
from collections.abc import Container
from enum import StrEnum

_NOT_ALIAS_SAFE = re.compile(r"[^A-Za-z0-9_]")


class BoxKind(StrEnum):
    """What a box on a picture is, in the words the layout plan uses."""

    #: Every element of one domain, stacked in the ontology's layer order. Computed.
    DOMAIN = "domain"
    #: The elements of one type inside a domain's canvas, boxed when there are several. Computed, and
    #: numbered by a counter, so two renders of a changed diagram need not agree on which is which.
    TYPE = "type"
    #: A grouping the diagram states (`authored-groupings`), or a box in a hand-written body.
    AUTHORED_GROUPING = "authored-grouping"
    #: An element drawn with others inside it, because the model aggregates or composes them.
    ELEMENT = "element"


def domain_box_alias(domain: str) -> str:
    """The alias of the box holding one domain's elements."""
    return f"DOM_{_NOT_ALIAS_SAFE.sub('_', domain)}"


def type_box_alias(namespace: str, ordinal: int) -> str:
    """The alias of the *ordinal*-th type box of one canvas; *namespace* keeps two canvases apart."""
    return f"GRPT_{namespace}{ordinal}"


def authored_grouping_alias(rank: int) -> str:
    """The alias of the *rank*-th authored grouping a body draws, counted in document order."""
    return f"GRPA_{rank}"


def box_kind(alias: str, *, element_aliases: Container[str]) -> BoxKind:
    """Which kind of box *alias* names, given the aliases this diagram draws its instances under.

    The instances are asked first: an element may be called anything, including something that opens
    like a computed box, and the diagram's own statement of what it holds outranks a spelling.
    """
    if alias in element_aliases:
        return BoxKind.ELEMENT
    if alias.startswith("DOM_"):
        return BoxKind.DOMAIN
    if alias.startswith("GRPT_"):
        return BoxKind.TYPE
    # `GRPA_` and everything else: a grouping the diagram states, or one a hand-written body draws.
    return BoxKind.AUTHORED_GROUPING
