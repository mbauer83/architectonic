"""Unit tests for module_filter.is_module_enabled."""

from __future__ import annotations

from src.domain.modules.module_filter import is_module_enabled


class _Stub:
    def __init__(
        self,
        name: str,
        enabled: bool = True,
        requires: list[str] | None = None,
    ) -> None:
        self.name = name
        self.enabled = enabled
        self.requires = requires or []


class TestIsModuleEnabled:
    def test_enabled_by_default_no_requires(self) -> None:
        assert is_module_enabled(_Stub("m"), {}, set()) is True

    def test_disabled_by_manifest(self) -> None:
        assert is_module_enabled(_Stub("m", enabled=False), {}, set()) is False

    def test_disabled_by_yaml_override(self) -> None:
        assert is_module_enabled(_Stub("m"), {"m": {"enabled": False}}, set()) is False

    def test_yaml_can_re_enable_disabled_manifest(self) -> None:
        assert is_module_enabled(_Stub("m", enabled=False), {"m": {"enabled": True}}, set()) is True

    def test_requires_satisfied(self) -> None:
        assert is_module_enabled(_Stub("m", requires=["dep"]), {}, {"dep"}) is True

    def test_requires_unsatisfied_fails_closed(self) -> None:
        assert is_module_enabled(_Stub("m", requires=["confidential_store"]), {}, set()) is False

    def test_missing_enabled_attr_defaults_true(self) -> None:
        class _Bare:
            name = "bare"

        assert is_module_enabled(_Bare(), {}, set()) is True

    def test_missing_requires_attr_defaults_empty(self) -> None:
        class _Bare:
            name = "bare"
            enabled = True

        assert is_module_enabled(_Bare(), {}, set()) is True

    def test_yaml_entry_without_enabled_key_has_no_effect(self) -> None:
        assert is_module_enabled(_Stub("m"), {"m": {}}, set()) is True
