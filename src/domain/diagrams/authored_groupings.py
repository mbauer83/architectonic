"""A diagram's groupings: what an entry may say, its identity, and the rule key of a box not written down.

A grouping holds either the members it lists (``entity-ids``) or a rule that selects them
(``rule``): a domain, or an element type within its parent. Groupings of either kind nest under
``groups``. Every entry carries a stable ``id`` of its own, which is what a layout addresses it by;
a box the renderer computes and no entry states is addressed by its rule — ``rule:domain=business``,
``rule:domain=business/type=business-service`` — never by a renderer's counter.

This module is the one reading of an entry's shape and of a rule key. Who is *in* a grouping is
`grouping_membership`'s question.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, get_args

from src.domain.diagrams.recorded_references import (
    GROUPING_MEMBERS_KEY,
    GROUPING_RULE_KEY,
    GROUPING_SUBGROUPS_KEY,
)
from src.domain.diagrams.relation_key import UPGRADE_SENTENCE

GROUPING_ID_KEY = "id"
_ENTRY_KEYS = frozenset(
    {GROUPING_ID_KEY, "label", "stereotype", GROUPING_MEMBERS_KEY, GROUPING_RULE_KEY, GROUPING_SUBGROUPS_KEY}
)

RuleKind = Literal["domain", "type"]
_RULE_KINDS: tuple[str, ...] = get_args(RuleKind)

_GROUPING_ID = re.compile(r"g-[A-Za-z0-9]{4,12}")
_RULE_VALUE = re.compile(r"[a-z0-9][a-z0-9_-]*")
_RULE_KEY_PREFIX = "rule:"
_ID_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


class MalformedGroupings(ValueError):
    """An ``authored-groupings`` statement that cannot be read, with the reason in a sentence."""


@dataclass(frozen=True)
class GroupingRule:
    """What selects a ruled grouping's members: one domain, or one element type within its parent."""

    kind: RuleKind
    value: str

    @property
    def text(self) -> str:
        return f"{self.kind}={self.value}"


def _where(trail: Sequence[int]) -> str:
    return "authored-groupings" + "".join(f"[{index}]" for index in trail)


def rule_of(entry: Mapping[str, object]) -> GroupingRule | None:
    """The rule *entry* states, or None for a listed grouping. Refuses a rule that is not one."""
    raw = entry.get(GROUPING_RULE_KEY)
    if raw is None:
        return None
    if not isinstance(raw, Mapping) or len(raw) != 1:
        raise MalformedGroupings(
            "A grouping's rule names exactly one of 'domain' or 'type', as in {domain: business}."
        )
    (kind, value), = raw.items()
    if kind not in _RULE_KINDS or not isinstance(value, str) or not _RULE_VALUE.fullmatch(value):
        raise MalformedGroupings(
            f"A grouping's rule is {{domain: <name>}} or {{type: <element type>}}; got {{{kind}: {value!r}}}."
        )
    return GroupingRule("domain" if kind == "domain" else "type", value)


def walk_groupings(
    groupings: object, trail: tuple[int, ...] = ()
) -> Iterator[tuple[tuple[int, ...], dict[str, object]]]:
    """Every entry of a groupings tree with where it sits, parents before their subgroups."""
    if not isinstance(groupings, list):
        return
    for index, entry in enumerate(groupings):
        if isinstance(entry, dict):
            yield (*trail, index), entry
            yield from walk_groupings(entry.get(GROUPING_SUBGROUPS_KEY), (*trail, index))


def grouping_ids(groupings: object) -> tuple[str, ...]:
    """The id of every entry that states one, at any depth, in document order."""
    return tuple(
        str(entry[GROUPING_ID_KEY]) for _trail, entry in walk_groupings(groupings) if entry.get(GROUPING_ID_KEY)
    )


