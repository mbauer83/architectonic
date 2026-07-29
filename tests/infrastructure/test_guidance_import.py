from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.guidance.guidance import GUIDANCE_FORMAT
from src.domain.modules.module_registry import ModuleRegistry
from src.infrastructure.app_bootstrap import build_module_registry
from src.infrastructure.guidance_import import (
    GuidanceImportError,
    fetch_source,
    filter_alias_document,
    filter_workspace_section,
    select_aliases,
    validate_schema,
)


class TestValidateSchema:
    def test_accepts_valid_document(self) -> None:
        data = {"guidance_format": GUIDANCE_FORMAT, "meta_ontologies": {"archimate-4": {}}}
        assert validate_schema(data) == data

    def test_accepts_workspace_only_document(self) -> None:
        data = {"guidance_format": GUIDANCE_FORMAT, "workspace": "One cross-cutting stance."}
        assert validate_schema(data) == data

    def test_rejects_non_mapping(self) -> None:
        with pytest.raises(GuidanceImportError, match="mapping"):
            validate_schema(["not", "a", "mapping"])

    def test_rejects_superseded_format_with_migration_hint(self) -> None:
        with pytest.raises(GuidanceImportError, match="arch-repair upgrade"):
            validate_schema({"guidance_format": GUIDANCE_FORMAT - 1, "meta_ontologies": {"archimate-4": {}}})

    def test_rejects_document_with_neither_section(self) -> None:
        with pytest.raises(GuidanceImportError, match="at least one"):
            validate_schema({"guidance_format": GUIDANCE_FORMAT})

    def test_rejects_workspace_map_from_the_superseded_shape(self) -> None:
        with pytest.raises(GuidanceImportError, match="single guidance text"):
            validate_schema({"guidance_format": GUIDANCE_FORMAT, "workspace": {"topic": {"context": "x"}}})


class TestSelectAliases:
    def test_no_module_returns_all_aliases(self) -> None:
        data = {"meta_ontologies": {"archimate-4": {"a": 1}, "sysml-v2": {"b": 2}}}
        assert select_aliases(data, None) == {"archimate-4": {"a": 1}, "sysml-v2": {"b": 2}}

    def test_module_filters_to_one_alias(self) -> None:
        data = {"meta_ontologies": {"archimate-4": {"a": 1}, "sysml-v2": {"b": 2}}}
        assert select_aliases(data, "archimate-4") == {"archimate-4": {"a": 1}}

    def test_unknown_module_raises(self) -> None:
        data = {"meta_ontologies": {"archimate-4": {}}}
        with pytest.raises(GuidanceImportError, match="not present"):
            select_aliases(data, "no-such-alias")

    def test_absent_meta_ontologies_yields_no_aliases(self) -> None:
        assert select_aliases({"workspace": "One cross-cutting stance."}, None) == {}


class TestFilterWorkspaceSection:
    def test_text_matched(self) -> None:
        summary = filter_workspace_section("Encode relations structurally.", strict=False)
        assert summary.alias == "workspace"
        assert summary.matched_keys == ("workspace",)
        assert summary.unmatched_keys == ()
        assert summary.filtered_document["workspace"] == "Encode relations structurally."
        assert summary.filtered_document["guidance_format"] == GUIDANCE_FORMAT

    def test_blank_text_reported_when_not_strict(self) -> None:
        summary = filter_workspace_section("   ", strict=False)
        assert summary.matched_keys == ()
        assert summary.unmatched_keys == ("workspace",)
        assert summary.filtered_document["workspace"] == ""

    def test_blank_text_raises_when_strict(self) -> None:
        with pytest.raises(GuidanceImportError, match="workspace guidance is empty"):
            filter_workspace_section("", strict=True)


