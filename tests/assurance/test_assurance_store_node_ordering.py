"""The SQL-backed store's own `ORDER BY` — the ordering every other adapter has to match.

Written against the real store, not a fake, because the ordering is SQL text: a column name
that does not exist, or a direction spliced in wrongly, only shows up here. Node timestamps are
pinned through the central clock so "most recently updated first" is a fact about the data
rather than a race between two inserts in the same second.
"""

from __future__ import annotations

import pytest

from src.domain.clock import frozen_now

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")
pytest.importorskip("cryptography", reason="cryptography not installed")


@pytest.fixture()
def store(tmp_path):
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore  # noqa: PLC0415
    from src.infrastructure.assurance.lifecycle import init_store  # noqa: PLC0415

    db_path = tmp_path / "store.db"
    init_store(db_path)
    opened = SQLCipherAssuranceStore(db_path)
    opened.unlock()

    # Created oldest-first; updated in the opposite order, so a created_at sort and an
    # updated_at sort cannot accidentally agree.
    with frozen_now("2026-01-01T00:00:00Z"):
        first = opened.create_node("loss", "Alpha Loss")
    with frozen_now("2026-01-02T00:00:00Z"):
        second = opened.create_node("hazard", "Bravo Hazard")
    with frozen_now("2026-01-03T00:00:00Z"):
        third = opened.create_node("assurance-constraint", "Charlie Constraint")
    with frozen_now("2026-07-01T00:00:00Z"):
        opened.update_node(third, status="active")
    with frozen_now("2026-07-02T00:00:00Z"):
        opened.update_node(second, status="active")
    with frozen_now("2026-07-03T00:00:00Z"):
        opened.update_node(first, status="active")

    yield opened, (first, second, third)
    opened.lock()


def _ids(nodes) -> list[str]:
    return [str(n["node_id"]) for n in nodes]


def test_unspecified_sort_keeps_the_natural_creation_order(store) -> None:
    opened, (first, second, third) = store
    assert _ids(opened.list_nodes()) == [first, second, third]


def test_most_recently_updated_first(store) -> None:
    opened, (first, second, third) = store
    assert _ids(opened.list_nodes(sort="updated_at", order="desc")) == [first, second, third]


def test_least_recently_updated_first(store) -> None:
    opened, (first, second, third) = store
    assert _ids(opened.list_nodes(sort="updated_at", order="asc")) == [third, second, first]


def test_created_at_and_updated_at_are_distinct_orderings(store) -> None:
    opened, _ids_created = store
    assert _ids(opened.list_nodes(sort="created_at", order="desc")) != _ids(
        opened.list_nodes(sort="updated_at", order="desc")
    )


def test_name_and_type_orderings(store) -> None:
    opened, (first, second, third) = store
    assert _ids(opened.list_nodes(sort="name", order="asc")) == [first, second, third]
    assert _ids(opened.list_nodes(sort="node_type", order="asc")) == [third, second, first]


def test_an_unknown_sort_field_cannot_reach_the_query(store) -> None:
    opened, (first, second, third) = store
    # A column name from the request never reaches SQL — it is looked up in the supported set,
    # so an injection attempt is simply an unknown field and yields the natural order.
    assert _ids(opened.list_nodes(sort="name; DROP TABLE assurance_nodes", order="desc")) == [
        first, second, third,
    ]
    assert len(opened.list_nodes()) == 3


def test_filters_still_apply_alongside_a_sort(store) -> None:
    opened, (_first, second, _third) = store
    rows = opened.list_nodes(node_type="hazard", sort="updated_at", order="desc")
    assert _ids(rows) == [second]
