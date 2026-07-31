"""Response contract for the group lifecycle operations.

A group is an axis (`model-project`, `docs`, `diagram-catalog`) plus a slug, and six operations act on
one: create, rename, archive, unarchive, update, delete. They share a reporting shape, and this is it.

Derived from ``write.artifact_write.group_ops``, which is what the handlers serialise — the six
returns there are the whole population, and every field below appears in at least one of them.
"""

from __future__ import annotations

from typing import Literal

from src.infrastructure.gui.contracts.wire_nulls import NullsOmitted


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
