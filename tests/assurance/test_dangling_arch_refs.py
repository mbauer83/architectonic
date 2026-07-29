"""Assurance references into the architecture model that no longer resolve.

An assurance node cites an architecture artifact id. The architecture model evolves
independently, so the cited entity can be renamed away or deleted while the analysis that
depends on it stays silent — the analysis still reads as complete, and the reference it
rests on points at nothing. Surfacing that is the point; the risk is reporting it wrongly.

Losses this guards: an analyst trusts an analysis whose foundation has gone (a dangling
reference reported as sound), and an analyst chases a phantom because a present entity was
reported missing. The first is the severe one — it is invisible in every other surface.

Behaviour that must hold, and why:

- **Never writes.** This is called from `assurance_verify`, a read tool. The previous
  version stamped `resolved_at` on the confidential store, which is what kept it from ever
  having a caller. A read that mutates a gated store is not a read.
- **Locked is not clean.** A store nobody can open has an unknown number of dangling
  references, not zero. Collapsing the two would report an unreadable store as being in
  good order.
- **Missing means missing.** Only a lookup that returns nothing counts as dangling.
"""

from __future__ import annotations

from typing import Any

from src.infrastructure.assurance.arch_ref_resolver import dangling_arch_refs


class _Store:
    """A confidential store stub that records any attempt to write to it."""

    def __init__(self, refs: list[dict[str, Any]], *, unlocked: bool = True) -> None:
        self._refs = refs
        self._unlocked = unlocked
        self.writes: list[tuple[str, str, str]] = []

    def is_unlocked(self) -> bool:
        return self._unlocked

    def list_arch_refs(self) -> list[dict[str, Any]]:
        return list(self._refs)

    def mark_arch_ref_resolved(self, node_id: str, arch_id: str, ref_type: str) -> None:
        self.writes.append((node_id, arch_id, ref_type))


class _Lookup:
    def __init__(self, present: set[str]) -> None:
        self._present = present
        self.queried: list[str] = []

    def get_entity(self, artifact_id: str) -> object | None:
        self.queried.append(artifact_id)
        return object() if artifact_id in self._present else None


def _ref(node: str, arch: str, kind: str = "analyses") -> dict[str, Any]:
    return {"assurance_node_id": node, "arch_artifact_id": arch, "ref_type": kind}


class TestItNeverWrites:
    def test_a_resolvable_reference_is_not_stamped(self) -> None:
        """The whole reason this is callable from a read tool."""
        store = _Store([_ref("HAZ@1", "APP@present")])
        dangling_arch_refs(store, _Lookup({"APP@present"}))
        assert store.writes == [], "a read surface must not write to the confidential store"

    def test_a_dangling_reference_is_not_stamped_either(self) -> None:
        store = _Store([_ref("HAZ@1", "APP@gone")])
        dangling_arch_refs(store, _Lookup(set()))
        assert store.writes == []


class TestLockedIsNotClean:
    def test_a_locked_store_reports_locked_rather_than_zero_dangling(self) -> None:
        store = _Store([_ref("HAZ@1", "APP@gone")], unlocked=False)
        lookup = _Lookup(set())

        out = dangling_arch_refs(store, lookup)

        assert out["store"] == "locked"
        assert out["dangling_refs"] == []
        assert lookup.queried == [], "a locked store must not be read from at all"

    def test_an_unlocked_store_says_so(self) -> None:
        out = dangling_arch_refs(_Store([]), _Lookup(set()))
        assert out["store"] == "unlocked"


class TestWhatCountsAsDangling:
    def test_a_missing_entity_is_reported_with_its_reference_intact(self) -> None:
        ref = _ref("HAZ@1", "APP@gone", "analyses")
        out = dangling_arch_refs(_Store([ref]), _Lookup(set()))
        assert out["dangling"] == 1
        assert out["dangling_refs"] == [ref], "the caller needs which node cited what, not just a count"

    def test_a_present_entity_is_not_reported(self) -> None:
        out = dangling_arch_refs(_Store([_ref("HAZ@1", "APP@here")]), _Lookup({"APP@here"}))
        assert out["dangling"] == 0 and out["dangling_refs"] == []

    def test_a_mixed_set_reports_only_the_missing_ones(self) -> None:
        refs = [_ref("HAZ@1", "APP@here"), _ref("HAZ@2", "APP@gone"), _ref("HAZ@3", "APP@also-gone")]
        out = dangling_arch_refs(_Store(refs), _Lookup({"APP@here"}))
        assert out["checked"] == 3
        assert out["dangling"] == 2
        assert [r["arch_artifact_id"] for r in out["dangling_refs"]] == ["APP@gone", "APP@also-gone"]

    def test_every_reference_is_checked_not_just_the_first(self) -> None:
        refs = [_ref("HAZ@1", "APP@a"), _ref("HAZ@2", "APP@b"), _ref("HAZ@3", "APP@c")]
        lookup = _Lookup({"APP@a", "APP@b", "APP@c"})
        dangling_arch_refs(_Store(refs), lookup)
        assert lookup.queried == ["APP@a", "APP@b", "APP@c"]

    def test_the_same_entity_cited_twice_is_reported_twice(self) -> None:
        """Two analyses resting on one deleted entity are two findings — deduplicating
        would hide that the second analysis is affected at all."""
        refs = [_ref("HAZ@1", "APP@gone"), _ref("UCA@2", "APP@gone")]
        out = dangling_arch_refs(_Store(refs), _Lookup(set()))
        assert out["dangling"] == 2

    def test_an_empty_store_is_reported_as_checked_nothing(self) -> None:
        out = dangling_arch_refs(_Store([]), _Lookup(set()))
        assert out["checked"] == 0 and out["dangling"] == 0
