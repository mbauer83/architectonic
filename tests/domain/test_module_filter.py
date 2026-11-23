"""Unit tests for module_filter.module_skip_reason."""

from __future__ import annotations

from src.domain.modules.module_filter import module_skip_reason


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
        assert module_skip_reason(_Stub("m"), {}, set()) is None

    def test_disabled_by_manifest(self) -> None:
        assert module_skip_reason(_Stub("m", enabled=False), {}, set()) == "disabled"

    def test_disabled_by_yaml_override(self) -> None:
        assert module_skip_reason(_Stub("m"), {"m": {"enabled": False}}, set()) == "disabled"

    def test_yaml_can_re_enable_disabled_manifest(self) -> None:
        assert module_skip_reason(_Stub("m", enabled=False), {"m": {"enabled": True}}, set()) is None

    def test_requires_satisfied(self) -> None:
        assert module_skip_reason(_Stub("m", requires=["dep"]), {}, {"dep"}) is None

    def test_requires_unsatisfied_fails_closed(self) -> None:
        assert module_skip_reason(_Stub("m", requires=["confidential_store"]), {}, set()) == (
            "required capability/module 'confidential_store' is not available"
        )

    def test_missing_enabled_attr_defaults_true(self) -> None:
        class _Bare:
            name = "bare"

        assert module_skip_reason(_Bare(), {}, set()) is None

    def test_missing_requires_attr_defaults_empty(self) -> None:
        class _Bare:
            name = "bare"
            enabled = True

        assert module_skip_reason(_Bare(), {}, set()) is None

    def test_yaml_entry_without_enabled_key_has_no_effect(self) -> None:
        assert module_skip_reason(_Stub("m"), {"m": {}}, set()) is None
