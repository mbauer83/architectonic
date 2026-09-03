"""The index and the duplicate check read a reference's enterprise target the same way.

They did not. `global-artifact-id` was spelled at eight sites in eight modules under four constant
names, and two of those readings were not equivalent: `_MemStore` bucketed a reference under its
*stripped* target (in two independently written copies), while `find_existing_gar` compared the raw
value. A reference whose target carried surrounding whitespace was therefore indexed under one key
and searched for under another — so the duplicate check could not see it and would create a second
reference to the same enterprise artifact.

The whitespace is not exotic: the field is authored by hand and by tools, and every other reader in
the repository already tolerated it. The tolerant reading existed; nothing consulted it.

Stated as a **pair**, over what the field permits rather than over what a writer emits today.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.application.modeling.enterprise_reference import (
    ENTITY_KIND,
    GLOBAL_ARTIFACT_ENTITY_TYPE,
    GLOBAL_ARTIFACT_ID,
    GLOBAL_ARTIFACT_KIND,
    GLOBAL_ARTIFACT_REFERENCE_TYPE,
    enterprise_target,
    proxies_an_entity,
)
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.infrastructure.artifact_index._mem_store import _MemStore
from src.infrastructure.write.artifact_write.global_artifact_reference import find_existing_gar

TARGET = "APP@1780000000.abcdefg.payments-service"

#: Every form the field permits for one target: as written, and the whitespace an author or a tool
#: can leave around it.
SPELLINGS = [TARGET, f" {TARGET}", f"{TARGET} ", f"  {TARGET}  ", f"\t{TARGET}", f"{TARGET}\n"]


def _reference(spelling: str, artifact_id: str = "GAR@1780000001.zzzzzzz.payments-service") -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type=GLOBAL_ARTIFACT_REFERENCE_TYPE,
        name="payments-service",
        version="0.1.0",
        status="draft",
        domain="common",
        subdomain="global-artifact-reference",
        path=Path("/repo/model/common/global-artifact-reference/gar.md"),
        keywords=(),
        extra={
            GLOBAL_ARTIFACT_ID: spelling,
            GLOBAL_ARTIFACT_KIND: ENTITY_KIND,
            GLOBAL_ARTIFACT_ENTITY_TYPE: "application-component",
        },
        content_text="",
        display_blocks={},
        display_label="payments-service",
        display_alias="payments_service",
    )


class _Repo:
    """The one method `find_existing_gar` uses."""

    def __init__(self, *records: EntityRecord) -> None:
        self._records = records

    def list_entities(self, artifact_type: str | None = None, **_: object) -> list[EntityRecord]:
        return [r for r in self._records if artifact_type in (None, r.artifact_type)]


@pytest.mark.parametrize("spelling", SPELLINGS)
def test_the_index_and_the_duplicate_check_agree_on_every_spelling(spelling) -> None:
    """The regression. Before one reader, the padded spellings indexed one way and matched another."""
    record = _reference(spelling)

    store = _MemStore()
    store.entities[record.artifact_id] = record
    store.index_entity(record)

    assert store.grf_targets_by_entity.get(TARGET) == {record.artifact_id}
    assert find_existing_gar(_Repo(record), TARGET) == record.artifact_id


@pytest.mark.parametrize("spelling", SPELLINGS)
def test_the_bulk_rebuild_agrees_with_the_incremental_path(spelling) -> None:
    """`_MemStore` maintains this map twice — on each entity, and on a full rebuild. Both readings
    were written independently, so they are asserted against each other rather than each against a
    fixture."""
    record = _reference(spelling)

    incremental = _MemStore()
    incremental.entities[record.artifact_id] = record
    incremental.index_entity(record)

    rebuilt = _MemStore()
    rebuilt.entities[record.artifact_id] = record
    rebuilt.rebuild_path_indexes()

    assert rebuilt.grf_targets_by_entity == incremental.grf_targets_by_entity
    assert rebuilt.grf_targets_by_entity.get(TARGET) == {record.artifact_id}


@pytest.mark.parametrize("spelling", SPELLINGS)
def test_unindexing_removes_what_indexing_added(spelling) -> None:
    """The pair that a drifting reading breaks second: a target bucketed under one key and discarded
    under another leaves the map holding a reference that no longer exists."""
    record = _reference(spelling)
    store = _MemStore()
    store.entities[record.artifact_id] = record
    store.index_entity(record)
    store.unindex_entity(record)

    assert TARGET not in store.grf_targets_by_entity


@pytest.mark.parametrize("blank", ["", "   ", "\t", "\n"])
def test_a_blank_target_is_no_target_rather_than_the_empty_one(blank) -> None:
    """Otherwise every reference with an unfilled field buckets together under `""` and answers each
    other's duplicate checks."""
    record = _reference(blank)
    store = _MemStore()
    store.entities[record.artifact_id] = record
    store.index_entity(record)

    assert enterprise_target(record.extra) is None
    assert store.grf_targets_by_entity == {}
    assert find_existing_gar(_Repo(record), "") is None


def test_a_missing_field_is_no_target() -> None:
    assert enterprise_target({}) is None


@pytest.mark.parametrize("value", [None, 42, ["a"], {"a": 1}])
def test_a_target_that_is_not_text_is_no_target(value) -> None:
    """The field is authored, so a YAML scalar of the wrong shape reaches here rather than being
    refused upstream. Reading one as a target would key the map by a list."""
    assert enterprise_target({GLOBAL_ARTIFACT_ID: value}) is None


def test_only_an_entity_reference_offers_a_connection_surface() -> None:
    """Three call sites compared this field against `"entity"` by hand; the question has a name now."""
    entity_ref = _reference(TARGET)
    assert proxies_an_entity(entity_ref.extra)

    document_ref = replace(entity_ref, extra={**entity_ref.extra, GLOBAL_ARTIFACT_KIND: "document"})
    assert not proxies_an_entity(document_ref.extra)
    assert not proxies_an_entity({})
