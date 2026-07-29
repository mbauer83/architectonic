"""Tests for the viewpoint-dependency promotion check (D14/WU-E10): ``_promote_viewpoints.py``
and the ``rewrite_viewpoint_pin`` file-op helper.

Covers: dependency collection (ok/engagement_only/version_mismatch), blocking-error messages,
the ``promote_alongside``/``repin`` resolutions (incl. transitive specialization validation
for promote_alongside), and the execute-time application of both resolutions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.domain.concept_scope import ConceptScope
from src.domain.modules.module_types import EntityTypeName
from src.domain.viewpoints.viewpoint_criteria import AttributeCondition, EntityCriteriaGroup, ValueRef
from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery, ViewpointCatalog, ViewpointDefinition
from src.infrastructure.viewpoint_declarations import (
    load_viewpoint_catalog_file,
    load_viewpoint_catalog_for_repos,
    write_viewpoint_catalog_file,
)
from src.infrastructure.write.artifact_write._promote_file_ops import rewrite_viewpoint_pin
from src.infrastructure.write.artifact_write._promote_viewpoints import (
    ViewpointDependency,
    apply_viewpoint_resolutions,
    collect_viewpoint_dependencies,
    viewpoint_dependency_errors,
)


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry  # noqa: PLC0415

    return build_runtime_catalogs(get_module_registry())


@dataclass
class _DiagramStub:
    diagram_type: str = "archimate"
    extra: dict = field(default_factory=dict)


def _def(**kw: object) -> ViewpointDefinition:
    defaults: dict[str, object] = dict(slug="my-vp", version=1, name="My VP")
    defaults.update(kw)
    return ViewpointDefinition(**defaults)  # type: ignore[arg-type]


def _role_definition(*, version: int = 1, specialization: str = "business-role") -> ViewpointDefinition:
    """A definition referencing a real module-shipped entity type + specialization
    (``role``/``business-role``) so it validates against the real catalogs without any
    repo-local specialization declarations."""
    return _def(
        version=version,
        scope=ConceptScope(entity_types=frozenset({EntityTypeName("role")})),
        query=ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(
                children=(
                    AttributeCondition(
                        attribute="specialization", comparator="eq", value=ValueRef(literal=specialization)
                    ),
                )
            )
        ),
    )


@pytest.fixture()
def roots(tmp_path: Path) -> tuple[Path, Path]:
    eng = tmp_path / "eng"
    ent = tmp_path / "ent"
    eng.mkdir()
    ent.mkdir()
    return eng, ent


# ---------------------------------------------------------------------------
# collect_viewpoint_dependencies
# ---------------------------------------------------------------------------


class TestCollectViewpointDependencies:
    def test_skips_diagrams_without_viewpoint_application(self, roots: tuple[Path, Path]) -> None:
        eng_root, ent_root = roots
        repo = MagicMock()
        repo.get_diagram.return_value = _DiagramStub(extra={})
        deps = collect_viewpoint_dependencies(["DGM@1"], repo=repo, ent_root=ent_root)
        assert deps == []

    def test_ok_status_when_versions_match(self, roots: tuple[Path, Path]) -> None:
        eng_root, ent_root = roots
        write_viewpoint_catalog_file(ent_root, ViewpointCatalog(entries=(_def(version=2),)))
        repo = MagicMock()
        repo.get_diagram.return_value = _DiagramStub(extra={"viewpoint": {"slug": "my-vp", "version": 2}})
        deps = collect_viewpoint_dependencies(["DGM@1"], repo=repo, ent_root=ent_root)
        assert deps == [
            ViewpointDependency(
                target_id="DGM@1", target_kind="diagram", slug="my-vp", pinned_version=2,
                status="ok", enterprise_version=2,
            )
        ]

    def test_engagement_only_when_enterprise_lacks_slug(self, roots: tuple[Path, Path]) -> None:
        eng_root, ent_root = roots
        repo = MagicMock()
        repo.get_diagram.return_value = _DiagramStub(
            diagram_type="matrix", extra={"viewpoint": {"slug": "my-vp", "version": 1}}
        )
        deps = collect_viewpoint_dependencies(["MTX@1"], repo=repo, ent_root=ent_root)
        assert len(deps) == 1
        assert deps[0].target_kind == "matrix"
        assert deps[0].status == "engagement_only"
        assert deps[0].enterprise_version is None

    def test_version_mismatch_when_enterprise_has_different_version(self, roots: tuple[Path, Path]) -> None:
        eng_root, ent_root = roots
        write_viewpoint_catalog_file(ent_root, ViewpointCatalog(entries=(_def(version=3),)))
        repo = MagicMock()
        repo.get_diagram.return_value = _DiagramStub(extra={"viewpoint": {"slug": "my-vp", "version": 1}})
        deps = collect_viewpoint_dependencies(["DGM@1"], repo=repo, ent_root=ent_root)
        assert deps[0].status == "version_mismatch"
        assert deps[0].enterprise_version == 3


# ---------------------------------------------------------------------------
# viewpoint_dependency_errors
# ---------------------------------------------------------------------------


class TestViewpointDependencyErrors:
    def _dep(self, **kw: object) -> ViewpointDependency:
        defaults: dict[str, object] = dict(
            target_id="DGM@1", target_kind="diagram", slug="my-vp", pinned_version=1,
            status="engagement_only", enterprise_version=None,
        )
        defaults.update(kw)
        return ViewpointDependency(**defaults)  # type: ignore[arg-type]

    def test_ok_dependency_produces_no_errors(self, roots: tuple[Path, Path]) -> None:
        eng_root, ent_root = roots
        errors = viewpoint_dependency_errors(
            [self._dep(status="ok", enterprise_version=1)], eng_root=eng_root, ent_root=ent_root
        )
        assert errors == []

    def test_engagement_only_blocked_with_actionable_message(self, roots: tuple[Path, Path]) -> None:
        eng_root, ent_root = roots
        errors = viewpoint_dependency_errors([self._dep()], eng_root=eng_root, ent_root=ent_root)
        assert len(errors) == 1
        assert "my-vp" in errors[0]
        assert "engagement repo" in errors[0]
        assert "promote_alongside" in errors[0]

    def test_engagement_only_resolved_by_promote_alongside(self, roots: tuple[Path, Path]) -> None:
        eng_root, ent_root = roots
        write_viewpoint_catalog_file(eng_root, ViewpointCatalog(entries=(_role_definition(),)))
        errors = viewpoint_dependency_errors(
            [self._dep()],
            eng_root=eng_root,
            ent_root=ent_root,
            catalogs=_catalogs(),
            resolutions={"my-vp": "promote_alongside"},
        )
        assert errors == []

    def test_promote_alongside_blocked_by_transitive_unknown_specialization(self, roots: tuple[Path, Path]) -> None:
        eng_root, ent_root = roots
        write_viewpoint_catalog_file(
            eng_root, ViewpointCatalog(entries=(_role_definition(specialization="not-a-real-specialization"),))
        )
        errors = viewpoint_dependency_errors(
            [self._dep()],
            eng_root=eng_root,
            ent_root=ent_root,
            catalogs=_catalogs(),
            resolutions={"my-vp": "promote_alongside"},
        )
        assert any("promoted alongside" in e and "unknown-value" in e for e in errors)

    def test_promote_alongside_without_engagement_definition_reports_missing(self, roots: tuple[Path, Path]) -> None:
        eng_root, ent_root = roots
        errors = viewpoint_dependency_errors(
            [self._dep()],
            eng_root=eng_root,
            ent_root=ent_root,
            catalogs=_catalogs(),
            resolutions={"my-vp": "promote_alongside"},
        )
        assert any("no engagement-repo definition" in e for e in errors)

    def test_newer_enterprise_version_still_blocks_without_repin(self, roots: tuple[Path, Path]) -> None:
        eng_root, ent_root = roots
        dep = self._dep(status="version_mismatch", pinned_version=1, enterprise_version=2)
        errors = viewpoint_dependency_errors([dep], eng_root=eng_root, ent_root=ent_root)
        assert len(errors) == 1
        assert "re-pin" in errors[0]
        assert "repin" in errors[0]

    def test_version_mismatch_resolved_by_repin(self, roots: tuple[Path, Path]) -> None:
        eng_root, ent_root = roots
        dep = self._dep(status="version_mismatch", pinned_version=1, enterprise_version=2)
        errors = viewpoint_dependency_errors(
            [dep], eng_root=eng_root, ent_root=ent_root, resolutions={"my-vp": "repin"}
        )
        assert errors == []

    def test_repin_resolution_does_not_satisfy_engagement_only(self, roots: tuple[Path, Path]) -> None:
        eng_root, ent_root = roots
        errors = viewpoint_dependency_errors(
            [self._dep()], eng_root=eng_root, ent_root=ent_root, resolutions={"my-vp": "repin"}
        )
        assert len(errors) == 1
        assert "engagement repo" in errors[0]


# ---------------------------------------------------------------------------
# apply_viewpoint_resolutions (execute-time)
# ---------------------------------------------------------------------------


class TestApplyViewpointResolutions:
    def test_promote_alongside_writes_definition_into_enterprise_catalog(self, roots: tuple[Path, Path]) -> None:
        eng_root, ent_root = roots
        write_viewpoint_catalog_file(eng_root, ViewpointCatalog(entries=(_role_definition(version=2),)))
        deps = [
            ViewpointDependency(
                target_id="DGM@1", target_kind="diagram", slug="my-vp", pinned_version=2,
                status="engagement_only", enterprise_version=None,
            )
        ]
        backups: list[tuple[Path, bytes | None]] = []
        apply_viewpoint_resolutions(
            deps,
            {"my-vp": "promote_alongside"},
            engagement_root=eng_root,
            enterprise_root=ent_root,
            registry=MagicMock(),
            backups=backups,
        )
        written = load_viewpoint_catalog_file(ent_root)
        assert written.get("my-vp") == _role_definition(version=2)
        assert len(backups) == 2  # both catalogs (enterprise write, engagement removal) backed up

    def test_promote_alongside_moves_the_definition_out_of_the_engagement_catalog(
        self, roots: tuple[Path, Path]
    ) -> None:
        """A definition lives in exactly one tier: the move must complete, not copy."""
        eng_root, ent_root = roots
        write_viewpoint_catalog_file(
            eng_root, ViewpointCatalog(entries=(_role_definition(version=2), _def(slug="stays", version=1)))
        )
        deps = [
            ViewpointDependency(
                target_id="DGM@1", target_kind="diagram", slug="my-vp", pinned_version=2,
                status="engagement_only", enterprise_version=None,
            )
        ]
        apply_viewpoint_resolutions(
            deps, {"my-vp": "promote_alongside"}, engagement_root=eng_root, enterprise_root=ent_root,
            registry=MagicMock(), backups=[],
        )
        eng_after = load_viewpoint_catalog_file(eng_root)
        assert eng_after.get("my-vp") is None
        assert eng_after.get("stays") is not None

    def test_the_two_repo_catalogs_still_load_after_promote_alongside(self, roots: tuple[Path, Path]) -> None:
        """Regression: the engagement copy left behind made the next process start crash —
        ``enterprise | engagement`` raised "Duplicate viewpoint slug" (first seen as the CI
        e2e job's `arch-assurance init` failing on a scaffolded enterprise repo)."""
        eng_root, ent_root = roots
        write_viewpoint_catalog_file(eng_root, ViewpointCatalog(entries=(_role_definition(version=2),)))
        deps = [
            ViewpointDependency(
                target_id="DGM@1", target_kind="diagram", slug="my-vp", pinned_version=2,
                status="engagement_only", enterprise_version=None,
            )
        ]
        apply_viewpoint_resolutions(
            deps, {"my-vp": "promote_alongside"}, engagement_root=eng_root, enterprise_root=ent_root,
            registry=MagicMock(), backups=[],
        )
        merged = load_viewpoint_catalog_for_repos(enterprise_root=ent_root, engagement_root=eng_root)
        assert merged.get("my-vp") == _role_definition(version=2)

    def test_promote_alongside_replaces_existing_slug_not_duplicates(self, roots: tuple[Path, Path]) -> None:
        eng_root, ent_root = roots
        write_viewpoint_catalog_file(eng_root, ViewpointCatalog(entries=(_role_definition(version=2),)))
        write_viewpoint_catalog_file(ent_root, ViewpointCatalog(entries=(_def(slug="other", version=1),)))
        deps = [
            ViewpointDependency(
                target_id="DGM@1", target_kind="diagram", slug="my-vp", pinned_version=2,
                status="engagement_only", enterprise_version=None,
            )
        ]
        apply_viewpoint_resolutions(
            deps, {"my-vp": "promote_alongside"}, engagement_root=eng_root, enterprise_root=ent_root,
            registry=MagicMock(), backups=[],
        )
        written = load_viewpoint_catalog_file(ent_root)
        assert {e.slug for e in written.entries} == {"my-vp", "other"}

    def test_repin_rewrites_diagram_frontmatter_version(self, roots: tuple[Path, Path]) -> None:
        eng_root, ent_root = roots
        rel = Path("diagram-catalog/diagrams/DGM@1.abc.test.puml")
        eng_path = eng_root / rel
        eng_path.parent.mkdir(parents=True)
        eng_path.write_text(
            "---\nartifact-id: DGM@1\nname: Test\nviewpoint:\n  slug: my-vp\n  version: 1\n---\n@startuml\n@enduml\n",
            encoding="utf-8",
        )
        ent_path = ent_root / rel
        ent_path.parent.mkdir(parents=True)
        ent_path.write_text(eng_path.read_text(encoding="utf-8"), encoding="utf-8")

        registry = MagicMock()
        registry.find_file_by_id.return_value = eng_path
        deps = [
            ViewpointDependency(
                target_id="DGM@1", target_kind="diagram", slug="my-vp", pinned_version=1,
                status="version_mismatch", enterprise_version=3,
            )
        ]
        apply_viewpoint_resolutions(
            deps, {"my-vp": "repin"}, engagement_root=eng_root, enterprise_root=ent_root,
            registry=registry, backups=[],
        )
        rewritten = ent_path.read_text(encoding="utf-8")
        assert "version: 3" in rewritten
        assert "name: Test" in rewritten
        assert eng_path.read_text(encoding="utf-8").count("version: 1") == 1  # engagement copy untouched


# ---------------------------------------------------------------------------
# rewrite_viewpoint_pin
# ---------------------------------------------------------------------------


class TestRewriteViewpointPin:
    def test_rewrites_version_preserves_other_fields_and_body(self, tmp_path: Path) -> None:
        path = tmp_path / "diagram.puml"
        path.write_text(
            "---\nartifact-id: DGM@1\nname: Test\nstatus: draft\nviewpoint:\n  slug: my-vp\n  version: 1\n"
            "  enforcement_override: warn\n---\n@startuml\ntitle Test\n@enduml\n",
            encoding="utf-8",
        )
        rewrite_viewpoint_pin(path, 5)
        text = path.read_text(encoding="utf-8")
        assert "version: 5" in text
        assert "enforcement_override: warn" in text
        assert "name: Test" in text
        assert "@startuml\ntitle Test\n@enduml" in text

    def test_noop_when_no_viewpoint_frontmatter(self, tmp_path: Path) -> None:
        path = tmp_path / "diagram.puml"
        original = "---\nartifact-id: DGM@1\nname: Test\n---\n@startuml\n@enduml\n"
        path.write_text(original, encoding="utf-8")
        rewrite_viewpoint_pin(path, 5)
        assert path.read_text(encoding="utf-8") == original

    def test_noop_when_no_frontmatter_block(self, tmp_path: Path) -> None:
        path = tmp_path / "diagram.puml"
        original = "@startuml\n@enduml\n"
        path.write_text(original, encoding="utf-8")
        rewrite_viewpoint_pin(path, 5)
        assert path.read_text(encoding="utf-8") == original
