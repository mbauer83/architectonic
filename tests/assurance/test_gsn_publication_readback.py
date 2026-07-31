"""What was published can be read back, and only what the reader may see.

Recording a GSN publication was possible and reading it back was not, so the only way to learn whether
an assurance case had been published was to open a diagram and infer it. That was the last row of the
migration ledger — a canonical address the manifest declared and nothing served.

The read is *derived*, not stored: recording leaves ``gsn-source`` arch-refs on the nodes it bound, and
grouping those by diagram reconstructs the publication. So the property under test is that the two
agree, which they cannot fail to if there is one fact — and these tests are what keep it one fact.
"""

from __future__ import annotations

import pytest

from src.application.assurance_exposure import AssuranceExposurePolicy
from src.application.assurance_gsn import list_publications, record_publication

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")


@pytest.fixture()
def published(unlocked_store):  # type: ignore[no-untyped-def]
    """An analysis with two nodes, published to one GSN diagram with both bound.

    Fixture content the test owns: the assertions name specific bindings, which would be a false
    regression if they came from the live store.
    """
    store = unlocked_store
    analysis_id = store.create_analysis(name="Store Disclosure", method="GSN")
    first = store.create_node("evidence", "Access log is retained", analysis_id=analysis_id)
    second = store.create_node("evidence", "Clearance check is tested", analysis_id=analysis_id)
    # `record_publication` refuses an unpublishable classification and needs a real archive; the
    # bindings it writes are the whole subject here, so they are written the same way it writes them.
    store.register_arch_ref(first, "GSN@1.a.case#nodes/g1", "gsn-source")
    store.register_arch_ref(second, "GSN@1.a.case#nodes/g2", "gsn-source")
    return store, analysis_id, first, second


def test_a_publication_reads_back_with_every_binding(published) -> None:
    """The regression: recorded and read-back must describe the same publication."""
    store, analysis_id, first, second = published

    publications = list_publications(store, analysis_id=analysis_id)

    assert len(publications) == 1
    published_diagram = publications[0]
    assert published_diagram["diagram_id"] == "GSN@1.a.case"
    assert published_diagram["binding_count"] == 2
    assert published_diagram["source_bindings"] == [
        {"assurance_node_id": first, "gsn_node_id": "g1"},
        {"assurance_node_id": second, "gsn_node_id": "g2"},
    ]


def test_bindings_are_ordered_so_two_reads_agree(published) -> None:
    """The store returns nodes in whatever order it likes, and a caller diffing two reads of an
    unchanged publication must not see a change. Ordering is the contract, not an accident."""
    store, analysis_id, _first, _second = published

    once = list_publications(store, analysis_id=analysis_id)
    again = list_publications(store, analysis_id=analysis_id)

    assert once == again
    ids = [b["gsn_node_id"] for b in once[0]["source_bindings"]]
    assert ids == sorted(ids)


def test_a_ref_that_is_not_a_gsn_source_is_not_a_publication(published) -> None:
    """Arch-refs carry several relations; only one of them means "published". Counting the others
    would report a publication that never happened."""
    store, analysis_id, first, _second = published
    store.register_arch_ref(first, "APP@1.a.component", "implements")

    publications = list_publications(store, analysis_id=analysis_id)

    assert [p["diagram_id"] for p in publications] == ["GSN@1.a.case"]


def test_a_binding_the_reader_may_not_see_is_not_counted(published) -> None:
    """Exposure filtering runs *before* grouping, and the count is the obvious place for a leak.

    A reader who may see one of two bound nodes is told one. Reporting two would disclose that another
    node exists, which is precisely what the ceiling withholds — and it would do so through a number
    nobody thinks of as content.
    """
    store, analysis_id, first, _second = published

    publications = list_publications(
        store, analysis_id=analysis_id, visible_node_ids=frozenset({first})
    )

    assert len(publications) == 1
    assert publications[0]["binding_count"] == 1
    assert publications[0]["source_bindings"] == [
        {"assurance_node_id": first, "gsn_node_id": "g1"}
    ]


def test_a_diagram_with_no_visible_binding_is_absent_rather_than_empty(published) -> None:
    """Listing it with a count of zero would confirm a publication the reader may not know about, and
    would also be a puzzle: a published diagram that bound nothing."""
    store, analysis_id, _first, _second = published

    publications = list_publications(
        store, analysis_id=analysis_id, visible_node_ids=frozenset()
    )

    assert publications == []


def test_an_analysis_that_published_nothing_reads_back_empty(unlocked_store) -> None:
    """Not an error, and not a 404: an analysis that has never been published is a normal state, and
    the caller asked a question with an answer."""
    analysis_id = unlocked_store.create_analysis(name="Never Published", method="GSN")
    unlocked_store.create_node("evidence", "Unbound", analysis_id=analysis_id)

    assert list_publications(unlocked_store, analysis_id=analysis_id) == []


def test_the_recorder_and_the_reader_name_the_same_ref_type() -> None:
    """The two halves are one fact only while they agree on the ref type. A rename on either side
    would leave recording working and reading back silently empty — the failure this route exists to
    remove, reintroduced."""
    import inspect

    from src.application.assurance_gsn import GSN_SOURCE_REF_TYPE

    assert f'"{GSN_SOURCE_REF_TYPE}"' in inspect.getsource(record_publication)
