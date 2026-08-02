"""Response contract for the group lifecycle operations.

A group is an axis (`model-project`, `docs`, `diagram-catalog`) plus a slug, and six operations act on
one: create, rename, archive, unarchive, update, delete. They share a reporting shape, and this is it.

Derived from ``write.artifact_write.group_ops``, which is what the handlers serialise — the six
returns there are the whole population, and every field below appears in at least one of them.
"""

from __future__ import annotations

from typing import Literal

from src.infrastructure.rest.contracts.wire_nulls import NullsOmitted


class GroupOperationResponse(NullsOmitted):
    """What a group operation did.

    ``action`` reports it in the past tense, because the response describes a completed change rather
    than the request that asked for it — a caller replaying a log needs to know what happened, and
    "archive" does not say whether it did.

    **One closed model rather than six, discriminated on ``action``.** A union per action would be
    more precise about which extra field accompanies which verb, and it would cost six models and a
    discriminated wrapper to express three optional fields. The imprecision it buys back is small and
    named: ``id`` accompanies a create, ``old_slug`` a rename, ``files_removed`` a delete. A seventh
    action, or an extra that is not obviously tied to one verb, is the point at which the union earns
    its keep.

    **The field names are the producer's, not better ones.** ``id`` would read better as ``group_id``,
    but this contract is a projection of ``group_ops``' output rather than an independent description
    of it: a DTO that renames what it receives is a closed model that rejects every real response, and
    that mistake has already cost a 500 on the entity read once this release.
    ``test_group_operation_contract.py`` holds the two field sets equal.

    Unset extras are **absent**, not null — the null-omitting policy — so a client reading
    ``files_removed`` learns "this was not a delete" from the key's absence rather than having to
    distinguish null from zero. Zero files removed is a real outcome and must not look like "not
    applicable".
    """

    action: Literal["created", "renamed", "archived", "unarchived", "updated", "deleted"]
    axis: str
    slug: str

    #: The registry id assigned by a create.
    id: str | None = None
    #: What a rename renamed *from*; the new slug is ``slug``.
    old_slug: str | None = None
    #: How many files a delete removed. Absent unless the action was a delete; zero is meaningful.
    files_removed: int | None = None

    # ── A model-project delete cascades, and says how far ────────────────────────────────────────
    #
    # Deleting a model-project is not deleting a registry row: it removes the entities and connections
    # the project owned, deletes connections *into* them from elsewhere, and rewrites the diagrams that
    # referenced them. A caller that got back only `action: deleted` would have no way to know a
    # neighbouring project's diagram had just changed under it, so these are part of the answer rather
    # than logging.
    #
    # They arrive here through a projection in the router, because the write layer's
    # `cascade_delete_model_project` is shared with the MCP tools and the CLI and answers in its own
    # envelope. Absent — not zero — for any delete that did not cascade, per the null-omitting policy:
    # "no entities were owned" and "this was not a project delete" are different facts.
    #: Entities and connections the project owned, removed with it.
    owned_deleted: int | None = None
    #: Connections from elsewhere *into* the deleted project, removed because their target went away.
    foreign_connections_deleted: int | None = None
    #: Diagrams elsewhere rewritten because they referenced something the delete removed.
    diagrams_updated: int | None = None
    #: What the cascade could not do cleanly. Empty is meaningful; absent means no cascade ran.
    warnings: list[str] | None = None
