"""An icon's `applies-to` admits exactly the elements whose type or specialization it names."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.icons.applicability import Applicability, InvalidApplicabilityError, applicability_from
from src.domain.ontology_representation.artifact_types import EntityRecord


def _entity(artifact_type: str, *specializations: str) -> EntityRecord:
    return EntityRecord(
        artifact_id="NOD@1.aaaa.x", artifact_type=artifact_type, name="x", version="0.1.0", status="draft",
        domain="technology", subdomain="", path=Path("x.md"), keywords=(), extra={}, content_text="",
        display_blocks={}, display_label="", display_alias="", specializations=specializations,
    )


NODE = _entity("technology-node")
CLUSTER = _entity("technology-node", "kubernetes-cluster")
TAGGED_TWICE = _entity("technology-node", "vm", "kubernetes-cluster")
SERVICE = _entity("application-service")


def _for(*names: str) -> Applicability:
    return applicability_from(names)


def test_no_names_admit_any_element() -> None:
    assert all(_for().admits(e.type_and_specializations) for e in (NODE, CLUSTER, SERVICE))


def test_a_type_name_admits_the_type_with_or_without_a_specialization() -> None:
    assert _for("technology-node").admits(NODE.type_and_specializations)
    assert _for("technology-node").admits(CLUSTER.type_and_specializations)
    assert not _for("technology-node").admits(SERVICE.type_and_specializations)


def test_a_specialization_name_admits_only_elements_that_carry_it() -> None:
    assert _for("kubernetes-cluster").admits(CLUSTER.type_and_specializations)
    assert _for("kubernetes-cluster").admits(TAGGED_TWICE.type_and_specializations)
    assert not _for("kubernetes-cluster").admits(NODE.type_and_specializations)


def test_reading_and_writing_agree() -> None:
    written = _for("kubernetes-cluster", "application-service").as_list()

    assert applicability_from(written) == _for("application-service", "kubernetes-cluster")


def test_an_absent_field_reads_as_unrestricted() -> None:
    assert applicability_from(None).is_unrestricted


@pytest.mark.parametrize("raw", ["", "  ", 3, {"type": "technology-node"}])
def test_an_entry_that_is_not_a_name_is_refused(raw: object) -> None:
    with pytest.raises(InvalidApplicabilityError):
        applicability_from([raw])
