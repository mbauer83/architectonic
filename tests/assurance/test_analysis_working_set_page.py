"""The paginated working set: authored ∪ participating, with each node's role stated.

Two things this has to get right, and both are invisible if only the happy path is tested:

* **a borrowed node has to look borrowed.** The whole reason provenance and participation are two
  relations is that an FMEA can reason over an STPA's control structure without owning it. A page
  that returned both sets undifferentiated would let a reader attribute one method's findings to the
  other.
* **exposure filtering runs before the page is built.** Filtered afterwards, pages would come back
  short by unpredictable amounts and the totals beside them would count records the reader may not
  see — which is a disclosure, not a display bug.

The cursor is exercised across a page boundary rather than asserted as a value: what matters is that
walking it visits every node exactly once, which is the property an unstable sort order breaks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.application.assurance_exposure import AssuranceExposurePolicy
from src.application.assurance_working_set_page import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    analysis_working_set_page,
    effective_limit,
)

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")


@pytest.fixture()
def store(tmp_path: Path) -> Any:
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "working-set.db"
    init_store(db_path)
    opened = SQLCipherAssuranceStore(db_path)
    opened.unlock()
    yield opened
    opened.lock()


def _policy(ceiling: str = "TLP:RED") -> AssuranceExposurePolicy:
    return AssuranceExposurePolicy(ceiling, True)


@pytest.fixture()
def combined(store: Any) -> dict[str, Any]:
    """An STPA that authored two nodes, and an FMEA that borrowed one of them."""
    stpa = str(store.create_analysis("Brakes", "STPA", tlp="TLP:WHITE"))
    fmea = str(store.create_analysis("Pumps", "FMEA", tlp="TLP:WHITE"))
    authored_by_fmea = str(store.create_node("failure-mode", "Pump stalls", analysis_id=fmea))
    borrowed = str(store.create_node("control-structure-node", "Pump controller", analysis_id=stpa))
    store.add_analysis_member(fmea, borrowed)
    return {
        "stpa": stpa, "fmea": fmea, "authored": authored_by_fmea, "borrowed": borrowed,
    }


class TestRolesAreStatedPerItem:
    def test_an_authored_node_reads_as_authored(self, store: Any, combined: dict[str, Any]) -> None:
        page = analysis_working_set_page(store, _policy(), combined["fmea"])

        roles = {item.node["node_id"]: item.relationship for item in page.items}
        assert roles[combined["authored"]] == "authored"

    def test_a_borrowed_node_reads_as_referenced(self, store: Any, combined: dict[str, Any]) -> None:
        """The distinction the two relations exist for. Lost, a reader attributes the STPA's control
        structure to the FMEA that merely reasons over it."""
        page = analysis_working_set_page(store, _policy(), combined["fmea"])

        roles = {item.node["node_id"]: item.relationship for item in page.items}
        assert roles[combined["borrowed"]] == "referenced"

    def test_the_role_totals_describe_the_analysis(self, store: Any, combined: dict[str, Any]) -> None:
        page = analysis_working_set_page(store, _policy(), combined["fmea"])

        assert page.authored_total == 1
        assert page.referenced_total == 1

    def test_the_borrowed_node_keeps_its_own_provenance(
        self, store: Any, combined: dict[str, Any]
    ) -> None:
        page = analysis_working_set_page(store, _policy(), combined["fmea"])

        borrowed = next(i for i in page.items if i.node["node_id"] == combined["borrowed"])
        assert str(borrowed.node["analysis_id"]) == combined["stpa"], (
            "participation does not re-attribute authorship"
        )


class TestTheRelationshipFilter:
    def test_it_narrows_to_one_role(self, store: Any, combined: dict[str, Any]) -> None:
        page = analysis_working_set_page(store, _policy(), combined["fmea"], relationship="authored")

        assert [i.node["node_id"] for i in page.items] == [combined["authored"]]

    def test_the_totals_still_describe_the_whole_working_set(
        self, store: Any, combined: dict[str, Any]
    ) -> None:
        """A filter narrows what is *shown*, not what is *counted* — otherwise "1 authored,
        0 borrowed" would be a report about the query rather than about the analysis."""
        page = analysis_working_set_page(store, _policy(), combined["fmea"], relationship="authored")

        assert page.authored_total == 1
        assert page.referenced_total == 1


class TestPaging:
    def _many(self, store: Any, count: int) -> str:
        analysis = str(store.create_analysis("Wide", "STPA", tlp="TLP:WHITE"))
        for index in range(count):
            store.create_node("hazard", f"Hazard {index:03d}", analysis_id=analysis)
        return analysis

    def test_walking_the_cursor_visits_every_node_exactly_once(self, store: Any) -> None:
        """The property a non-deterministic sort order breaks — silently, and only sometimes."""
        analysis = self._many(store, 7)

        seen: list[str] = []
        cursor: str | None = None
        while True:
            page = analysis_working_set_page(store, _policy(), analysis, limit=3, cursor=cursor)
            seen.extend(str(item.node["node_id"]) for item in page.items)
            cursor = page.next_cursor
            if cursor is None:
                break

        assert len(seen) == 7
        assert len(set(seen)) == 7, "a page boundary repeated or skipped a node"

    def test_the_last_page_carries_no_cursor(self, store: Any) -> None:
        analysis = self._many(store, 2)

        page = analysis_working_set_page(store, _policy(), analysis, limit=10)

        assert page.next_cursor is None

    def test_an_unreadable_cursor_starts_at_the_beginning(self, store: Any) -> None:
        """A stale bookmark is not an error the user can act on, so it resumes rather than refuses."""
        analysis = self._many(store, 2)

        page = analysis_working_set_page(store, _policy(), analysis, cursor="not-a-cursor")

        assert len(page.items) == 2


class TestTheLimit:
    def test_absent_means_the_house_default(self) -> None:
        assert effective_limit(None) == DEFAULT_LIMIT

    def test_an_absurd_request_is_clamped(self) -> None:
        """A maximum exists so one request cannot ask the store for everything."""
        assert effective_limit(10_000) == MAX_LIMIT

    def test_zero_or_negative_still_returns_a_page(self) -> None:
        assert effective_limit(0) == 1
        assert effective_limit(-5) == 1


class TestExposureFilteringPrecedesThePage:
    def test_an_above_ceiling_node_is_absent_from_items_and_from_the_totals(
        self, store: Any
    ) -> None:
        """Filtered *after* paging, the page would be short and the totals would count a record the
        reader may not see — which discloses that it exists."""
        analysis = str(store.create_analysis("Brakes", "STPA", tlp="TLP:GREEN"))
        visible = str(store.create_node(
            "hazard", "Visible hazard", analysis_id=analysis, tlp="TLP:GREEN"))
        store.create_node("hazard", "Secret hazard", analysis_id=analysis, tlp="TLP:RED")

        page = analysis_working_set_page(store, _policy("TLP:GREEN"), analysis)

        assert [str(i.node["node_id"]) for i in page.items] == [visible]
        assert page.authored_total == 1, "the total counts what is visible, not what is stored"
        assert "Secret hazard" not in str(page.items)
