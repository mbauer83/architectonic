"""Which keys more than one party claims — the detector under every "these two overlap" refusal.

A submission refuses two proposed changes that write one field of one artifact. A change set refuses
two of its operations that change one key, and a check over several sets reports where two of them
do. Those are one question — *who else claims this?* — asked over different keys and different
parties, and it is answered here once so that the three cannot come to disagree about what
overlapping means.

Deliberately no opinion about what an overlap *costs*. A submission refuses on sight; sets compare
the values and let equal ones converge. That judgement belongs to whoever asked.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable
from typing import TypeVar

Key = TypeVar("Key", bound=Hashable)
Party = TypeVar("Party", bound=Hashable)


def contested(claims: Iterable[tuple[Key, Party]]) -> dict[Key, tuple[Party, ...]]:
    """Every key claimed by more than one party, with the parties in the order they claimed it.

    Stated over the whole collection rather than over neighbours: two claims on one key need not be
    adjacent, and a rule that only compared consecutive ones would pass the arrangement that hides
    the problem. Keys come back in the order each was first *contested*, so a caller that refuses on
    the first one refuses on the same one however the rest are arranged. A party claiming the same
    key twice is counted once.
    """
    claimants: dict[Key, list[Party]] = {}
    found: dict[Key, list[Party]] = {}
    for key, party in claims:
        parties = claimants.setdefault(key, [])
        if party in parties:
            continue
        parties.append(party)
        if len(parties) > 1:
            found[key] = parties
    return {key: tuple(parties) for key, parties in found.items()}
