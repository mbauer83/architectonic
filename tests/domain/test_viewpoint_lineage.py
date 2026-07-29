"""Fork-lineage semantics: content digests, stamping, and digest-based staleness."""

from __future__ import annotations

from dataclasses import replace

from src.domain.viewpoints.viewpoint_criteria import AttributeCondition, EntityCriteriaGroup, ValueRef
from src.domain.viewpoints.viewpoint_lineage import definition_digest, fork_lineage, fork_status
from src.domain.viewpoints.viewpoint_parsing import viewpoint_definition_from_mapping
from src.domain.viewpoints.viewpoint_serialization import viewpoint_definition_to_mapping
from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery, ForkLineage, ViewpointDefinition


def _definition(**kw: object) -> ViewpointDefinition:
    defaults: dict[str, object] = dict(slug="origin", version=1, name="Origin")
    defaults.update(kw)
    return ViewpointDefinition(**defaults)  # type: ignore[arg-type]


def _query(type_name: str) -> ExecutableViewpointQuery:
    return ExecutableViewpointQuery(
        entity_criteria=EntityCriteriaGroup(
            children=(AttributeCondition(attribute="type", comparator="eq", value=ValueRef(literal=type_name)),)
        )
    )


class TestDefinitionDigest:
    def test_digest_is_stable_for_equal_content(self) -> None:
        assert definition_digest(_definition(query=_query("goal"))) == definition_digest(
            _definition(query=_query("goal"))
        )

    def test_digest_changes_with_content_even_without_a_version_bump(self) -> None:
        assert definition_digest(_definition(query=_query("goal"))) != definition_digest(
            _definition(query=_query("process"))
        )

    def test_a_definitions_own_lineage_never_affects_its_digest(self) -> None:
        lineage = ForkLineage(slug="elsewhere", version=1, definition_digest="x")
        assert definition_digest(_definition()) == definition_digest(_definition(forked_from=lineage))


class TestForkStatus:
    def test_untouched_origin_reads_current(self) -> None:
        origin = _definition(query=_query("goal"))
        assert fork_status(fork_lineage(origin, 7), origin) == "current"

    def test_editing_the_origin_flips_to_stale_even_without_a_version_bump(self) -> None:
        origin = _definition(query=_query("goal"))
        lineage = fork_lineage(origin, 7)
        edited_origin = replace(origin, query=_query("process"))  # same version integer
        assert fork_status(lineage, edited_origin) == "stale"

    def test_missing_origin_is_its_own_state(self) -> None:
        origin = _definition()
        assert fork_status(fork_lineage(origin, None), None) == "origin-missing"

    def test_non_fork_has_no_status(self) -> None:
        assert fork_status(None, _definition()) is None


class TestLineageRoundTrip:
    def test_forked_from_round_trips_through_the_wire_mapping(self) -> None:
        stamped = _definition(
            slug="fork",
            forked_from=ForkLineage(slug="origin", version=3, definition_digest="abc123", index_generation=42),
        )
        mapping = viewpoint_definition_to_mapping(stamped)
        assert mapping["forked_from"] == {
            "slug": "origin",
            "version": 3,
            "definition_digest": "abc123",
            "index_generation": 42,
        }
        assert viewpoint_definition_from_mapping(mapping).forked_from == stamped.forked_from

    def test_non_fork_omits_the_key(self) -> None:
        assert "forked_from" not in viewpoint_definition_to_mapping(_definition())
