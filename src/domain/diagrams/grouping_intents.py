"""What an editor means for a diagram's groupings — nest these, unnest those, create a box, delete one —
applied to its ``authored-groupings``.

```json
[
  {"intent": "nest", "keys": ["APP@1712870400.xVrBYD"], "grouping": "g-a1B2c3"},
  {"intent": "unnest", "keys": ["APP@1712870400.xVrBYD"]},
  {"intent": "create_grouping", "label": "Front office", "keys": ["…"], "parent": "g-a1B2c3"},
  {"intent": "delete_grouping", "grouping": "g-a1B2c3"}
]
```

Membership is diagram content, not layout, so these change the groupings statement; what the layout
must do to keep matching it is told by `Regrouped.refit`: the boxes whose members changed, which are
fitted round their members again. A listed grouping holds an instance exclusively: nesting an instance
takes it out of every other listed grouping, as a drawing is drawn in one listed box only
(`grouping_membership`). A ruled grouping selects its members by its rule, so it neither gains nor
loses one by listing, and an intent that would make it do so is refused.

Entry shape and ids are `authored_groupings`'s; this module reads them through it.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.domain.artifact_id import canonical_entity_key
from src.domain.diagrams.authored_groupings import (
    GROUPING_ID_KEY,
    MalformedGroupings,
    grouping_ids,
    rule_of,
    walk_groupings,
    with_grouping_ids,
)
from src.domain.diagrams.recorded_references import GROUPING_MEMBERS_KEY, GROUPING_SUBGROUPS_KEY


@dataclass(frozen=True)
class Nest:
    """The instances *keys* join the listed grouping *grouping*, and leave every other listed grouping."""

    keys: tuple[str, ...]
    grouping: str


@dataclass(frozen=True)
class Unnest:
    """The instances *keys* leave their listed grouping for its parent, or for the canvas at the top."""

    keys: tuple[str, ...]


@dataclass(frozen=True)
class CreateGrouping:
    """A new listed grouping, labelled *label*, holding *keys*, inside *parent* or at the top."""

    label: str
    keys: tuple[str, ...]
    parent: str | None = None


@dataclass(frozen=True)
class DeleteGrouping:
    """The grouping goes; its members and subgroups go to its parent, or to the canvas at the top."""

    grouping: str


type GroupingIntent = Nest | Unnest | CreateGrouping | DeleteGrouping


@dataclass(frozen=True)
class Regrouped:
    """The groupings after an intent, and the ids of the boxes the layout must fit again or drop."""

    groupings: list[dict[str, object]]
    #: Groupings whose members changed, with every grouping around them: their stated boxes no longer
    #: fit what they hold.
    refit: frozenset[str]
    #: Groupings the intent removed; their layout entries name nothing now.
    removed: frozenset[str]


@dataclass(frozen=True)
class _Found:
    entry: dict[str, object]
    parent: dict[str, object] | None
    siblings: list[object]


def _find(groupings: list[object], grouping_id: str) -> _Found:
    """The grouping *grouping_id*, the grouping around it, and the list it sits in — found by the one walk
    of a groupings tree (`walk_groupings`)."""
    parents: dict[tuple[int, ...], dict[str, object]] = {}
    for trail, entry in walk_groupings(groupings):
        parents[trail] = entry
        if entry.get(GROUPING_ID_KEY) == grouping_id:
            parent = parents.get(trail[: len(trail) - 1])
            siblings = parent.get(GROUPING_SUBGROUPS_KEY) if parent is not None else groupings
            assert isinstance(siblings, list)
            return _Found(entry, parent, siblings)
    raise MalformedGroupings(f"This diagram has no grouping '{grouping_id}'.")


def _label(entry: Mapping[str, object]) -> str:
    return f"'{entry.get('label') or entry.get(GROUPING_ID_KEY)}'"


def _refuse_if_ruled(entry: Mapping[str, object], doing: str) -> None:
    if rule_of(entry) is not None:
        raise MalformedGroupings(
            f"The grouping {_label(entry)} selects its members by its rule, so it cannot {doing} by listing; "
            "change its rule, or nest them in a listed grouping."
        )


def _members(entry: Mapping[str, object]) -> list[str]:
    raw = entry.get(GROUPING_MEMBERS_KEY)
    return [str(member) for member in raw] if isinstance(raw, list) else []


def _join(entry: dict[str, object], keys: Sequence[str]) -> None:
    held = {canonical_entity_key(member) for member in _members(entry)}
    entry[GROUPING_MEMBERS_KEY] = _members(entry) + [key for key in keys if canonical_entity_key(key) not in held]


def _withdrawn(groupings: list[object], keys: Sequence[str]) -> dict[str, dict[str, object]]:
    """Take *keys* out of every listed grouping; the groupings each left, by key."""
    leaving = {canonical_entity_key(key): key for key in keys}
    left: dict[str, dict[str, object]] = {}
    for _trail, entry in walk_groupings(groupings):
        members = _members(entry)
        kept = [member for member in members if canonical_entity_key(member) not in leaving]
        if len(kept) == len(members):
            continue
        left.update({leaving[canonical_entity_key(m)]: entry for m in members if canonical_entity_key(m) in leaving})
        if kept:
            entry[GROUPING_MEMBERS_KEY] = kept
        else:
            entry.pop(GROUPING_MEMBERS_KEY, None)
    return left


def _without_emptied(groupings: list[object], emptied: set[str]) -> tuple[list[object], set[str]]:
    """*groupings* less the listed ones among *emptied* that now hold nothing; and the ids so removed.

    As pruning does (`pruned_groupings`): a listed box left with no member and no subgroup draws nothing.
    """
    removed: set[str] = set()

    def kept(level: list[object]) -> list[object]:
        result: list[object] = []
        for entry in level:
            if isinstance(entry, dict):
                nested = entry.get(GROUPING_SUBGROUPS_KEY)
                if isinstance(nested, list):
                    entry[GROUPING_SUBGROUPS_KEY] = kept(nested)
                    if not entry[GROUPING_SUBGROUPS_KEY]:
                        entry.pop(GROUPING_SUBGROUPS_KEY)
                grouping_id = str(entry.get(GROUPING_ID_KEY, ""))
                hollow = not _members(entry) and not entry.get(GROUPING_SUBGROUPS_KEY) and rule_of(entry) is None
                if hollow and grouping_id in emptied:
                    removed.add(grouping_id)
                    continue
            result.append(entry)
        return result

    return kept(groupings), removed


def _enclosing(groupings: object, ids: set[str]) -> frozenset[str]:
    """*ids* with the id of every grouping around one of them."""
    by_trail = {trail: str(entry.get(GROUPING_ID_KEY, "")) for trail, entry in walk_groupings(groupings)}
    parent_of = {
        grouping_id: by_trail[trail[: len(trail) - 1]] for trail, grouping_id in by_trail.items() if len(trail) > 1
    }
    found = set(ids)
    for grouping_id in ids:
        while (grouping_id := parent_of.get(grouping_id, "")) and grouping_id not in found:
            found.add(grouping_id)
    return frozenset(found)


def _holder(groupings: list[object], key: str) -> dict[str, object] | None:
    """The listed grouping that holds *key*: the first to list it, as membership is settled."""
    wanted = canonical_entity_key(key)
    return next(
        (entry for _trail, entry in walk_groupings(groupings)
         if any(canonical_entity_key(member) == wanted for member in _members(entry))),
        None,
    )


def _moved(groupings: list[object], keys: Sequence[str], into: dict[str, object] | None) -> set[str]:
    """*keys* leave every listed grouping and join *into* (None: the canvas); the ids whose members changed.

    A ruled grouping lists no members, so nothing is taken out of one here.
    """
    if into is not None:
        _refuse_if_ruled(into, "gain members")
    left = _withdrawn(groupings, keys)
    if into is not None:
        _join(into, keys)
    touched = {str(entry.get(GROUPING_ID_KEY, "")) for entry in left.values()}
    return touched | ({str(into.get(GROUPING_ID_KEY, ""))} if into is not None else set())


def _unnested(tree: list[object], keys: Sequence[str]) -> set[str]:
    touched: set[str] = set()
    for key in keys:
        holder = _holder(tree, key)
        if holder is None:
            raise MalformedGroupings(
                f"{key} is in no listed grouping, so there is nothing to unnest it from; a grouping that "
                "selects its members by its rule cannot lose members by listing."
            )
        touched |= _moved(tree, [key], _find(tree, str(holder.get(GROUPING_ID_KEY))).parent)
    return touched


def _created(tree: list[object], intent: CreateGrouping) -> set[str]:
    parent = _find(tree, intent.parent).entry if intent.parent is not None else None
    touched = _moved(tree, intent.keys, None)
    if parent is not None:
        nested = parent.get(GROUPING_SUBGROUPS_KEY)
        parent[GROUPING_SUBGROUPS_KEY] = level = nested if isinstance(nested, list) else []
        touched.add(str(parent.get(GROUPING_ID_KEY, "")))
    else:
        level = tree
    level.append({"label": intent.label, GROUPING_MEMBERS_KEY: list(intent.keys)})
    return touched


def _deleted(tree: list[object], grouping_id: str) -> set[str]:
    found = _find(tree, grouping_id)
    members, nested = _members(found.entry), found.entry.get(GROUPING_SUBGROUPS_KEY)
    if found.parent is not None and members:
        _refuse_if_ruled(found.parent, "gain members")
        _join(found.parent, members)
    at = next(index for index, entry in enumerate(found.siblings) if entry is found.entry)
    found.siblings[at:at + 1] = list(nested) if isinstance(nested, list) else []
    return {str(found.parent.get(GROUPING_ID_KEY, ""))} if found.parent is not None else set()


def regrouped(intent: GroupingIntent, groupings: Sequence[object], *, diagram_id: str) -> Regrouped:
    """*intent* applied to *groupings*, which are left as they are. Raises `MalformedGroupings`, saying why,
    for an intent that names no grouping of the diagram or would list members in a ruled one.

    *diagram_id* seeds the id a created grouping is given (`with_grouping_ids`).
    """
    tree: list[object] = copy.deepcopy(list(groupings))
    before = set(grouping_ids(tree))
    removed: set[str] = set()
    match intent:
        case Nest(keys=keys, grouping=grouping_id):
            touched = _moved(tree, keys, _find(tree, grouping_id).entry)
        case Unnest(keys=keys):
            touched = _unnested(tree, keys)
        case CreateGrouping():
            touched = _created(tree, intent)
        case DeleteGrouping(grouping=grouping_id):
            touched = _deleted(tree, grouping_id)
            removed.add(grouping_id)
    tree, emptied = _without_emptied(tree, touched)
    identified = with_grouping_ids(tree, diagram_id=diagram_id)
    touched |= set(grouping_ids(identified)) - before  # the grouping a create made
    removed |= emptied
    return Regrouped(identified, _enclosing(identified, touched - removed) - removed, frozenset(removed))
