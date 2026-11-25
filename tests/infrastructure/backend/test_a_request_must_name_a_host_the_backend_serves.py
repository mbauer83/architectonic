"""The whole application refuses a request addressed to a name it does not serve.

Regression: only the MCP mounts checked the `Host` header. A web page whose domain was re-pointed at
127.0.0.1 could read and write a loopback backend through REST — including unlocking the assurance
store — because REST answered any name.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.config.allowed_hosts import ENV_ALLOWED_HOSTS, ENV_ALLOWED_HOSTS_FORMER, AllowedHosts, allowed_hosts
from src.infrastructure.backend.arch_backend_app import _build_app
from src.infrastructure.backend.host_guard import HOST_REFUSED_STATUS


@pytest.fixture(autouse=True)
def _no_configured_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_ALLOWED_HOSTS, raising=False)
    monkeypatch.delenv(ENV_ALLOWED_HOSTS_FORMER, raising=False)


class TestTheList:
    @pytest.mark.parametrize(
        "host", ["localhost", "localhost:8000", "127.0.0.1:5173", "[::1]:8000", "LOCALHOST:8000"],
    )
    def test_the_loopback_names_are_allowed_by_default(self, host: str) -> None:
        assert allowed_hosts().permits(host)

    @pytest.mark.parametrize(
        "host", ["attacker.example", "attacker.example:8000", "localhost.attacker.example", "", None],
    )
    def test_anything_else_is_not(self, host: str | None) -> None:
        assert not allowed_hosts().permits(host)

    def test_a_configured_name_is_added(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ENV_ALLOWED_HOSTS, "arch.internal:*, 10.20.20.34:8000")
        hosts = allowed_hosts()

        assert hosts.permits("arch.internal")
        assert hosts.permits("arch.internal:443")
        assert hosts.permits("10.20.20.34:8000")
        assert not hosts.permits("10.20.20.34:9000")
        assert hosts.permits("localhost:8000")

    def test_the_former_variable_is_still_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ENV_ALLOWED_HOSTS_FORMER, "arch.internal:*")
        assert allowed_hosts().permits("arch.internal:8000")

    def test_a_star_turns_the_check_off(self) -> None:
        assert AllowedHosts(entries=None).permits("anything.example")


class TestTheApplication:
    @pytest.fixture
    def app(self) -> object:
        return _build_app()

    @pytest.mark.parametrize("path", ["/health", "/api/modules", "/", "/mcp/read"])
    def test_a_foreign_name_is_refused_on_every_surface(self, app: object, path: str) -> None:
        client = TestClient(app, base_url="http://attacker.example:8000")  # type: ignore[arg-type]

        response = client.get(path)

        assert response.status_code == HOST_REFUSED_STATUS
        assert ENV_ALLOWED_HOSTS in response.text

    def test_the_assurance_unlock_is_refused_under_a_foreign_name(self, app: object) -> None:
        client = TestClient(app, base_url="http://attacker.example:8000")  # type: ignore[arg-type]

        response = client.post("/api/assurance/reload", json={"authorize": True})

        assert response.status_code == HOST_REFUSED_STATUS

    def test_a_loopback_name_is_served(self, app: object) -> None:
        client = TestClient(app, base_url="http://localhost:8000")  # type: ignore[arg-type]

        assert client.get("/health").status_code == 200
