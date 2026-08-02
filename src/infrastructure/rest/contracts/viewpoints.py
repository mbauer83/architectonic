"""Response contracts for the viewpoint authoring surface.

A viewpoint's slug is a *natural* key the author chooses, and it is part of the definition record
itself — unlike an artifact id, which the server mints. So a ``PUT`` body legitimately carries the
slug inside its definition: that is the resource's own field, not a second place to say which
resource the request addresses. The handler still refuses a definition whose slug disagrees with
the path, because two disagreeing spellings have no defensible winner.

A committed deletion answers 204 and says nothing. Its *dry run* answers 200 with the same
:class:`ViewpointPersistResponse` a create or replace returns — a deletion plan is a persist result
whose ``action`` is ``delete``, and giving it a second identical DTO would only mean two places to
change. A deletion *refused* because diagrams still pin the definition is not a success with
``ok: false``; it is a ``viewpoint_referenced`` error carrying the referencers, so the client can
offer links rather than parse prose.
"""

from __future__ import annotations

from typing import Literal

from src.infrastructure.rest.contracts.wire_nulls import NullsOmitted
from src.infrastructure.rest.contracts.wire_shape import Closed


class ViewpointValidationIssueDto(Closed):
    """One validation finding against a definition, addressed at the field that caused it.

    ``expected``/``found`` are always serialized, as null where the finding has no comparison to
    report: a client that had to distinguish "absent" from "null" would be reading a fourth state
    that never occurs.

    Which is why neither carries a default. They did, and the document then published both as
    *optional* — contradicting the paragraph above it, and disagreeing with the frontend's decoder,
    which requires them present and nullable. A default here describes the field's value; it is the
    absence of one that describes its presence.
    """

    severity: Literal["error", "warning"]
    code: str
    path: str
    message: str
    expected: str | None
    found: str | None


class ViewpointReferencerDto(Closed):
    """A diagram or matrix whose frontmatter pins this viewpoint."""

    artifact_id: str
    target_kind: Literal["diagram", "matrix"]


class ViewpointPersistResponse(Closed):
    """The outcome of creating or replacing a definition — or of the dry run that previews it.

    ``ok`` with ``issues`` rather than an error status: the editor's preview is a *successful*
    validation report, and the same body has to describe both the plan and the committed write for
    the two to be comparable.
    """

    ok: bool
    action: Literal["create", "edit", "delete"]
    slug: str
    #: Present on every answer, and null where the action has no version to report — a deletion, or
    #: a refused create. It carried ``= None``, which published it as *optional*, but
    #: ``PersistResult.as_answer`` emits the key unconditionally: the default described the field's
    #: value, not its presence, and the client's decoder had it right.
    version: int | None
    dry_run: bool
    issues: list[ViewpointValidationIssueDto] = []
    referencers: list[ViewpointReferencerDto] = []


class ViewpointReferencerListResponse(Closed):
    """Every diagram or matrix pinning one viewpoint definition.

    The management view reads this before offering a semantic edit: a version bump leaves every
    referencer pinned to a version that no longer describes the definition, and the warning has to
    name them.
    """

    referencers: list[ViewpointReferencerDto]


class ViewpointPinsResponse(NullsOmitted):
    """The pinned definition slugs, and any that were dropped for no longer existing.

    ``pruned`` is reported by the read and **absent** from the write. A pin whose definition has since
    left the effective catalog is silently dropped, and a list that just quietly shrank would leave the
    user wondering what they had pinned; the read says so. The write prunes nothing, so it has nothing
    to report — and absent rather than empty, because an empty list would read as "nothing was dropped
    this time" from an operation that never drops anything.

    Null-omitting for that reason: the client reads ``pruned`` as absent-or-value
    (``Schema.optional``), so sending null would fail its decode and lose the whole response.
    """

    slugs: list[str]
    pruned: list[str] | None = None


class ViewpointApplicationResponse(NullsOmitted):
    """The viewpoint a diagram or matrix pins, as its frontmatter states it.

    ``version`` is the *pinned* version, not the definition's current one: the point of pinning is
    that the definition can move on and the artifact keeps saying which version it was drawn
    against. The projection read is where staleness is reported.

    ``enforcement_override`` is absent where the artifact accepts the repository default; a value
    here is a deliberate per-artifact departure from it — which is why it is absent-or-value and not
    nullable: null would be a third state the frontmatter cannot express.
    """

    slug: str
    version: int
    enforcement_override: Literal["off", "warn", "ghost"] | None = None
    #: Values for the definition's declared parameters, bound at projection time. An open map — the
    #: keys are the definition's parameter names, which are the definition's to choose — with the
    #: same closed scalar value space binding produces.
    derivation_params: dict[str, bool | int | float | str | list[str]] | None = None