class TestFilterAliasDocument:
    """Placement validation itself lives in ``src.domain.guidance.guidance_document`` (see
    ``tests/domain/test_guidance_document.py``); these cover the import-facing contract: the alias
    must resolve to a registered module, and unmatched keys abort only under ``--strict``."""

    @pytest.fixture
    def registry(self) -> ModuleRegistry:
        return build_module_registry()

    def test_known_entity_type_matched(self, registry: ModuleRegistry) -> None:
        alias_data = {"motivation": {"entity_types": {"stakeholder": {"create_when": "c", "never_create_when": "n"}}}}
        summary = filter_alias_document("archimate-4", alias_data, registry, strict=False)
        assert summary.matched_keys == ("motivation.entity_types.stakeholder",)
        assert summary.unmatched_keys == ()
        tree = summary.filtered_document["meta_ontologies"]["archimate-4"]
        assert tree["motivation"]["entity_types"]["stakeholder"]["create_when"] == "c"

    def test_unknown_entity_type_listed_and_dropped_when_not_strict(self, registry: ModuleRegistry) -> None:
        alias_data = {"motivation": {"entity_types": {"not-a-real-type": {"create_when": "c"}}}}
        summary = filter_alias_document("archimate-4", alias_data, registry, strict=False)
        assert summary.unmatched_keys == ("motivation.entity_types.not-a-real-type",)
        assert summary.filtered_document["meta_ontologies"]["archimate-4"] == {}

    def test_unknown_entity_type_raises_when_strict(self, registry: ModuleRegistry) -> None:
        alias_data = {"motivation": {"entity_types": {"not-a-real-type": {"create_when": "c"}}}}
        with pytest.raises(GuidanceImportError, match="not-a-real-type"):
            filter_alias_document("archimate-4", alias_data, registry, strict=True)

    def test_unknown_module_alias_raises(self, registry: ModuleRegistry) -> None:
        with pytest.raises(GuidanceImportError, match="no-such-alias"):
            filter_alias_document("no-such-alias", {}, registry, strict=False)

    def test_non_mapping_alias_data_raises(self, registry: ModuleRegistry) -> None:
        with pytest.raises(GuidanceImportError, match="mapping"):
            filter_alias_document("archimate-4", "not-a-mapping", registry, strict=False)

    def test_connection_types_section_validated_too(self, registry: ModuleRegistry) -> None:
        alias_data = {"connection_types": {"not-a-real-connection": {}}}
        summary = filter_alias_document("archimate-4", alias_data, registry, strict=False)
        assert summary.unmatched_keys == ("connection_types.not-a-real-connection",)

    def test_connection_guidance_kept_at_the_root(self, registry: ModuleRegistry) -> None:
        alias_data = {"connection_types": {"archimate-serving": {"create_when": "c", "never_create_when": "n"}}}
        summary = filter_alias_document("archimate-4", alias_data, registry, strict=False)
        assert summary.matched_keys == ("connection_types.archimate-serving",)
        tree = summary.filtered_document["meta_ontologies"]["archimate-4"]
        assert tree["connection_types"]["archimate-serving"]["create_when"] == "c"

    def test_known_specialization_slug_matched(self, registry: ModuleRegistry) -> None:
        alias_data = {
            "common": {
                "entity_types": {
                    "service": {
                        "specializations": {"business-service": {"create_when": "c", "never_create_when": "n"}}
                    }
                }
            }
        }
        summary = filter_alias_document("archimate-4", alias_data, registry, strict=False)
        assert summary.matched_keys == (
            "common.entity_types.service",
            "common.entity_types.service.specializations.business-service",
        )
        assert summary.unmatched_keys == ()
        tree = summary.filtered_document["meta_ontologies"]["archimate-4"]
        filtered_service = tree["common"]["entity_types"]["service"]
        assert filtered_service["specializations"]["business-service"]["create_when"] == "c"

    def test_unknown_specialization_slug_raises_when_strict(self, registry: ModuleRegistry) -> None:
        alias_data = {
            "common": {"entity_types": {"service": {"specializations": {"not-a-real-slug": {"create_when": "c"}}}}}
        }
        with pytest.raises(GuidanceImportError, match="not-a-real-slug"):
            filter_alias_document("archimate-4", alias_data, registry, strict=True)


class TestFetchSource:
    def test_reads_local_file(self, tmp_path: Path) -> None:
        source = tmp_path / "guidance.yaml"
        source.write_text("hello", encoding="utf-8")
        assert fetch_source(str(source), allow_http=False) == b"hello"

    def test_missing_local_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(GuidanceImportError, match="not found"):
            fetch_source(str(tmp_path / "missing.yaml"), allow_http=False)

    def test_oversize_local_file_raises(self, tmp_path: Path) -> None:
        from src.infrastructure.guidance_import import _MAX_SOURCE_BYTES

        source = tmp_path / "big.yaml"
        source.write_bytes(b"x" * (_MAX_SOURCE_BYTES + 1))
        with pytest.raises(GuidanceImportError, match="size cap"):
            fetch_source(str(source), allow_http=False)

    def test_plain_http_rejected_by_default(self) -> None:
        with pytest.raises(GuidanceImportError, match="allow-http"):
            fetch_source("http://example.invalid/guidance.yaml", allow_http=False)
