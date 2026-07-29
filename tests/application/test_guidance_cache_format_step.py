"""The guidance-cache format migrator (arch-repair, offline): detects sub-current cached documents
and restructures them into the current, hierarchy-shaped format — each entity type under the domain
its module declares — blocking on unreadable, newer, or unresolvable ones."""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

from src.application.deployment_upgrade.steps.guidance_cache_format import GuidanceCacheFormatStep
from src.domain.guidance.guidance import GUIDANCE_FORMAT
from src.domain.guidance.guidance_hierarchy import GuidanceHierarchy
from src.domain.repository.operational_upgrade import UpgradeTarget
from src.infrastructure.app_bootstrap import build_module_registry, guidance_hierarchies
from src.infrastructure.deployment.file_targets import GuidanceCacheHandle

_ALIAS = "archimate-4"

# A cache in the superseded shape: level-keyed sibling maps, with the alias repeated one level down
# and no tie between an entity type and its domain.
_SUPERSEDED_DOC = """guidance_format: 3
workspace:
  encode-relations:
    context: "Encode relations structurally."
  keep-principles-general:
    context: "State principles generally."
meta_ontologies:
  archimate-4:
    meta_ontology:
      archimate-4:
        context: "Naming across the whole model."
    domain:
      motivation:
        context: "Why the architecture is shaped this way."
    entity_types:
      goal: {create_when: cw, never_create_when: nw}
"""


def _hierarchies() -> dict[str, GuidanceHierarchy]:
    return guidance_hierarchies(build_module_registry())


def _handle(root: Path) -> GuidanceCacheHandle:
    target = UpgradeTarget(
        kind="guidance_cache",
        stable_id=f"guidance_cache:{root}",
        display_location=str(root),
        current_version=None,
    )
    return GuidanceCacheHandle(target=target, root=root)


def _run(root: Path, *, hierarchies: dict[str, GuidanceHierarchy] | None = None) -> list:
    step = GuidanceCacheFormatStep(hierarchies if hierarchies is not None else _hierarchies())
    handle = _handle(root)
    findings = step.detect(handle.view())
    uow = handle.begin()
    applied = step.apply(handle.view(), uow, findings)
    uow.commit()
    return applied


class TestDetect:
    def test_superseded_document_is_auto_migratable(self, tmp_path: Path) -> None:
        (tmp_path / f"{_ALIAS}.guidance.yaml").write_text(_SUPERSEDED_DOC, encoding="utf-8")
        findings = GuidanceCacheFormatStep(_hierarchies()).detect(_handle(tmp_path).view())
        assert len(findings) == 1
        assert findings[0].auto_migratable is True
        assert findings[0].severity == "warning"
        assert not findings[0].blocks_commit

    def test_current_document_yields_no_finding(self, tmp_path: Path) -> None:
        (tmp_path / "a.guidance.yaml").write_text(
            f"guidance_format: {GUIDANCE_FORMAT}\nmeta_ontologies: {{}}\n", encoding="utf-8"
        )
        assert GuidanceCacheFormatStep(_hierarchies()).detect(_handle(tmp_path).view()) == []

    def test_newer_document_blocks_commit(self, tmp_path: Path) -> None:
        (tmp_path / "a.guidance.yaml").write_text("guidance_format: 99\n", encoding="utf-8")
        findings = GuidanceCacheFormatStep(_hierarchies()).detect(_handle(tmp_path).view())
        assert len(findings) == 1
        assert findings[0].auto_migratable is False
        assert findings[0].blocks_commit is True
        assert "newer" in findings[0].description

    def test_headerless_document_blocks_commit(self, tmp_path: Path) -> None:
        (tmp_path / "a.guidance.yaml").write_text("meta_ontologies: {}\n", encoding="utf-8")
        findings = GuidanceCacheFormatStep(_hierarchies()).detect(_handle(tmp_path).view())
        assert len(findings) == 1
        assert findings[0].blocks_commit is True

    def test_unknown_alias_blocks_instead_of_half_migrating(self, tmp_path: Path) -> None:
        """Without the module's guidance tree there is no way to know which domain a type belongs
        under, so the cache is reported for manual re-import rather than rewritten."""
        (tmp_path / f"{_ALIAS}.guidance.yaml").write_text(_SUPERSEDED_DOC, encoding="utf-8")
        findings = GuidanceCacheFormatStep().detect(_handle(tmp_path).view())
        assert len(findings) == 1
        assert findings[0].auto_migratable is False
        assert findings[0].blocks_commit is True
        assert "arch-import-guidance" in (findings[0].manual_instructions or "")


