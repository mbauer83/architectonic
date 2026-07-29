"""Unit tests for module_overrides() settings function."""

from __future__ import annotations

from unittest.mock import patch

from src.config.settings import module_overrides


class TestModuleOverrides:
    def test_empty_modules_section_returns_empty(self) -> None:
        with patch("src.config.settings.load_settings", return_value={"modules": {}}):
            assert module_overrides() == {}

    def test_absent_modules_section_returns_empty(self) -> None:
        with patch("src.config.settings.load_settings", return_value={}):
            assert module_overrides() == {}

    def test_enabled_false_override_parsed(self) -> None:
        settings = {"modules": {"sysml_v2_min": {"enabled": False}}}
        with patch("src.config.settings.load_settings", return_value=settings):
            result = module_overrides()
        assert result == {"sysml_v2_min": {"enabled": False}}

    def test_enabled_true_override_parsed(self) -> None:
        settings = {"modules": {"assurance": {"enabled": True}}}
        with patch("src.config.settings.load_settings", return_value=settings):
            result = module_overrides()
        assert result["assurance"] == {"enabled": True}

    def test_non_dict_module_entry_ignored(self) -> None:
        settings = {"modules": {"bad-entry": "not-a-dict"}}
        with patch("src.config.settings.load_settings", return_value=settings):
            assert module_overrides() == {}

    def test_non_dict_modules_section_returns_empty(self) -> None:
        settings = {"modules": "not-a-dict"}
        with patch("src.config.settings.load_settings", return_value=settings):
            assert module_overrides() == {}

    def test_requires_key_in_yaml_is_not_surfaced(self) -> None:
        # 'requires' is a manifest declaration; YAML overrides only support 'enabled'.
        settings = {"modules": {"m": {"enabled": True, "requires": ["dep"]}}}
        with patch("src.config.settings.load_settings", return_value=settings):
            result = module_overrides()
        assert "requires" not in result.get("m", {})
