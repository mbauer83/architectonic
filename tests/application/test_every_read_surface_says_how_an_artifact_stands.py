"""REST, the MCP returns and the CLI give the same answer about pending local changes.

Three transports, one question: is what I am looking at the enterprise baseline, or does it carry
changes not yet accepted upstream? They must not be able to disagree, and they are not the same shape
of surface — REST and MCP serialise a typed payload, while the CLI is `print(record)` over `__str__`
and has no field to carry one.

The measured reason this is a test rather than a convention: `is_global` is one predicate with one
owner, emitted at ten call sites, and the three hit serialisers disagree — two omit it. A surface
that quietly stops reporting a standing shows a proposed artifact as accepted upstream.

Written against a repository the test builds, so the counts are the test's own and not the shipped
model's.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.modeling.proposal_standing import (
    standing_reader,
    standing_subject,
    standing_subject_by_id,
)
from src.application.modeling.proposed_change import (
    BASE_REVISION,
    PROPOSAL_STATE,
    PROPOSED_CHANGE_TYPE,
    PROPOSES_CHANGE_TO,
    RECORDED_EDIT,
)
from src.domain.baseline_standing import EnterpriseBaseline, Proposed
from src.domain.ontology_representation.artifact_types import EntityRecord

ENTERPRISE_ID = "APP@1780000000.aaaaaaa.payments-service"
GAR_ID = "GAR@1780000001.bbbbbbb.payments-service"
PROPOSAL_ID = "PCH@1780000002.ccccccc.rename-it"


def _record(artifact_id: str, artifact_type: str, extra: dict) -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        name=artifact_id.split(".")[-1],
        version="0.1.0",
        status="draft",
        domain="common",
        subdomain=artifact_type,
        path=Path(f"/repo/model/common/{artifact_type}/{artifact_id}.md"),
        keywords=(),
        extra=extra,
        content_text="",
        display_blocks={},
        display_label=artifact_id,
        display_alias=artifact_id.replace("@", "_"),
    )


class _Repo:
    """The three methods the reader uses."""

    def __init__(self, *records: EntityRecord) -> None:
        self._records = {r.artifact_id: r for r in records}

    def list_entities(self, artifact_type: str | None = None, **_: object) -> list[EntityRecord]:
        return [r for r in self._records.values() if artifact_type in (None, r.artifact_type)]

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self._records.get(artifact_id)


@pytest.fixture()
def repo() -> _Repo:
    """A reference to an enterprise artifact, and a live change proposed against it."""
    from src.application.modeling.enterprise_reference import GLOBAL_ARTIFACT_ID

    return _Repo(
        _record(GAR_ID, "global-artifact-reference", {GLOBAL_ARTIFACT_ID: ENTERPRISE_ID}),
        _record(PROPOSAL_ID, PROPOSED_CHANGE_TYPE, {
            PROPOSES_CHANGE_TO: ENTERPRISE_ID,
            PROPOSAL_STATE: "draft",
            BASE_REVISION: "0f1e2d3c4b5a6978",
            RECORDED_EDIT: {"kind": "entity", "artifact-id": ENTERPRISE_ID, "fields": {"name": "Payments"}},
        }),
        _record("VAL@1780000003.ddddddd.local-thing", "value", {}),
    )


def test_a_reference_reports_the_standing_of_what_it_stands_for(repo: _Repo) -> None:
    """The rule that makes the whole surface work: a change is against the *enterprise* artifact,
    which the engagement repository holds as a reference."""
    reference = repo.get_entity(GAR_ID)
    assert reference is not None

    standing = standing_reader(repo)(standing_subject(reference))

    assert isinstance(standing, Proposed)
    assert standing.changed_fields == ("name",)


def test_an_ordinary_engagement_entity_is_the_baseline(repo: _Repo) -> None:
    local = repo.get_entity("VAL@1780000003.ddddddd.local-thing")
    assert local is not None

    assert isinstance(standing_reader(repo)(standing_subject(local)), EnterpriseBaseline)


def test_the_id_based_lookup_agrees_with_the_record_based_one(repo: _Repo) -> None:
    """Two callers, one rule: REST holds records, the MCP list holds only ids. If these could
    disagree, one transport would report a proposed artifact as accepted."""
    reference = repo.get_entity(GAR_ID)
    assert reference is not None

    assert standing_subject_by_id(repo, GAR_ID) == standing_subject(reference)


def test_an_id_the_repository_does_not_hold_is_its_own_subject(repo: _Repo) -> None:
    """A summary can name an artifact the entity index does not carry — a document or a diagram."""
    assert standing_subject_by_id(repo, "DOC@1780000004.eeeeeee.a-doc") == "DOC@1780000004.eeeeeee.a-doc"


def test_the_reader_is_one_snapshot_rather_than_a_lookup_per_row(repo: _Repo) -> None:
    """A list read of several hundred rows must not re-derive the pending changes per row."""
    asked: list[str | None] = []
    original = repo.list_entities

    def counting(artifact_type: str | None = None, **kw: object) -> list[EntityRecord]:
        asked.append(artifact_type)
        return original(artifact_type, **kw)

    repo.list_entities = counting  # type: ignore[method-assign]
    reader = standing_reader(repo)
    for _ in range(50):
        reader(ENTERPRISE_ID)

    assert asked == [PROPOSED_CHANGE_TYPE], asked


def test_a_repository_with_nothing_proposed_costs_no_revision_reads() -> None:
    """The ordinary case. Hashing a file to confirm that nothing is pending is work for nothing."""
    plain = _Repo(_record("VAL@1780000003.ddddddd.local-thing", "value", {}))
    plain.get_entity = lambda _id: pytest.fail("no revision should be read")  # type: ignore[assignment]

    assert isinstance(standing_reader(plain)("anything"), EnterpriseBaseline)


def test_no_repository_at_all_answers_the_baseline() -> None:
    """An app built without a served repository — the reader must not raise into a read path."""
    assert isinstance(standing_reader(None)("anything"), EnterpriseBaseline)
