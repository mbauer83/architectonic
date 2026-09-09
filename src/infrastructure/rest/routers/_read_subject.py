"""Which artifact a detail read should serve for an id, and which ids it should not serve at all.

Two kinds of artifact are system-managed and deliberately kept out of every list and every search: a
global artifact reference, which proxies promoted content, and a proposed change, which records an
edit this repository is holding. Neither is part of the model a reader works with, and both were
reachable by
URL — a reference showed a proxy with a description written for nobody, and saving an edit to
promoted content navigated the reader straight into the change it had just recorded.

So the detail read resolves a reference to what it stands for, and refuses every other internal type
by name. In its own module because the alternative was growing `state.py`, which is a shared surface
already at the source-length policy's ceiling, with a rule that belongs to reads.
"""

from __future__ import annotations

from fastapi import HTTPException

from src.application.entity_type_predicates import is_internal_entity_type
from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.rest.routers import state as s


def artifact_a_read_should_serve(artifact_id: str, catalogs: RuntimeCatalogs) -> str:
    """The artifact to read for this id, or a 404 saying why this one is not read directly.

    `catalogs` is a parameter, not a lookup: a router module reading the process's own catalogs is
    one a test cannot override, which `test_runtime_catalogs_have_one_accessor` exists to prevent.
    """
    promoted, via_reference = s.resolve_gar(artifact_id)
    if via_reference:
        if s.get_repo().get_entity(promoted) is None:
            raise HTTPException(
                404,
                f"'{artifact_id}' is an internal reference to '{promoted}'. Read that artifact "
                "instead; references are not part of the model a reader works with.",
            )
        return promoted

    record = s.get_repo().get_entity(artifact_id)
    if record is not None and is_internal_entity_type(record.artifact_type, catalogs.ontology):
        raise HTTPException(
            404,
            f"'{artifact_id}' is a {record.artifact_type}, which this repository manages for itself. "
            "System-managed artifacts are not part of the model a reader works with.",
        )
    return artifact_id
