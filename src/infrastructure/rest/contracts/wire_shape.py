"""Whether a response DTO admits fields it does not declare.

Closed is the default and the point: an open model publishes ``additionalProperties: true``, which
documents "an object" and promises nothing — the state of 69 of 161 operations before 0.2.0. The
exceptions are named one by one in :mod:`open_models`, with a reason each.

That default was spelled out twenty-six times: every module in this package declared its own
byte-identical ``class _Closed(BaseModel)``. Nothing held them equal, so the package was
inconsistent about its own central convention while the *other* half of the same rule —
:class:`wire_nulls.NullsOmitted` — lived once, with its rationale, and was imported everywhere.
This is that half, in the same shape.

The base carries no reason and no policy beyond closedness, which is why sharing it is safe where
sharing an *open* base was not: :mod:`open_models` records that inheritance was too weak a way to
mark a model open, because a model became open by attaching whichever base was nearest and the
reason in that base's docstring was then simply wrong. There is no such judgement here. Every
response DTO is closed; only the exceptions need a reason, and they are rostered rather than
inherited.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Closed(BaseModel):
    """A response DTO that rejects any field it does not declare.

    A handler returning something undeclared is a validation error rather than a silent addition,
    and the published schema says ``additionalProperties: false`` — so the document, and not the
    frontend's decoder, is the executable statement of what a read contains.
    """

    model_config = ConfigDict(extra="forbid")
