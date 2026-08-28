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

from collections.abc import Callable
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

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

#: The keys an authored grouping uses for its own members and for the boxes it nests. Named here
#: because four places read them — the renderer resolving records, the sync reconciling membership,
#: the delete guard asking who references an entity, and the delete itself pruning what it removed —
#: and a grouping member is an entity reference exactly as an `entity-ids-used` entry is. It went
#: unread by the guard, so deleting an entity referenced only through a grouping was neither blocked
#: nor reported, and the id survived in the file pointing at nothing with `artifact_verify` clean.
GROUPING_MEMBERS_KEY = "entity-ids"
GROUPING_SUBGROUPS_KEY = "groups"


def grouping_member_ids(authored_groupings: object) -> tuple[str, ...]:
    """Every entity id an `authored-groupings` tree names, at any depth, in declared order.

    Boxes nest to any depth, so a reference can sit at any level; asking only the top one is how the
    guard missed it.
    """
    if not isinstance(authored_groupings, list):
        return ()
    found: list[str] = []
    for group in authored_groupings:
        if not isinstance(group, dict):
            continue
        members = group.get(GROUPING_MEMBERS_KEY)
        if isinstance(members, list):
            found.extend(str(member) for member in members)
        found.extend(grouping_member_ids(group.get(GROUPING_SUBGROUPS_KEY)))
    return tuple(found)


@dataclass(frozen=True)
class PrunedGroupings:
    """An `authored-groupings` tree with some members removed, and what came out of it.

    The removals are returned as data rather than reported here: what counts as a member worth
    keeping, and how its loss should be worded, belong to the caller. Two callers prune this tree —
    a sync against the entities the diagram still holds, and a delete against the entities it
    removed — and they had grown two traversals of it under two names.
    """

    groupings: list[dict[str, object]]
    #: `(box label, member id)` for each member pruned, in traversal order.
    dropped_members: tuple[tuple[str, str], ...]
    #: The label of each box that had members and kept none, so it was removed.
    emptied_labels: tuple[str, ...]


def pruned_groupings(
    authored_groupings: object, keep: Callable[[str], bool]
) -> PrunedGroupings:
    """*authored_groupings* with every member *keep* rejects removed, at any depth.

    A box survives if it keeps a member **or** keeps a box: a box that only nests others has no
    members of its own and is not empty. Losing that distinction is what discarded a nested box.
    Keys other than the members and the subgroups are carried through untouched — a rewrite that
    rebuilds a box from a fixed set of keys deletes whatever it did not think of.
    """
    if not isinstance(authored_groupings, list):
        return PrunedGroupings([], (), ())
    kept: list[dict[str, object]] = []
    dropped: list[tuple[str, str]] = []
    emptied: list[str] = []
    for group in authored_groupings:
        if not isinstance(group, dict):
            continue
        label = str(group.get("label", ""))
        members = group.get(GROUPING_MEMBERS_KEY)
        declared = [str(member) for member in (members if isinstance(members, list) else [])]
        surviving = [member for member in declared if keep(member)]
        dropped.extend((label, member) for member in declared if not keep(member))
        nested = pruned_groupings(group.get(GROUPING_SUBGROUPS_KEY), keep)
        dropped.extend(nested.dropped_members)
        emptied.extend(nested.emptied_labels)
        if not surviving and not nested.groupings:
            if declared:
                emptied.append(label)
            continue
        rebuilt = {
            key: value for key, value in group.items()
            if key not in (GROUPING_MEMBERS_KEY, GROUPING_SUBGROUPS_KEY)
        }
        if surviving:
            rebuilt[GROUPING_MEMBERS_KEY] = surviving
        if nested.groupings:
            rebuilt[GROUPING_SUBGROUPS_KEY] = nested.groupings
        kept.append(rebuilt)
    return PrunedGroupings(kept, tuple(dropped), tuple(emptied))