class TestApply:
    def _migrated(self, tmp_path: Path) -> dict:
        doc = tmp_path / f"{_ALIAS}.guidance.yaml"
        doc.write_text(_SUPERSEDED_DOC, encoding="utf-8")
        applied = _run(tmp_path)
        assert len(applied) == 1 and applied[0].outcome == "applied"
        return yaml.safe_load(doc.read_text(encoding="utf-8"))

    def test_format_header_is_current(self, tmp_path: Path) -> None:
        assert self._migrated(tmp_path)["guidance_format"] == GUIDANCE_FORMAT

    def test_entity_type_moves_under_its_declared_domain(self, tmp_path: Path) -> None:
        tree = self._migrated(tmp_path)["meta_ontologies"][_ALIAS]
        assert tree["motivation"]["entity_types"]["goal"] == {"create_when": "cw", "never_create_when": "nw"}
        assert "entity_types" not in tree

    def test_meta_ontology_context_moves_onto_the_alias(self, tmp_path: Path) -> None:
        tree = self._migrated(tmp_path)["meta_ontologies"][_ALIAS]
        assert tree["context"] == "Naming across the whole model."
        assert "meta_ontology" not in tree

    def test_domain_context_keeps_its_node_and_loses_the_level_key(self, tmp_path: Path) -> None:
        tree = self._migrated(tmp_path)["meta_ontologies"][_ALIAS]
        assert tree["motivation"]["context"] == "Why the architecture is shaped this way."
        assert "domain" not in tree

    def test_workspace_topics_fold_into_one_text(self, tmp_path: Path) -> None:
        workspace = self._migrated(tmp_path)["workspace"]
        assert workspace == "Encode relations structurally.\n\nState principles generally."

    def test_migrated_document_reloads_through_the_runtime_parser(self, tmp_path: Path) -> None:
        """The point of migrating rather than header-patching: the result is a document the
        overlay parser reads, with the type guidance intact."""
        from src.domain.guidance.guidance import GuidanceKey, guidance_overlay_from_mapping

        overlay = guidance_overlay_from_mapping(self._migrated(tmp_path))
        entry = overlay.get(GuidanceKey(module_alias=_ALIAS, concept_kind="entity", type_name="goal"))
        assert entry is not None and entry.create_when == "cw"

    def test_idempotent_second_run_is_noop(self, tmp_path: Path) -> None:
        doc = tmp_path / f"{_ALIAS}.guidance.yaml"
        doc.write_text(_SUPERSEDED_DOC, encoding="utf-8")
        _run(tmp_path)
        assert _run(tmp_path) == []

    def test_newer_document_is_not_rewritten(self, tmp_path: Path) -> None:
        doc = tmp_path / "a.guidance.yaml"
        doc.write_text("guidance_format: 99\n", encoding="utf-8")
        _run(tmp_path)
        assert doc.read_text(encoding="utf-8") == "guidance_format: 99\n"

    def test_unknown_alias_is_not_rewritten(self, tmp_path: Path) -> None:
        doc = tmp_path / f"{_ALIAS}.guidance.yaml"
        doc.write_text(_SUPERSEDED_DOC, encoding="utf-8")
        assert _run(tmp_path, hierarchies={}) == []
        assert doc.read_text(encoding="utf-8") == _SUPERSEDED_DOC
