"""An analysis may state its system under analysis late, and may never restate it.

`architecture_anchor_id` is documented as optional at creation and immutable afterwards, and the two
together left no route: an analysis created without one could never acquire one, and recreating it
was barred too — provenance is immutable, so its nodes cannot be re-filed under a replacement.

Immutability is protecting something real. Moving an anchor rewrites what an analysis was scoped to,
and every finding under it was reached against the old subject. Filling one that was never set is a
different act: nothing is rewritten, because there was nothing there. Only that transition opens.

Anchor resolution is deliberately not checked here, because `create_analysis` does not check it
either. A rule the create path does not hold would make the two disagree about the same field.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

FIRST = "APP@1780783671.hkrdtm.architecture-management-platform"
SECOND = "APP@1777293133.OYEmP1.architecture-backend"


def _store(path: Path) -> Any:
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    init_store(path)
    built = SQLCipherAssuranceStore(path)
    built.unlock()
    return built


def _archive(store: Any) -> Any:
    from src.infrastructure.assurance._archive import SQLCipherAssuranceArchive

    return SQLCipherAssuranceArchive(store.unlocked_connection)


@pytest.fixture()
def store(tmp_path: Path) -> Any:
    built = _store(tmp_path / "store.db")
    yield built
    built.lock()


def _update(store: Any, **kwargs: object) -> Any:
    from src.application.assurance import analysis as analysis_uc

    return analysis_uc.update_analysis(store, _archive(store), **kwargs)


def _created(store: Any, anchor: str) -> str:
    from src.application.assurance import analysis as analysis_uc

    result = analysis_uc.create_analysis(
        store, _archive(store), name="Storage integration", method="STPA",
        architecture_anchor_id=anchor,
    )
    return str(result.payload["analysis_id"])


class TestAnAnalysisWithNoAnchor:
    def test_it_can_be_given_one(self, store: Any) -> None:
        analysis_id = _created(store, "")

        result = _update(store, analysis_id=analysis_id, architecture_anchor_id=FIRST)

        assert result.payload["architecture_anchor_id"] == FIRST

    def test_the_fill_is_archived(self, store: Any) -> None:
        """It changes what the analysis is scoped to, so the chain has to carry it."""
        import json

        analysis_id = _created(store, "")
        _update(store, analysis_id=analysis_id, architecture_anchor_id=FIRST)

        entries = _archive(store).list_entries(operation="UPDATE_ANALYSIS")
        assert [json.loads(str(e["payload_json"]))["architecture_anchor_id"] for e in entries] == [FIRST]

    def test_an_empty_string_is_not_a_fill(self, store: Any) -> None:
        """Nothing to record and nothing to refuse — it asks for the state it is already in."""
        analysis_id = _created(store, "")

        result = _update(store, analysis_id=analysis_id, architecture_anchor_id="")

        assert result.payload["architecture_anchor_id"] == ""
        assert _archive(store).list_entries(operation="UPDATE_ANALYSIS") == []


class TestAnAnalysisThatAlreadyHasOne:
    def test_moving_it_is_refused(self, store: Any) -> None:
        analysis_id = _created(store, FIRST)

        result = _update(store, analysis_id=analysis_id, architecture_anchor_id=SECOND)

        assert result.error == "anchor_immutable"

    def test_the_stored_anchor_is_untouched(self, store: Any) -> None:
        """A refusal that had already written would be worse than no rule at all."""
        analysis_id = _created(store, FIRST)
        _update(store, analysis_id=analysis_id, architecture_anchor_id=SECOND)

        assert store.get_analysis(analysis_id)["architecture_anchor_id"] == FIRST

    def test_clearing_it_is_refused(self, store: Any) -> None:
        analysis_id = _created(store, FIRST)

        result = _update(store, analysis_id=analysis_id, architecture_anchor_id="")

        assert result.error == "anchor_immutable"

    def test_restating_the_same_anchor_is_accepted(self, store: Any) -> None:
        """It asks for the state the analysis is in, so refusing would only punish a caller that
        sent the whole record back."""
        analysis_id = _created(store, FIRST)

        result = _update(store, analysis_id=analysis_id, architecture_anchor_id=FIRST)

        assert result.payload["architecture_anchor_id"] == FIRST

    def test_a_refused_anchor_does_not_apply_the_rest_of_the_update(self, store: Any) -> None:
        """One call, one verdict. A partly-applied update leaves the caller unable to say what
        happened from the refusal alone."""
        analysis_id = _created(store, FIRST)

        _update(store, analysis_id=analysis_id, name="Renamed", architecture_anchor_id=SECOND)

        assert store.get_analysis(analysis_id)["name"] == "Storage integration"


class TestWhatStaysImmutable:
    def test_the_method_still_cannot_change(self, store: Any) -> None:
        """It decides which node types the analysis may author, so a change orphans its contents."""
        analysis_id = _created(store, FIRST)

        store.update_analysis(analysis_id, method="CAST")

        assert store.get_analysis(analysis_id)["method"] == "STPA"

    def test_the_domain_drops_an_anchor_that_is_already_set(self) -> None:
        """The decision procedure, stated over a record rather than through a store."""
        from src.domain.assurance.assurance_analysis import permitted_analysis_updates

        assert permitted_analysis_updates(
            {"architecture_anchor_id": FIRST}, {"architecture_anchor_id": SECOND, "name": "n"}
        ) == {"name": "n"}

    def test_the_domain_admits_one_into_an_empty_field(self) -> None:
        from src.domain.assurance.assurance_analysis import permitted_analysis_updates

        assert permitted_analysis_updates(
            {"architecture_anchor_id": ""}, {"architecture_anchor_id": FIRST}
        ) == {"architecture_anchor_id": FIRST}

    def test_the_domain_treats_a_missing_field_as_empty(self) -> None:
        """A record from a store that never wrote the column is not a record with an anchor."""
        from src.domain.assurance.assurance_analysis import permitted_analysis_updates

        assert permitted_analysis_updates({}, {"architecture_anchor_id": FIRST}) == {
            "architecture_anchor_id": FIRST
        }
