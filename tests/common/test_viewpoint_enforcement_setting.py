"""Tests for the ``viewpoint_enforcement`` validation setting (off|warn|ghost, default warn)."""

from __future__ import annotations

import pytest

from src.config.settings import viewpoint_enforcement_setting


def test_defaults_to_warn(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    monkeypatch.setattr(settings, "load_settings", lambda: {"validation": {}})
    assert viewpoint_enforcement_setting() == "warn"


def test_reads_configured_value(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    monkeypatch.setattr(settings, "load_settings", lambda: {"validation": {"viewpoint_enforcement": "off"}})
    assert viewpoint_enforcement_setting() == "off"


def test_invalid_value_falls_back_to_warn(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    monkeypatch.setattr(settings, "load_settings", lambda: {"validation": {"viewpoint_enforcement": "sometimes"}})
    assert viewpoint_enforcement_setting() == "warn"
