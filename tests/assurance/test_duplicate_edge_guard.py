"""The same relationship, twice, is not a stronger claim.

`add_edge` was a plain INSERT and the edge id carries a timestamp, so nothing stopped a second row
for the same (source, target, type). Two identical `leads-to` edges do not say the effect is more
certain — they say the same thing twice, and anything that walks or counts relationships counts them
twice. The severity derivation reduces over the losses a failure mode reaches, so a duplicated hop
inflates nothing today; a weighted or counting traversal added later would inherit the flaw silently.

Rejected rather than silently deduplicated: a caller who did not expect the edge to exist has learned
something, and one who did gets back the id they were about to look up.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.application import assurance_mutations as mutations

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")


class _NullArchive:
    def append(self, *_args: object, **_kwargs: object) -> None:
        return None


def _legal(_source_type: str, _target_type: str) -> frozenset[str]:
    return frozenset({"leads-to"})


@pytest.fixture()
def store(tmp_path: Path) -> Any:
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "store.db"
    init_store(db_path)
    built = SQLCipherAssuranceStore(db_path)
    built.unlock()
    yield built
    built.lock()


def _add(store: Any, source: str, target: str, conn_type: str = "leads-to") -> Any:
    return mutations.add_edge(
        store,
        _NullArchive(),  # type: ignore[arg-type]
        source_id=source,
        target_id=target,
        conn_type=conn_type,
        legal_connection_types=_legal,
    )


@pytest.fixture()
def pair(store: Any) -> tuple[str, str]:
    hazard = str(store.create_node("hazard", "Readable outside the gate"))
    loss = str(store.create_node("loss", "Disclosure"))
    return hazard, loss


class TestASecondCopyIsRefused:
    def test_the_first_one_is_created(self, store: Any, pair: tuple[str, str]) -> None:
        assert isinstance(_add(store, *pair), mutations.MutationOk)

    def test_the_second_one_is_reported_as_a_duplicate(self, store: Any, pair: tuple[str, str]) -> None:
        _add(store, *pair)

        assert isinstance(_add(store, *pair), mutations.MutationDuplicateEdge)

    def test_the_duplicate_names_the_edge_that_already_exists(
        self, store: Any, pair: tuple[str, str]
    ) -> None:
        """So a caller can use it rather than having to search for what blocked them."""
        first = _add(store, *pair)
        assert isinstance(first, mutations.MutationOk)

        second = _add(store, *pair)
        assert isinstance(second, mutations.MutationDuplicateEdge)

        assert second.edge_id == first.payload["edge_id"]

    def test_only_one_row_is_stored(self, store: Any, pair: tuple[str, str]) -> None:
        _add(store, *pair)
        _add(store, *pair)

        assert len(store.list_edges(source_id=pair[0], target_id=pair[1])) == 1


class TestWhatIsNotADuplicate:
    def test_a_different_connection_type_between_the_same_pair(
        self, store: Any, pair: tuple[str, str]
    ) -> None:
        """The guard is per (source, target, type). Two different relations between one pair are two
        different claims."""
        _add(store, *pair)

        def _two(_s: str, _t: str) -> frozenset[str]:
            return frozenset({"leads-to", "explains"})

        result = mutations.add_edge(
            store, _NullArchive(),  # type: ignore[arg-type]
            source_id=pair[0], target_id=pair[1], conn_type="explains",
            legal_connection_types=_two,
        )

        assert isinstance(result, mutations.MutationOk)

    def test_the_reverse_direction(self, store: Any, pair: tuple[str, str]) -> None:
        """Direction carries the meaning in a causal vocabulary, so A→B and B→A are not the same
        edge — the ontology matrix decides whether the reverse is legal, not this guard."""
        hazard, loss = pair
        _add(store, hazard, loss)

        assert isinstance(_add(store, loss, hazard), mutations.MutationOk)
