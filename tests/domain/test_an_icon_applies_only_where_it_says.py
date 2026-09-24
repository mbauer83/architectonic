"""An icon's `applies-to` admits exactly the elements it names, and a change that drops one narrows it."""

from __future__ import annotations

import pytest

from src.domain.icons.applicability import (
    Applicability,
    ApplicabilityEntry,
    InvalidApplicabilityError,
    applicability_from,
)

NODE = ApplicabilityEntry("archimate-4", "technology-node")
CLUSTER = ApplicabilityEntry("archimate-4", "technology-node", "kubernetes-cluster")
CONTAINER = ApplicabilityEntry("c4", "container")


def _of(*entries: ApplicabilityEntry) -> Applicability:
    return Applicability(frozenset(entries))


def test_no_entries_admits_any_element() -> None:
    assert _of().admits(CLUSTER) and _of().admits(CONTAINER)


def test_a_type_entry_admits_the_type_with_or_without_a_specialization() -> None:
    assert _of(NODE).admits(NODE) and _of(NODE).admits(CLUSTER)
    assert not _of(NODE).admits(CONTAINER)


def test_a_specialization_entry_admits_only_that_specialization() -> None:
    assert _of(CLUSTER).admits(CLUSTER)
    assert not _of(CLUSTER).admits(NODE)
    assert not _of(CLUSTER).admits(ApplicabilityEntry("archimate-4", "technology-node", "vm"))


def test_the_same_type_name_in_another_ontology_is_another_type() -> None:
    assert not _of(ApplicabilityEntry("c4", "technology-node")).admits(NODE)


@pytest.mark.parametrize(
    ("previous", "replacement", "narrows"),
    [
        (_of(CLUSTER), _of(NODE), False),
        (_of(NODE), _of(CLUSTER), True),
        (_of(NODE), _of(), False),
        (_of(), _of(NODE), True),
        (_of(NODE, CONTAINER), _of(NODE), True),
        (_of(NODE), _of(NODE, CONTAINER), False),
        (_of(), _of(), False),
    ],
)
def test_replacing_a_set_narrows_it_exactly_when_it_stops_admitting_something(
    previous: Applicability, replacement: Applicability, narrows: bool
) -> None:
    assert replacement.narrows(previous) is narrows


def test_reading_and_writing_a_set_agree() -> None:
    written = _of(CLUSTER, CONTAINER).as_list()

    assert applicability_from(written) == _of(CLUSTER, CONTAINER)


def test_an_absent_field_reads_as_unrestricted() -> None:
    assert applicability_from(None).is_unrestricted


@pytest.mark.parametrize(
    "raw",
    [
        {"type": "technology-node"},
        {"ontology": "archimate-4", "type": " "},
        {"ontology": "archimate-4", "type": "node", "specialization": ""},
        {"ontology": "archimate-4", "type": "node", "stereotype": "x"},
    ],
)
def test_an_entry_that_cannot_be_stated_exactly_is_refused(raw: dict[str, str]) -> None:
    with pytest.raises(InvalidApplicabilityError):
        applicability_from([raw])
