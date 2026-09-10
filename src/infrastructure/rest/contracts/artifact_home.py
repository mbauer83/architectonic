"""Where an artifact is filed, as a write body says it.

One declaration for all three kinds. The field reached six bodies across three router packages and
the sentence explaining it was written three times over — which is the shape a rule takes just
before its copies stop agreeing about what an absent value means.

Two mixins rather than one, because absence reads differently on each side and that difference is
the whole subtlety: a create with no home named files the artifact in the uncategorized collection,
while an edit with no home named leaves it where it is. A single optional field could not say both.
"""

from __future__ import annotations

from pydantic import BaseModel

from src.domain.repository.groups import UNCATEGORIZED


class FiledOnCreate(BaseModel):
    """A write body that says where the artifact it creates is filed."""

    #: Which collection the artifact is filed in — its *home*. Absent means `uncategorized`, the
    #: same reading the write path and every MCP twin already take.
    group: str | None = None

    def home(self) -> str:
        """The collection to place it in, absent reading as the uncategorized one.

        A method rather than each handler's own `or UNCATEGORIZED`, so what an absent home means is
        stated once for every surface that creates something.
        """
        return self.group or UNCATEGORIZED


class Rehomeable(BaseModel):
    """A write body that can move the artifact it edits."""

    #: Move the artifact to this collection. Absent leaves it where it is; naming `uncategorized`
    #: is how a re-home *out* of a collection is said, because that is a real collection rather
    #: than the absence of one.
    group: str | None = None
