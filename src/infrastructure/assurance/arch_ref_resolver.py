"""Which assurance→architecture references no longer resolve.

Assurance nodes cite architecture artifact ids. The architecture model evolves on its own,
so those citations can dangle — the cited entity is renamed away, superseded or deleted,
and an analysis silently comes to rest on something that is no longer there. Finding those
is a modelling gap of exactly the kind the assurance capability exists to surface, so it
belongs in the verifier's output rather than in a separate maintenance action.

Read-only by design. An earlier version also stamped `resolved_at` on every reference it
could resolve, which is why it never found a home: the natural caller is `assurance_verify`,
a read tool, and a read tool that writes to the confidential store is not one. Nothing ever
read `resolved_at` back — no query filtered on it, no tool returned it, no surface showed
it — so the write bought nothing and cost the function its only plausible caller. If a
"last confirmed present" timestamp is wanted later, it belongs in an explicit reconcile
*write* tool, alongside `assurance_reconcile_aibom`, and only once something reads it.

The one-way rule holds either way: this looks architecture ids up in the architecture
store, and never writes an assurance reference into an architecture artifact.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.application.assurance.ports import ConfidentialAssuranceStore
    from src.domain.ontology_representation.artifact_types import EntityRecord

logger = logging.getLogger(__name__)


class ArchitectureEntityLookup(Protocol):
    """The one read this needs: does an architecture entity with this id exist?

    Narrow on purpose, as elsewhere in this package. Stated as the full artifact-lookup
    port, every caller would have to supply a whole repository — and a test would have to
    fake three reads that play no part in the answer.
    """

    def get_entity(self, artifact_id: str) -> "EntityRecord | None": ...


def dangling_arch_refs(
    assurance_store: ConfidentialAssuranceStore,
    artifact_store: ArchitectureEntityLookup,
) -> dict[str, object]:
    """Assurance references whose architecture artifact cannot be found.

    Never raises and never writes. A locked store reports itself as locked rather than as
    having no dangling references — the two are not the same answer, and reporting the
    second for the first would say a store nobody can read is in good order.
    """
    if not assurance_store.is_unlocked():
        return {"store": "locked", "checked": 0, "dangling": 0, "dangling_refs": []}

    refs = assurance_store.list_arch_refs()
    dangling: list[dict[str, object]] = []

    for ref in refs:
        arch_id = str(ref["arch_artifact_id"])
        if artifact_store.get_entity(arch_id) is None:
            dangling.append(ref)
            logger.debug(
                "Dangling assurance→arch ref: %s → %s (%s)",
                ref["assurance_node_id"],
                arch_id,
                ref["ref_type"],
            )

    if dangling:
        logger.info(
            "%d assurance→architecture references no longer resolve (informational)",
            len(dangling),
        )

    return {
        "store": "unlocked",
        "checked": len(refs),
        "dangling": len(dangling),
        "dangling_refs": dangling,
    }
