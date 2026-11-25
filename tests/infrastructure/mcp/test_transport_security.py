"""The MCP mounts' DNS-rebinding settings come from the application's one host list."""

from __future__ import annotations

import pytest

from src.config.allowed_hosts import ENV_ALLOWED_HOSTS, ENV_ALLOWED_HOSTS_FORMER
from src.infrastructure.mcp.transport_security import build_transport_security

_ORIGINS = "ARCH_MCP_ALLOWED_ORIGINS"


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (ENV_ALLOWED_HOSTS, ENV_ALLOWED_HOSTS_FORMER, _ORIGINS):
        monkeypatch.delenv(name, raising=False)


def test_unset_allows_the_loopback_names_only() -> None:
    settings = build_transport_security()
    assert settings.enable_dns_rebinding_protection is True
    assert "localhost:*" in settings.allowed_hosts
    assert "127.0.0.1:*" in settings.allowed_hosts
    assert not any("10.20.20.34" in host for host in settings.allowed_hosts)


def test_wildcard_disables_protection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_ALLOWED_HOSTS, "*")
    assert build_transport_security().enable_dns_rebinding_protection is False


@pytest.mark.parametrize("variable", [ENV_ALLOWED_HOSTS, ENV_ALLOWED_HOSTS_FORMER])
def test_explicit_host_is_allowed_alongside_localhost(monkeypatch: pytest.MonkeyPatch, variable: str) -> None:
    monkeypatch.setenv(variable, "10.20.20.34:8000, arch.internal:*")
    settings = build_transport_security()
    assert settings.enable_dns_rebinding_protection is True
    assert "10.20.20.34:8000" in settings.allowed_hosts
    assert "arch.internal:*" in settings.allowed_hosts
    # A name without a port matches `name:*` in the application's list; the SDK needs it spelled.
    assert "arch.internal" in settings.allowed_hosts
    assert "127.0.0.1:*" in settings.allowed_hosts
    assert "localhost:*" in settings.allowed_hosts


def test_origins_are_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_ORIGINS, "https://arch.internal:*")
    settings = build_transport_security()
    assert "https://arch.internal:*" in settings.allowed_origins
    assert "http://localhost:*" in settings.allowed_origins
