"""The wire form of how an artifact stands relative to the enterprise baseline.

`src/domain/baseline_standing.py` is the value; this is its contract. Two arms discriminated on
`kind`, so a client matches exhaustively on the same two cases the server does rather than inferring
them from which fields happen to be present.

**Non-optional wherever it is carried, and that is the whole point.** `is_global` is declared
`bool | None = None` two fields away, and two of its three hit serialisers omit it — type-legally,
because the contract permits absence. A reader cannot then tell "not global" from "nobody said". For
this value that distinction is the answer: absence would read as the enterprise baseline, which is
precisely the reading that makes a pending local change invisible.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from src.domain.baseline_standing import BASELINE_KIND, PROPOSED_KIND
from src.infrastructure.rest.contracts.wire_shape import Closed


class EnterpriseBaselineStanding(Closed):
    """What is shown is exactly the enterprise baseline."""

    kind: Literal["enterprise-baseline"] = BASELINE_KIND


class ProposedStanding(Closed):
    """The baseline plus local changes that have not been accepted upstream."""

    kind: Literal["proposed"] = PROPOSED_KIND
    #: Every live change against this artifact, so a reader can open them.
    proposal_ids: list[str]
    #: Which parts differ — the question a boolean could not answer, and the reason this is a union.
    changed_fields: list[str]
    #: What the artifact was when the changes were written.
    base_revision: str
    #: Derived on read, never stored: whether the changes still apply to the baseline they name.
    condition: Literal["current", "stale", "conflicting"]


#: One artifact's standing on the wire. `Field(discriminator=...)` rather than a bare union so the
#: published schema is a `oneOf` with a mapping, and a generated client gets the same exhaustive
#: match the server has instead of a guess at which arm it received.
BaselineStandingContract = Annotated[
    EnterpriseBaselineStanding | ProposedStanding, Field(discriminator="kind")
]
