"""The assurance entity types a caller may create — defined once.

The assurance ontology module declares these types, but the layering rules keep the application
layer from reading an ontology package, so the vocabulary is stated here as the domain fact it is
and a conformance test pins it to the module's declaration. That test is the point of this module:
the list previously lived inline in the write use case as a hand-copied mirror of the tool
description, unguarded, and it drifted — `failure-mode` was declared by the ontology, accepted by
the store, rendered by every read surface, and rejected at the one place that creates it. Nothing
failed loudly; the type was simply uncreatable.

This is the same failure the guideword vocabularies were consolidated to stop, and it is worth
naming the shape: a vocabulary copied into a validation gate goes stale silently, because the gate
only ever says no to the value that is missing from it. The id prefixes below were a second copy of
the same declaration and had drifted in a second way — silently, via a fallback.
"""

from __future__ import annotations

#: The prefix each node type's ids carry. Stated here for the same reason as the type list, and
#: pinned to the ontology by the same test — the store adapters kept their own copy, it never gained
#: an entry for two of the types, and the fallback quietly invented a prefix from the first three
#: letters of the type name. That is worse than an error: an id is persisted, so a made-up prefix is
#: permanent, and nothing about a wrong one looks wrong.
NODE_ID_PREFIXES: dict[str, str] = {
    "loss": "LSS",
    "hazard": "HAZ",
    "control-structure-node": "CSN",
    "control-action": "CAC",
    "unsafe-control-action": "UCA",
    "loss-scenario": "LOS",
    "assurance-constraint": "ACN",
    "failure-mode": "FMD",
    "evidence": "EVD",
    "risk": "RSK",
    "incident": "INC",
    "corrective-action": "CRA",
    "obligation": "OBL",
}

CREATABLE_NODE_TYPES: frozenset[str] = frozenset(NODE_ID_PREFIXES)


#: Fields a caller may change on an existing node.
#:
#: One definition, imported by every storage backend. It was four hand-kept copies — one per
#: adapter — and each silently dropped anything absent from its own set. That is how `analysis_id`
#: came to be unwritable: the write surface accepted it, the store discarded it, the response said
#: the node was updated, and 26 nodes in the live store have no author recorded as a result.
#:
#: `analysis_id` is here because *re-attributing* a node has to be possible. Authorship is fixed in
#: the sense that nothing should change it casually, not in the sense that a node authored before
#: analyses existed must stay orphaned forever.
#:
#: `node_type` is deliberately absent: the type decides the node's id prefix, which is already
#: persisted, so changing it would leave an id that lies about what it names.
NODE_UPDATABLE: frozenset[str] = frozenset({
    "name",
    "status",
    "tlp",
    "concern_class",
    "disposition",
    "uca_type",
    "failure_type",
    "mode",
    "binding_status",
    "node_role",
    "content_text",
    "analysis_id",
})
