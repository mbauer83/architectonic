"""Where an artifact is filed, as a write body says it — for REST and MCP alike.

One declaration for all three kinds. The field reached six bodies across three router packages and
the sentence explaining it was written three times over — which is the shape a rule takes just
before its copies stop agreeing about what an absent value means.

Two mixins rather than one, because absence reads differently on each side and that difference is
the whole subtlety: a create with no home named files the artifact in the uncategorized collection,
while an edit with no home named leaves it where it is. A single optional field could not say both.

Below both transports, as `candidate_wire` and `diagram_layout_wire` are: the diagram replacement that
REST and MCP share takes `Rehomeable`, so it may not live among one transport's contracts.

`PathComponent` is here too, the type every such field is declared with: a collection's slug names its
directory, so `group: "../../elsewhere"` filed an artifact outside the repository. It publishes the
rule (`repository_confinement.SEGMENT_PATTERN`) as the field's pattern, so the request is refused
before a handler runs and the published schema states what is accepted.
`tests/architecture/test_every_location_parameter_is_confined.py` holds every such field to it.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, StringConstraints

from src.application.repository_confinement import SEGMENT_PATTERN
from src.domain.repository.groups import UNCATEGORIZED

#: One path component: a collection's slug, a file name.
PathComponent = Annotated[str, StringConstraints(pattern=SEGMENT_PATTERN)]


class FiledOnCreate(BaseModel):
    """A write body that says where the artifact it creates is filed."""

    #: Which collection the artifact is filed in — its *home*. Absent means `uncategorized`, the
    #: same reading the write path and every MCP twin already take.
    group: PathComponent | None = None

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
    group: PathComponent | None = None
