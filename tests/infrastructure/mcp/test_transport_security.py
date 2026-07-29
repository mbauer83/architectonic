"""Env-driven MCP transport security allowlist (DNS-rebinding protection)."""

from __future__ import annotations

import pytest

from src.infrastructure.mcp.transport_security import build_transport_security

_HOSTS = "ARCH_MCP_ALLOWED_HOSTS"
_ORIGINS = "ARCH_MCP_ALLOWED_ORIGINS"


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_HOSTS, raising=False)
    monkeypatch.delenv(_ORIGINS, raising=False)


def test_unset_keeps_sdk_default(monkeypatch: pytest.MonkeyPatch) -> None:
    assert build_transport_security() is None


def test_wildcard_disables_protection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_HOSTS, "*")
    settings = build_transport_security()
    assert settings is not None
    assert settings.enable_dns_rebinding_protection is False


def test_explicit_host_is_allowed_alongside_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_HOSTS, "10.20.20.34:8000, arch.internal:*")
    settings = build_transport_security()
    assert settings is not None
    assert settings.enable_dns_rebinding_protection is True
    # The deployment host is permitted ...
    assert "10.20.20.34:8000" in settings.allowed_hosts
    assert "arch.internal:*" in settings.allowed_hosts
    # ... without losing local access.
    assert "127.0.0.1:*" in settings.allowed_hosts
    assert "localhost:*" in settings.allowed_hosts


def test_origins_are_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_ORIGINS, "https://arch.internal:*")
    settings = build_transport_security()
    assert settings is not None
    assert "https://arch.internal:*" in settings.allowed_origins
    assert "http://localhost:*" in settings.allowed_origins
