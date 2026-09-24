"""A baseline the real archive seals can be listed through the REST contract.

The archive returns every column of `baselines`, `timestamp_token_hex` included, and the closed
response contract did not declare it, so the first store to hold a baseline answered every
`GET /api/assurance/baselines` with a 500. The HTTP tests used a fake archive whose rows were whatever
the fake returned, so the real row shape never met the contract in a test until this one.
"""

from __future__ import annotations

import pytest

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")


@pytest.fixture()
def archive(tmp_path):  # type: ignore[no-untyped-def]
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance._worm_archive import WORMSQLCipherAssuranceArchive
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "store.db"
    init_store(db_path)
    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    yield WORMSQLCipherAssuranceArchive(store._thread_conn_or_none)  # noqa: SLF001
    store.lock()


def test_a_real_baseline_row_validates_against_the_listing_contract(archive) -> None:  # type: ignore[no-untyped-def]
    from src.infrastructure.rest.contracts.assurance_queries import AssuranceBaselineListResponse

    archive.append("CREATE", node_id="LSS@1.test", payload={"name": "Loss"})
    archive.seal_baseline(notes="release", analysis_id="STPA@1.x.y")
    baselines = archive.list_baselines()

    listing = AssuranceBaselineListResponse.model_validate({"baselines": baselines, "count": len(baselines)})

    assert listing.count == 1
    record = listing.baselines[0]
    assert record.analysis_id == "STPA@1.x.y" and record.timestamp_token_hex is None
    assert set(baselines[0]) <= set(type(record).model_fields), "a column the contract does not declare"


def test_a_timestamp_token_is_listed_when_the_seal_carries_one(archive) -> None:  # type: ignore[no-untyped-def]
    from src.infrastructure.rest.contracts.assurance_queries import AssuranceBaselineListResponse

    archive.append("CREATE", node_id="LSS@1.test")
    sealed = archive.seal_baseline(notes="with a token")
    archive.add_timestamp_token(str(sealed["baseline_id"]), "3082abcd")

    listing = AssuranceBaselineListResponse.model_validate({"baselines": archive.list_baselines(), "count": 1})

    assert listing.baselines[0].timestamp_token_hex == "3082abcd"
