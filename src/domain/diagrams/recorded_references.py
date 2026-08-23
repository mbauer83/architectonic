"""When a diagram's recorded references disagree with the picture, and which side is wrong.

`connection-ids-used` is a claim about the body: *these are the relations this view draws*. It is
also a query surface — which views show this connection — so a wrong entry is a wrong answer about
the model, and impact analysis reads it.

Two callers need the same judgement and must not each spell it. The write path applies it to decide
what survives a body replacement; verification applies it to report an entry the stored body does not
draw. A reconcile that dropped a reference the verifier would have kept, or the reverse, is the two
disagreeing about the same picture.

**The judgement is deliberately one-sided.** Silence is not evidence: a body may draw something the
reader cannot name, so an unmatched reference is contradicted only where the body positively says
otherwise — both endpoints are among the entities it declares, so it had the vocabulary to draw the
relation, and the pair is not one the reader could not decide between. Anything else is kept, and
kept quietly.
"""

from __future__ import annotations

from collections.abc import Set as AbstractSet

from src.domain.artifact_id import MalformedArtifactIdError, parse_connection_id, stable_conn_id


def reference_endpoints(reference: str) -> set[str] | None:
    """The pair a connection id names, in the form ids are compared in — or None if unreadable.

    Read through `parse_connection_id`, which owns the `source---target@@type` form and already
    canonicalises both endpoints. Spelling that separator here instead is what the register of
    one-reader syntaxes refuses, and the reason is on the record: a plain `find("---")` matched the
    hyphen inside a slug.
    """
    try:
        key = parse_connection_id(reference)
    except MalformedArtifactIdError:
        return None
    return {key.src_short, key.tgt_short}


def body_contradicts_reference(
    reference: str,
    *,
    declared_entities: AbstractSet[str],
    drawn_stable: AbstractSet[str],
    undecided_pairs: AbstractSet[frozenset[str]] = frozenset(),
) -> bool:
    """Whether the body positively says it does not draw this connection.

    *declared_entities* and *drawn_stable* are in stable form — `stable_id` for entities,
    `stable_conn_id` for connections. *undecided_pairs* are the endpoint pairs where a drawn glyph
    fits more than one connection, so the reader could not name which.
    """
    if stable_conn_id(reference) in drawn_stable:
        return False
    endpoints = reference_endpoints(reference)
    if endpoints is None or not endpoints <= set(declared_entities):
        return False
    return frozenset(endpoints) not in undecided_pairs
