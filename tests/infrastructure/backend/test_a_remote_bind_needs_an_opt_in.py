"""A backend with no authentication listens beyond the loopback only when the operator says so.

Regression: `arch-backend --host 0.0.0.0` started without a word, serving every repository and the
assurance unlock to whatever reached the address.
"""

from __future__ import annotations

import pytest

from src.infrastructure.backend import arch_backend
from src.infrastructure.backend.backend_process import serving_flags
from src.infrastructure.backend.bind_policy import (
    REMOTE_OPT_IN_FLAG,
    REMOTE_OPT_IN_SETTING,
    bind_refusal,
    is_loopback,
)


@pytest.mark.parametrize("host", ["127.0.0.1", "127.8.0.1", "localhost", "LOCALHOST", "::1", "[::1]"])
def test_the_loopback_needs_no_opt_in(host: str) -> None:
    assert is_loopback(host)
    assert bind_refusal(host, opted_in=False) is None


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "10.20.20.34", "arch.internal", ""])
def test_any_other_address_is_refused_naming_both_opt_ins(host: str) -> None:
    refusal = bind_refusal(host, opted_in=False)

    assert refusal is not None
    assert REMOTE_OPT_IN_FLAG in refusal
    assert REMOTE_OPT_IN_SETTING in refusal


def test_an_opt_in_permits_it() -> None:
    assert bind_refusal("0.0.0.0", opted_in=True) is None


class TestTheEntryPoint:
    """`main` refuses before it does anything that starts a server."""

    @pytest.fixture(autouse=True)
    def _nothing_starts(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        started: list[str] = []
        monkeypatch.setattr(arch_backend, "resolve_backend_port", lambda start=None, explicit_port=None: 8123)
        monkeypatch.setattr(arch_backend, "_is_background_tty_job", lambda: False)
        monkeypatch.setattr(arch_backend, "_start", lambda *args, **kwargs: started.append("started"))
        monkeypatch.setattr(arch_backend, "backend_allows_remote_without_auth", lambda: False)
        return started

    def test_a_remote_host_without_an_opt_in_exits_before_starting(
        self, capsys: pytest.CaptureFixture[str], _nothing_starts: list[str],
    ) -> None:
        with pytest.raises(SystemExit) as exit_info:
            arch_backend.main(["--host", "0.0.0.0"])

        assert exit_info.value.code == 2
        assert REMOTE_OPT_IN_FLAG in capsys.readouterr().err
        assert _nothing_starts == []

    def test_the_flag_opts_in(self, _nothing_starts: list[str]) -> None:
        arch_backend.main(["--host", "0.0.0.0", REMOTE_OPT_IN_FLAG])

        assert _nothing_starts == ["started"]

    def test_the_setting_opts_in(self, monkeypatch: pytest.MonkeyPatch, _nothing_starts: list[str]) -> None:
        monkeypatch.setattr(arch_backend, "backend_allows_remote_without_auth", lambda: True)

        arch_backend.main(["--host", "0.0.0.0"])

        assert _nothing_starts == ["started"]

    def test_the_default_host_starts(self, _nothing_starts: list[str]) -> None:
        arch_backend.main([])

        assert _nothing_starts == ["started"]


def test_a_restart_keeps_the_opt_in() -> None:
    """Without it, an update restarting an opted-in backend would be refused at start."""
    argv = ["arch-backend", "--host", "0.0.0.0", REMOTE_OPT_IN_FLAG, "--port", "8000"]

    assert serving_flags(argv) == ["--host", "0.0.0.0", REMOTE_OPT_IN_FLAG]


def test_the_setting_is_read_only_as_a_literal_true(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    for value, expected in ((True, True), ("true", False), (1, False), (False, False)):
        section = {"backend": {"allow_remote_without_auth": value}}
        monkeypatch.setattr(settings, "load_settings", lambda section=section: section)
        assert settings.backend_allows_remote_without_auth() is expected


def test_the_container_opts_in_to_the_bind_its_entrypoint_makes() -> None:
    """The image activates the server settings; its entrypoint listens on all interfaces."""
    import yaml

    from tests.support.source_paths import REPO_ROOT

    entrypoint = (REPO_ROOT / "docker" / "entrypoint.sh").read_text(encoding="utf-8")
    server_settings = yaml.safe_load((REPO_ROOT / "config" / "settings.server.yaml").read_text(encoding="utf-8"))
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "--host 0.0.0.0" in entrypoint
    assert "cp /app/config/settings.server.yaml /app/config/settings.yaml" in dockerfile
    assert server_settings["backend"]["allow_remote_without_auth"] is True
