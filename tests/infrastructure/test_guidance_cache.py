from __future__ import annotations

from pathlib import Path

import pytest

import src.infrastructure.guidance_cache as guidance_cache_module
from src.domain.guidance.guidance import GUIDANCE_FORMAT, GuidanceKey
from src.infrastructure.guidance_cache import (
    guidance_cache_root,
    load_guidance_overlay,
    load_workspace_guidance,
)

_ALIAS = "archimate-4"


@pytest.fixture(autouse=True)
def _isolated_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(guidance_cache_module, "_CONFIG_DIR", tmp_path / ".config" / "arch-repo")


def _write_cache(text: str) -> None:
    cache_dir = guidance_cache_root()
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{_ALIAS}.guidance.yaml").write_text(text, encoding="utf-8")


def _key(type_name: str) -> GuidanceKey:
    return GuidanceKey(module_alias=_ALIAS, concept_kind="entity", type_name=type_name)


class TestLoadGuidanceOverlay:
    def test_absent_file_returns_empty_overlay(self) -> None:
        overlay = load_guidance_overlay(_ALIAS)
        assert overlay.is_empty()

    def test_present_file_parses_into_overlay(self) -> None:
        _write_cache(
            """
            meta_ontologies:
              archimate-4:
                motivation:
                  entity_types:
                    stakeholder:
                      create_when: "c"
                      never_create_when: "n"
            """,
        )
        overlay = load_guidance_overlay(_ALIAS)
        entry = overlay.get(_key("stakeholder"))
        assert entry is not None
        assert entry.create_when == "c"

    def test_malformed_yaml_top_level_returns_empty_overlay(self) -> None:
        _write_cache("- just\n- a\n- list\n")
        assert load_guidance_overlay(_ALIAS).is_empty()

    def test_one_deployment_level_cache_is_alias_scoped_only(self) -> None:
        """No repository-tier distinction: the cache is keyed only by module alias, not by
        which engagement/enterprise repo happens to be active."""
        _write_cache(
            """
            meta_ontologies:
              archimate-4:
                motivation:
                  entity_types:
                    stakeholder: {create_when: "one source", never_create_when: "n"}
            """,
        )
        overlay = load_guidance_overlay(_ALIAS)
        assert overlay.get(_key("stakeholder")) is not None
        assert load_guidance_overlay("some-other-alias").is_empty()


class TestLoadWorkspaceGuidance:
    def _write_workspace(self, text: str) -> None:
        cache_dir = guidance_cache_root()
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "workspace.guidance.yaml").write_text(text, encoding="utf-8")

    def test_absent_file_returns_empty(self) -> None:
        assert load_workspace_guidance().is_empty()

    def test_present_file_parses_the_level_text(self) -> None:
        self._write_workspace(
            f"""
            guidance_format: {GUIDANCE_FORMAT}
            workspace: "Encode relations structurally."
            """,
        )
        assert load_workspace_guidance().context == "Encode relations structurally."

    def test_malformed_top_level_returns_empty(self) -> None:
        self._write_workspace("- not\n- a\n- mapping\n")
        assert load_workspace_guidance().is_empty()
