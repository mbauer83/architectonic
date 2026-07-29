"""Tests for viewpoint persistence lifecycle and referencer discovery.

Pure functions only: callers own loading the local catalog and persisting the returned
catalog.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from src.application.viewpoints.persist_definition import (
    delete_viewpoint_definition,
    find_viewpoint_referencers,
    persist_viewpoint_definition,
)
from src.domain.concept_scope import ConceptScope
from src.domain.modules.module_types import EntityTypeName
from src.domain.viewpoints.viewpoint_lineage import definition_digest
from src.domain.viewpoints.viewpoints import (
    ExecutableViewpointQuery,
    ForkLineage,
    ViewpointCatalog,
    ViewpointDefinition,
)
from tests.application.viewpoints._fixtures import REGISTRIES


@dataclass
class _DiagramStub:
    artifact_id: str
    diagram_type: str
    extra: dict = field(default_factory=dict)


@dataclass
class _DiagramSearchStub:
    diagrams: list = field(default_factory=list)

    def list_diagrams(self, **_kwargs):
        return self.diagrams


def _definition(**kw: object) -> ViewpointDefinition:
    defaults: dict[str, object] = dict(slug="test-viewpoint", version=1, name="Test")
    defaults.update(kw)
    return ViewpointDefinition(**defaults)  # type: ignore[arg-type]


class TestForkLineageStamping:
    """Lineage is stamped by THIS service and only this service — the single path both
    the GUI Save-as and the MCP tool go through, so forks carry identical lineage."""

    def _origin(self) -> ViewpointDefinition:
        return _definition(slug="origin", version=3, name="Origin")

    def test_create_with_fork_of_stamps_origin_digest_and_generation(self) -> None:
        origin = self._origin()
        result = persist_viewpoint_definition(
            "create",
            _definition(slug="fork", name="Fork"),
            local_catalog=ViewpointCatalog.empty(),
            merged_catalog=ViewpointCatalog((origin,)),
            registries=REGISTRIES,
            fork_of="origin",
            index_generation=42,
        )
        assert result.ok is True
        assert result.catalog_to_write is not None
        stored = result.catalog_to_write.get("fork")
        assert stored is not None and stored.forked_from is not None
        assert stored.forked_from.slug == "origin"
        assert stored.forked_from.version == 3
        assert stored.forked_from.definition_digest == definition_digest(origin)
        assert stored.forked_from.index_generation == 42

    def test_unknown_fork_origin_is_rejected(self) -> None:
        result = persist_viewpoint_definition(
            "create",
            _definition(slug="fork"),
            local_catalog=ViewpointCatalog.empty(),
            merged_catalog=ViewpointCatalog.empty(),
            registries=REGISTRIES,
            fork_of="ghost",
        )
        assert result.ok is False
        assert result.issues[0].code == "unknown-fork-origin"

    def test_plain_create_strips_client_supplied_lineage(self) -> None:
        forged = replace(
            _definition(slug="fresh"),
            forked_from=ForkLineage(slug="origin", version=1, definition_digest="forged"),
        )
        result = persist_viewpoint_definition(
            "create",
            forged,
            local_catalog=ViewpointCatalog.empty(),
            merged_catalog=ViewpointCatalog.empty(),
            registries=REGISTRIES,
        )
        assert result.ok is True
        assert result.catalog_to_write is not None
        stored = result.catalog_to_write.get("fresh")
        assert stored is not None and stored.forked_from is None

    def test_edit_preserves_stored_lineage_regardless_of_what_the_client_sends(self) -> None:
        origin = self._origin()
        lineage = ForkLineage(slug="origin", version=3, definition_digest=definition_digest(origin))
        existing = replace(_definition(slug="fork", name="Fork"), forked_from=lineage)
        edited = _definition(slug="fork", name="Fork (renamed)")  # client sends NO lineage
        result = persist_viewpoint_definition(
            "edit",
            edited,
            local_catalog=ViewpointCatalog((existing,)),
            merged_catalog=ViewpointCatalog((existing, origin)),
            registries=REGISTRIES,
        )
        assert result.ok is True
        assert result.catalog_to_write is not None
        stored = result.catalog_to_write.get("fork")
        assert stored is not None
        assert stored.forked_from == lineage
        assert stored.name == "Fork (renamed)"


class TestCreate:
    def test_creates_and_returns_catalog_to_write(self) -> None:
        definition = _definition()
        result = persist_viewpoint_definition(
            "create", definition, local_catalog=ViewpointCatalog.empty(), merged_catalog=ViewpointCatalog.empty(),
            registries=REGISTRIES,
        )
        assert result.ok is True
        assert result.issues == ()
        assert result.catalog_to_write is not None
        assert result.catalog_to_write.get("test-viewpoint") == definition

    def test_slug_collision_rejected_with_no_catalog_to_write(self) -> None:
        existing = _definition(slug="dup")
        merged = ViewpointCatalog(entries=(existing,))
        result = persist_viewpoint_definition(
            "create", _definition(slug="dup"), local_catalog=ViewpointCatalog.empty(), merged_catalog=merged,
            registries=REGISTRIES,
        )
        assert result.ok is False
        assert result.issues[0].code == "slug-collision"
        assert result.catalog_to_write is None

    def test_invalid_definition_reports_validation_issues(self) -> None:
        bad_scope = _definition(
            scope=ConceptScope(entity_types=frozenset({EntityTypeName("not-a-real-type")}))
        )
        result = persist_viewpoint_definition(
            "create", bad_scope, local_catalog=ViewpointCatalog.empty(), merged_catalog=ViewpointCatalog.empty(),
            registries=REGISTRIES,
        )
        assert result.ok is False
        assert any(i.code == "unknown-type" for i in result.issues)
        assert result.catalog_to_write is None

    def test_warning_is_reported_without_blocking_persistence(self) -> None:
        definition = _definition(
            scope=ConceptScope(
                entity_types=frozenset({EntityTypeName("application-component")})
            ),
            query=ExecutableViewpointQuery(),
            selection_mode="query",
        )

        result = persist_viewpoint_definition(
            "create",
            definition,
            local_catalog=ViewpointCatalog.empty(),
            merged_catalog=ViewpointCatalog.empty(),
            registries=REGISTRIES,
        )

        assert result.ok is True
        assert [item.code for item in result.issues] == ["selection-layers-diverge"]
        assert result.catalog_to_write is not None


class TestEdit:
    def _local_catalog_with(self, definition: ViewpointDefinition) -> ViewpointCatalog:
        return ViewpointCatalog(entries=(definition,))

    def test_descriptive_edit_does_not_require_bump(self) -> None:
        local = self._local_catalog_with(_definition())
        edited = _definition(description="now with a description")
        result = persist_viewpoint_definition(
            "edit", edited, local_catalog=local, merged_catalog=ViewpointCatalog.empty(), registries=REGISTRIES
        )
        assert result.ok is True
        assert result.catalog_to_write.get("test-viewpoint").description == "now with a description"

    def test_semantic_edit_without_bump_rejected(self) -> None:
        local = self._local_catalog_with(_definition())
        edited = _definition(scope=ConceptScope(entity_types=frozenset({EntityTypeName("application-component")})))
        result = persist_viewpoint_definition(
            "edit", edited, local_catalog=local, merged_catalog=ViewpointCatalog.empty(), registries=REGISTRIES
        )
        assert result.ok is False
        assert any(i.code == "version-not-bumped" for i in result.issues)
        assert result.catalog_to_write is None

    def test_semantic_edit_with_bump_succeeds(self) -> None:
        local = self._local_catalog_with(_definition())
        edited = _definition(
            version=2, scope=ConceptScope(entity_types=frozenset({EntityTypeName("application-component")}))
        )
        result = persist_viewpoint_definition(
            "edit", edited, local_catalog=local, merged_catalog=ViewpointCatalog.empty(), registries=REGISTRIES
        )
        assert result.ok is True
        assert result.catalog_to_write.get("test-viewpoint").version == 2

    def test_unknown_slug_rejected(self) -> None:
        result = persist_viewpoint_definition(
            "edit", _definition(slug="never-created"), local_catalog=ViewpointCatalog.empty(),
            merged_catalog=ViewpointCatalog.empty(), registries=REGISTRIES,
        )
        assert result.ok is False
        assert result.issues[0].code == "unknown-slug"

    def test_enterprise_only_definition_is_read_only(self) -> None:
        enterprise_only = _definition(slug="enterprise-vp")
        merged = ViewpointCatalog(entries=(enterprise_only,))
        result = persist_viewpoint_definition(
            "edit", _definition(slug="enterprise-vp", description="hijack"), local_catalog=ViewpointCatalog.empty(),
            merged_catalog=merged, registries=REGISTRIES,
        )
        assert result.ok is False
        assert result.issues[0].code == "read-only-definition"


class TestDelete:
    def test_deletes_existing(self) -> None:
        local = ViewpointCatalog(entries=(_definition(),))
        result = delete_viewpoint_definition(
            "test-viewpoint", local_catalog=local, merged_catalog=ViewpointCatalog.empty(),
            read_access=_DiagramSearchStub(),
        )
        assert result.ok is True
        assert result.catalog_to_write == ViewpointCatalog.empty()

    def test_unknown_slug_rejected(self) -> None:
        result = delete_viewpoint_definition(
            "never-existed", local_catalog=ViewpointCatalog.empty(), merged_catalog=ViewpointCatalog.empty(),
            read_access=_DiagramSearchStub(),
        )
        assert result.ok is False
        assert result.issues[0].code == "unknown-slug"
        assert result.catalog_to_write is None

    def test_blocked_while_referenced(self) -> None:
        local = ViewpointCatalog(entries=(_definition(),))
        referencing_diagram = _DiagramStub(
            artifact_id="DIAG@1", diagram_type="context", extra={"viewpoint": {"slug": "test-viewpoint"}}
        )
        result = delete_viewpoint_definition(
            "test-viewpoint", local_catalog=local, merged_catalog=ViewpointCatalog.empty(),
            read_access=_DiagramSearchStub(diagrams=[referencing_diagram]),
        )
        assert result.ok is False
        assert result.issues[0].code == "delete-blocked-referenced"
        assert result.referencers[0].artifact_id == "DIAG@1"
        assert result.catalog_to_write is None


class TestFindReferencers:
    def test_matches_only_target_slug(self) -> None:
        matching = _DiagramStub(artifact_id="DIAG@a", diagram_type="context", extra={"viewpoint": {"slug": "x"}})
        other = _DiagramStub(artifact_id="DIAG@b", diagram_type="context", extra={"viewpoint": {"slug": "y"}})
        no_application = _DiagramStub(artifact_id="DIAG@c", diagram_type="context", extra={})
        store = _DiagramSearchStub(diagrams=[matching, other, no_application])
        referencers = find_viewpoint_referencers("x", read_access=store)
        assert [r.artifact_id for r in referencers] == ["DIAG@a"]

    def test_distinguishes_matrix_from_diagram(self) -> None:
        matrix = _DiagramStub(artifact_id="MTX@a", diagram_type="matrix", extra={"viewpoint": {"slug": "x"}})
        store = _DiagramSearchStub(diagrams=[matrix])
        referencers = find_viewpoint_referencers("x", read_access=store)
        assert referencers[0].target_kind == "matrix"

    def test_sorted_by_artifact_id(self) -> None:
        b = _DiagramStub(artifact_id="DIAG@b", diagram_type="context", extra={"viewpoint": {"slug": "x"}})
        a = _DiagramStub(artifact_id="DIAG@a", diagram_type="context", extra={"viewpoint": {"slug": "x"}})
        store = _DiagramSearchStub(diagrams=[b, a])
        referencers = find_viewpoint_referencers("x", read_access=store)
        assert [r.artifact_id for r in referencers] == ["DIAG@a", "DIAG@b"]
