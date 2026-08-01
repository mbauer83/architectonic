"""Recording a factor judgement: what is refused, what is audited, what comes back.

The refusals are the substance. A judgement about a node that is not a failure mode rates nothing.
A judgement with no basis would apply forever, which is what keying it to a basis exists to prevent.
A judgement with no rationale sets a priority band nobody can defend. Each is rejected before
anything is written, so the store never holds a rating that cannot be read back and understood.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.application.assurance.fmea_factors import (
    FactorInvalid,
    FactorNodeNotFound,
    FactorRecorded,
    FactorStoreLocked,
    RecordFactorRequest,
    record_factor_assessment,
)

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")


class _RecordingArchive:
    """Captures what would be appended, so the audit call is observable without a real archive."""

    def __init__(self) -> None:
        self.entries: list[tuple[str, str | None, dict[str, object]]] = []

    def append(self, operation: str, *, node_id: str | None = None, payload: dict | None = None) -> None:
        self.entries.append((operation, node_id, dict(payload or {})))


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


@pytest.fixture()
def archive() -> _RecordingArchive:
    return _RecordingArchive()


def _analysis(store: Any, name: str = "Fixture analysis", method: str = "STPA") -> str:
    """An analysis for the fixture's nodes to belong to.

    Every node records the analysis that produced it, and one without provenance is repair-only —
    so a fixture minting an unattributed node would exercise that guard rather than the behaviour
    under test.
    """
    return str(store.create_analysis(name, method, tlp="TLP:WHITE"))


@pytest.fixture()
def failure_mode(store: Any) -> str:
    return str(store.create_node(
        "failure-mode", "Store returns rows from a superseded snapshot",
        analysis_id=_analysis(store, "Pump failure modes", "FMEA"),
    ))


def _request(node_id: str, **overrides: object) -> RecordFactorRequest:
    payload: dict[str, object] = {
        "node_id": node_id,
        "factor": "occurrence",
        "value": "possible",
        "justification": "no field data; a comparable component fails about twice a year",
        "author": "analyst",
        "basis_digest": "abc123",
    }
    payload.update(overrides)
    return RecordFactorRequest(**payload)  # type: ignore[arg-type]


class TestARecordedJudgement:
    def test_it_comes_back_with_its_revision(self, store: Any, archive: Any, failure_mode: str) -> None:
        result = record_factor_assessment(_request(failure_mode), store=store, archive=archive)

        assert isinstance(result, FactorRecorded)
        assert (result.factor, result.value, result.revision) == ("occurrence", "possible", 1)
        assert result.created_at

    def test_it_is_appended_to_the_audit_archive(self, store: Any, archive: Any, failure_mode: str) -> None:
        """A rating that later drives a priority band has to be traceable to who set it."""
        record_factor_assessment(_request(failure_mode), store=store, archive=archive)

        operation, node_id, payload = archive.entries[-1]
        assert operation == "FMEA_FACTOR_ASSESSED"
        assert node_id == failure_mode
        assert payload["factor"] == "occurrence"
        assert payload["value"] == "possible"
        assert payload["author"] == "analyst"
        assert payload["basis_digest"] == "abc123"

    def test_it_is_readable_from_the_store(self, store: Any, archive: Any, failure_mode: str) -> None:
        record_factor_assessment(_request(failure_mode), store=store, archive=archive)

        rows = store.read_fmea_assessments([failure_mode])[failure_mode]

        assert [row["value"] for row in rows] == ["possible"]


class TestWhatIsRefused:
    def test_a_node_that_is_not_a_failure_mode(self, store: Any, archive: Any) -> None:
        """A hazard has no failure factors; rating one would record a judgement about nothing."""
        hazard = str(store.create_node(
            "hazard", "Renderer reachable with untrusted input", analysis_id=_analysis(store),
        ))

        result = record_factor_assessment(_request(hazard), store=store, archive=archive)

        assert isinstance(result, FactorNodeNotFound)
        assert archive.entries == [], "nothing may be audited for a write that did not happen"

    def test_a_node_that_does_not_exist(self, store: Any, archive: Any) -> None:
        result = record_factor_assessment(_request("FMD@nope"), store=store, archive=archive)

        assert isinstance(result, FactorNodeNotFound)

    def test_a_judgement_with_no_basis(self, store: Any, archive: Any, failure_mode: str) -> None:
        """Without a basis it could never stop applying, so it would outlive the model it rated."""
        result = record_factor_assessment(
            _request(failure_mode, basis_digest="  "), store=store, archive=archive,
        )

        assert isinstance(result, FactorInvalid)
        assert [e.field for e in result.errors] == ["basis_digest"]

    def test_a_judgement_with_no_rationale(self, store: Any, archive: Any, failure_mode: str) -> None:
        result = record_factor_assessment(
            _request(failure_mode, justification=""), store=store, archive=archive,
        )

        assert isinstance(result, FactorInvalid)
        assert [e.field for e in result.errors] == ["justification"]

    def test_a_value_outside_the_factor_scale(self, store: Any, archive: Any, failure_mode: str) -> None:
        result = record_factor_assessment(
            _request(failure_mode, value="catastrophic"), store=store, archive=archive,
        )

        assert isinstance(result, FactorInvalid)
        assert [e.field for e in result.errors] == ["value"]

    def test_nothing_is_written_when_validation_fails(
        self, store: Any, archive: Any, failure_mode: str
    ) -> None:
        record_factor_assessment(_request(failure_mode, justification=""), store=store, archive=archive)

        assert store.read_fmea_assessments([failure_mode]) == {}

    def test_a_locked_store_is_reported_rather_than_written_to(
        self, store: Any, archive: Any, failure_mode: str
    ) -> None:
        store.lock()

        result = record_factor_assessment(_request(failure_mode), store=store, archive=archive)

        assert isinstance(result, FactorStoreLocked)
        assert archive.entries == []