NOT_YET_UPGRADED = (
    "This diagram's groupings have no ids: it is stored in the format from before a grouping had an "
    f"identity of its own, and only the repository upgrade converts it. {UPGRADE_SENTENCE}"
)


def stored_before_groupings_had_ids(groupings: object) -> bool:
    """Whether a *stored* groupings value holds an entry with no id — the earlier format.

    Asked of what a file holds, never of what a caller states: a grouping a caller states now without
    an id is new and is given one by the write, while one a file holds without an id is content of
    an earlier format, which is the upgrade's to convert — rehearsed, reported, and only for the
    tiers a deployment owns.
    """
    return any(not entry.get(GROUPING_ID_KEY) for _trail, entry in walk_groupings(groupings))


def states_a_ruled_grouping(groupings: object) -> bool:
    """Whether any entry is ruled — which is what makes the stated groupings the whole list of boxes."""
    return any(GROUPING_RULE_KEY in entry for _trail, entry in walk_groupings(groupings))


def check_groupings(groupings: object) -> list[str]:
    """Everything wrong with a stored ``authored-groupings`` value, one sentence each. Empty when sound."""
    if groupings is None:
        return []
    if not isinstance(groupings, list):
        return ["authored-groupings is a list of groupings."]
    problems: list[str] = []
    seen: set[str] = set()
    for trail, entry in _every_item(groupings):
        where = _where(trail)
        if not isinstance(entry, dict):
            problems.append(f"{where} is not a grouping: expected a mapping.")
            continue
        problems.extend(_entry_problems(entry, where))
        grouping_id = entry.get(GROUPING_ID_KEY)
        if isinstance(grouping_id, str) and grouping_id in seen:
            problems.append(f"{where} repeats the grouping id '{grouping_id}'; every grouping has its own.")
        if isinstance(grouping_id, str):
            seen.add(grouping_id)
    return problems


def _every_item(groupings: list[object], trail: tuple[int, ...] = ()) -> Iterator[tuple[tuple[int, ...], object]]:
    for index, entry in enumerate(groupings):
        yield (*trail, index), entry
        nested = entry.get(GROUPING_SUBGROUPS_KEY) if isinstance(entry, dict) else None
        if isinstance(nested, list):
            yield from _every_item(nested, (*trail, index))


def _entry_problems(entry: Mapping[str, object], where: str) -> list[str]:
    problems: list[str] = []
    unknown = sorted(str(key) for key in entry if key not in _ENTRY_KEYS)
    if unknown:
        problems.append(f"{where} states {', '.join(unknown)}, which a grouping does not hold.")
    grouping_id = entry.get(GROUPING_ID_KEY)
    if grouping_id is None:
        problems.append(f"{where} has no id; every grouping carries a stable one. {UPGRADE_SENTENCE}")
    elif not isinstance(grouping_id, str) or not _GROUPING_ID.fullmatch(grouping_id):
        problems.append(f"{where} has the id {grouping_id!r}; a grouping id reads 'g-' and 4 to 12 letters or digits.")
    if GROUPING_RULE_KEY in entry and entry.get(GROUPING_MEMBERS_KEY):
        problems.append(f"{where} states both a rule and a list of members; a grouping is listed or ruled.")
    try:
        rule_of(entry)
    except MalformedGroupings as refusal:
        problems.append(f"{where}: {refusal}")
    members = entry.get(GROUPING_MEMBERS_KEY)
    if members is not None and not isinstance(members, list):
        problems.append(f"{where}: '{GROUPING_MEMBERS_KEY}' is a list of entity or occurrence ids.")
    nested = entry.get(GROUPING_SUBGROUPS_KEY)
    if nested is not None and not isinstance(nested, list):
        problems.append(f"{where}: '{GROUPING_SUBGROUPS_KEY}' is a list of groupings.")
    return problems


