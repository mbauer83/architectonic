"""Tests for app_bootstrap's guidance-overlay wiring (WU-B2).

Guidance is a deployment concern, not a per-repository-tier one: one deployment-level cache,
never split per engagement/enterprise repo. Covers: the cache-present/absent cases via the
real out-of-repo cache path, and the "no cache imported yet" fallback that keeps current
(pre-guidance) behavior.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import src.infrastructure.guidance_cache as guidance_cache_module
from src.infrastructure import app_bootstrap
from src.ontologies.archimate_4._loader import _PACKAGE_DIR, load_archimate_4_module
from src.ontologies.archimate_4._loader import META_ONTOLOGY_ALIAS as _ARCHIMATE_META_ALIAS


@pytest.fixture(autouse=True)
def _isolated_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(guidance_cache_module, "_CONFIG_DIR", tmp_path / ".config" / "arch-repo")


def _write_cache(text: str) -> None:
    cache_dir = guidance_cache_module.guidance_cache_root()
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "archimate-4.guidance.yaml").write_text(text, encoding="utf-8")


class TestLoadArchimateGuidanceOverlay:
    def test_no_cache_imported_returns_empty_overlay(self) -> None:
        overlay = app_bootstrap._load_guidance_overlay(_ARCHIMATE_META_ALIAS)
        assert overlay.is_empty()

    def test_imported_cache_surfaces_through_the_module(self) -> None:
        _write_cache(
            """
            meta_ontologies:
              archimate-4:
                entity_types:
                  stakeholder: {create_when: "imported", never_create_when: "n"}
            """,
        )

        overlay = app_bootstrap._load_guidance_overlay(_ARCHIMATE_META_ALIAS)
        module = load_archimate_4_module(_PACKAGE_DIR, guidance=overlay)

        assert module.entity_types["stakeholder"].create_when == "imported"

    def test_absent_cache_matches_current_behavior(self) -> None:
        """No guidance-cache file imported yet — module ships its own (usually empty) text."""
        overlay = app_bootstrap._load_guidance_overlay(_ARCHIMATE_META_ALIAS)
        assert overlay.is_empty()

        with_overlay = load_archimate_4_module(_PACKAGE_DIR, guidance=overlay)
        without_overlay = load_archimate_4_module(_PACKAGE_DIR)
        assert (
            with_overlay.entity_types["stakeholder"].create_when
            == without_overlay.entity_types["stakeholder"].create_when
        )