def _minted(seed: str, taken: set[str]) -> str:
    """A grouping id derived from *seed*, stepped past any already *taken*.

    Derived rather than drawn at random so that the same statement gets the same id wherever it is
    upgraded — two checkouts of one repository must not mint two identities for one grouping.
    """
    for attempt in range(len(taken) + 1):
        digest = int.from_bytes(hashlib.sha256(f"{seed}#{attempt}".encode()).digest()[:8], "big")
        letters = "".join(_ID_ALPHABET[(digest // 62**place) % 62] for place in range(6))
        if (candidate := f"g-{letters}") not in taken:
            return candidate
    raise AssertionError("unreachable: more attempts than ids taken")


def with_grouping_ids(groupings: Sequence[object], *, diagram_id: str) -> list[dict[str, object]]:
    """*groupings* with an id on every entry that had none, the stated ones kept and put first.

    An entry's id leads it, so a reader of the file meets the identity before the content. A ruled
    entry's empty member list is dropped: listed or ruled, and an empty list is neither.
    """
    taken = set(grouping_ids(list(groupings)))

    def identified(entries: Sequence[object], trail: tuple[int, ...]) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            here = (*trail, index)
            grouping_id = entry.get(GROUPING_ID_KEY)
            if not grouping_id:
                seed = f"{diagram_id}/{'.'.join(map(str, here))}/{entry.get('label', '')}"
                grouping_id = _minted(seed, taken)
                taken.add(grouping_id)
            rebuilt: dict[str, object] = {GROUPING_ID_KEY: grouping_id}
            rebuilt.update({key: value for key, value in entry.items() if key != GROUPING_ID_KEY})
            if GROUPING_RULE_KEY in entry and not entry.get(GROUPING_MEMBERS_KEY):
                # A ruled grouping read back from a surface that always serves a member list carries
                # an empty one. It states no members, and is not written as though it listed some.
                rebuilt.pop(GROUPING_MEMBERS_KEY, None)
            nested = entry.get(GROUPING_SUBGROUPS_KEY)
            if isinstance(nested, list):
                rebuilt[GROUPING_SUBGROUPS_KEY] = identified(nested, here)
            result.append(rebuilt)
        return result

    return identified(groupings, ())


@dataclass(frozen=True)
class RuleKey:
    """How a box no entry states is addressed: the rules from the outermost box in, and which one.

    *ordinal* tells apart two boxes one rule path draws — a type boxed once per flow of a canvas —
    counted from 1 in the order they are drawn.
    """

    path: tuple[GroupingRule, ...]
    ordinal: int = 1

    @property
    def text(self) -> str:
        spelled = _RULE_KEY_PREFIX + "/".join(rule.text for rule in self.path)
        return spelled if self.ordinal == 1 else f"{spelled}#{self.ordinal}"


def is_rule_key(text: str) -> bool:
    """Whether *text* is spelled as a rule key, well-formed or not."""
    return text.startswith(_RULE_KEY_PREFIX)


def read_rule_key(text: str) -> RuleKey:
    """The box *text* addresses by its rule. Refuses what is not a rule key."""
    spelled, numbered, ordinal_text = text.removeprefix(_RULE_KEY_PREFIX).partition("#")
    path: list[GroupingRule] = []
    for segment in spelled.split("/"):
        kind, stated, value = segment.partition("=")
        if kind not in _RULE_KINDS or not stated or not _RULE_VALUE.fullmatch(value):
            raise MalformedGroupings(
                f"'{text}' is not a rule key: expected 'rule:domain=<name>', 'rule:type=<element type>' or "
                "'rule:domain=<name>/type=<element type>'."
            )
        path.append(GroupingRule("domain" if kind == "domain" else "type", value))
    if not is_rule_key(text) or (numbered and not (ordinal_text.isdigit() and int(ordinal_text) >= 2)):
        raise MalformedGroupings(f"'{text}' is not a rule key: a repeated box is numbered from '#2'.")
    return RuleKey(tuple(path), int(ordinal_text) if numbered else 1)
