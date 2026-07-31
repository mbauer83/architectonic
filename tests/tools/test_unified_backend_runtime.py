from __future__ import annotations

from pathlib import Path

import yaml

from src.config import settings
from src.domain.modules.module_registry import ModuleRegistry
from src.infrastructure.app_bootstrap import module_registry_dependency, module_registry_from_app
from src.infrastructure.backend import (
    _lifecycle_cli,
    arch_backend,
    backend_control,
    backend_probe,
    backend_process,
    backend_state,
)
from src.infrastructure.backend.arch_backend_app import _build_app
from src.infrastructure.mcp import arch_mcp_stdio, arch_mcp_stdio_assurance


def test_arch_mcp_stdio_read_connects_to_read_path(monkeypatch) -> None:
    """arch-mcp-stdio (default) bridges to /mcp/read."""
    urls: list[str] = []

    def fake_anyio_run(fn, url: str) -> None:
        urls.append(url)

    monkeypatch.setattr(arch_mcp_stdio.anyio, "run", fake_anyio_run)
    monkeypatch.setattr(
        arch_mcp_stdio, "ensure_backend_running", lambda port, start_if_missing, cwd=None, project_dir=None: port
    )
    monkeypatch.setattr(arch_mcp_stdio, "configured_backend_url", lambda: None)

    arch_mcp_stdio.main([])

    assert urls and urls[0].endswith("/mcp/read")


def test_arch_mcp_stdio_write_connects_to_write_path(monkeypatch) -> None:
    """arch-mcp-stdio --server write bridges to /mcp/write."""
    urls: list[str] = []

    def fake_anyio_run(fn, url: str) -> None:
        urls.append(url)

    monkeypatch.setattr(arch_mcp_stdio.anyio, "run", fake_anyio_run)
    monkeypatch.setattr(
        arch_mcp_stdio, "ensure_backend_running", lambda port, start_if_missing, cwd=None, project_dir=None: port
    )
    monkeypatch.setattr(arch_mcp_stdio, "configured_backend_url", lambda: None)

    arch_mcp_stdio.main(["--server", "write"])

    assert urls and urls[0].endswith("/mcp/write")


def test_arch_mcp_stdio_uses_workspace_directory_for_autostart(monkeypatch, tmp_path: Path) -> None:
    calls: dict[str, object] = {}
    workspace_dir = tmp_path / "workspace"
    project_dir = tmp_path / "tooling"
    workspace_dir.mkdir()
    project_dir.mkdir()

    monkeypatch.setattr(arch_mcp_stdio.anyio, "run", lambda fn, url: None)
    monkeypatch.setattr(arch_mcp_stdio, "_project_directory", lambda: project_dir)
    monkeypatch.chdir(workspace_dir)

    def fake_resolve_backend_port(start=None, explicit_port=None):
        calls["resolve_start"] = start
        return 8123

    monkeypatch.setattr(
        arch_mcp_stdio,
        "resolve_backend_port",
        fake_resolve_backend_port,
    )
    monkeypatch.setattr(
        arch_mcp_stdio,
        "ensure_backend_running",
        lambda port, start_if_missing, cwd=None, project_dir=None: (
            calls.setdefault("ensure_port", port),
            calls.setdefault("ensure_cwd", cwd),
            calls.setdefault("ensure_project_dir", project_dir),
            8123,
        )[-1],
    )
    monkeypatch.setattr(arch_mcp_stdio, "configured_backend_url", lambda: None)

    arch_mcp_stdio.main([])

    assert calls["resolve_start"] == workspace_dir
    assert calls["ensure_port"] == 8123
    assert calls["ensure_cwd"] == workspace_dir
    assert calls["ensure_project_dir"] == project_dir


def test_assurance_bridge_read_connects_to_assurance_read_path(monkeypatch) -> None:
    """arch-mcp-stdio-assurance-read bridges to /mcp/assurance-read via HTTP."""
    urls: list[str] = []

    monkeypatch.setattr(arch_mcp_stdio.anyio, "run", lambda fn, url: urls.append(url))
    monkeypatch.setattr(
        arch_mcp_stdio, "ensure_backend_running", lambda port, start_if_missing, cwd=None, project_dir=None: port
    )
    monkeypatch.setattr(arch_mcp_stdio, "configured_backend_url", lambda: None)

    arch_mcp_stdio_assurance.main_read([])

    assert urls and urls[0].endswith("/mcp/assurance-read")


def test_assurance_bridge_write_connects_to_assurance_write_path(monkeypatch) -> None:
    """arch-mcp-stdio-assurance-write bridges to /mcp/assurance-write via HTTP."""
    urls: list[str] = []

    monkeypatch.setattr(arch_mcp_stdio.anyio, "run", lambda fn, url: urls.append(url))
    monkeypatch.setattr(
        arch_mcp_stdio, "ensure_backend_running", lambda port, start_if_missing, cwd=None, project_dir=None: port
    )
    monkeypatch.setattr(arch_mcp_stdio, "configured_backend_url", lambda: None)

    arch_mcp_stdio_assurance.main_write([])

    assert urls and urls[0].endswith("/mcp/assurance-write")


def test_backend_state_path_falls_back_without_arch_init(tmp_path: Path) -> None:
    path = backend_state.backend_state_path(tmp_path)
    assert path == tmp_path / ".arch" / "backend.pid"


def test_ensure_backend_running_requires_explicit_external_backend(monkeypatch) -> None:
    monkeypatch.setattr(backend_control, "read_backend_state", lambda start=None: None)
    monkeypatch.setattr(backend_control, "configured_backend_url", lambda: None)

    try:
        backend_control.ensure_backend_running(port=8123, start_if_missing=False)
    except RuntimeError as exc:
        assert "not running" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_ensure_backend_running_uses_explicit_external_backend(monkeypatch) -> None:
    monkeypatch.setattr(backend_control, "read_backend_state", lambda start=None: None)
    monkeypatch.setattr(backend_control, "configured_backend_url", lambda: "http://127.0.0.1:8123")
    monkeypatch.setattr(backend_control, "probe_backend_url", lambda url, timeout_s=1.0: url == "http://127.0.0.1:8123")

    port = backend_control.ensure_backend_running(port=8000, start_if_missing=False)

    assert port == 8000


def test_resolve_backend_port_uses_workspace_config(tmp_path: Path) -> None:
    config_path = tmp_path / "arch-workspace.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "engagement": {"local": "eng"},
                "enterprise": {"local": "ent"},
                "backend": {"port": 8123},
            }
        ),
        encoding="utf-8",
    )

    port = backend_probe.resolve_backend_port(start=tmp_path)

    assert port == 8123


def test_resolve_backend_port_falls_back_to_global_settings(monkeypatch) -> None:
    monkeypatch.setattr(backend_probe, "load_workspace_config", lambda start=None: None)
    monkeypatch.setattr(backend_probe, "global_backend_port", lambda: 8456)

    port = backend_probe.resolve_backend_port()

    assert port == 8456


def test_backend_log_path_uses_configured_workspace_relative_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(backend_state, "configured_backend_log_path", lambda: "runtime/backend.log")
    monkeypatch.setattr(backend_state, "workspace_root", lambda start=None: tmp_path)

    path = backend_state.backend_log_path(tmp_path / "subdir")

    assert path == tmp_path / "runtime" / "backend.log"


def test_backend_log_path_uses_configured_absolute_path(monkeypatch, tmp_path: Path) -> None:
    configured = tmp_path / "logs" / "backend.log"
    monkeypatch.setattr(backend_state, "configured_backend_log_path", lambda: str(configured))

    path = backend_state.backend_log_path()

    assert path == configured


def test_backend_min_log_level_defaults_to_info(monkeypatch) -> None:
    monkeypatch.setattr(settings, "load_settings", lambda: {"backend": {}})

    assert settings.backend_min_log_level() == "INFO"


def test_backend_min_log_level_normalizes_warn_alias(monkeypatch) -> None:
    monkeypatch.setattr(settings, "load_settings", lambda: {"backend": {"min_log_level": "warn"}})

    assert settings.backend_min_log_level() == "WARNING"


def test_backend_min_log_level_rejects_invalid_values(monkeypatch) -> None:
    monkeypatch.setattr(settings, "load_settings", lambda: {"backend": {"min_log_level": "verbose"}})

    assert settings.backend_min_log_level() == "INFO"


def test_repo_init_defaults(monkeypatch) -> None:
    monkeypatch.setattr(settings, "load_settings", lambda: {"repo_init": {}})

    assert settings.repo_init_default_branch() == "main"
    assert settings.repo_init_commit_author_name() == "arch-switch-engagement"
    assert settings.repo_init_commit_author_email() == "arch-switch-engagement@local.invalid"


def test_repo_init_engagement_overrides(monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "load_settings",
        lambda: {
            "repo_init": {
                "default_branch": "main",
                "commit_author_name": "Global Bot",
                "commit_author_email": "global@example.com",
                "engagement": {
                    "default_branch": "trunk",
                    "commit_author_name": "Engagement Bot",
                    "commit_author_email": "engagement@example.com",
                },
            }
        },
    )

    assert settings.repo_init_default_branch("engagement") == "trunk"
    assert settings.repo_init_commit_author_name("engagement") == "Engagement Bot"
    assert settings.repo_init_commit_author_email("engagement") == "engagement@example.com"


def test_backend_start_command_prefers_current_python_when_backend_deps_exist(monkeypatch) -> None:
    monkeypatch.setattr(backend_probe.importlib.util, "find_spec", lambda name: object())

    cmd = backend_probe.backend_start_command(port=8123)

    assert cmd == [backend_probe.sys.executable, "-m", "src.infrastructure.backend.arch_backend", "--port", "8123"]


def test_backend_start_command_uses_uv_with_explicit_project_when_deps_missing(monkeypatch, tmp_path: Path) -> None:
    project_dir = tmp_path / "tooling"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text("[project]\nname = 'tooling'\n", encoding="utf-8")

    monkeypatch.setattr(backend_probe.importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(backend_probe.shutil, "which", lambda name: "/usr/bin/uv" if name == "uv" else None)

    cmd = backend_probe.backend_start_command(port=8123, project_dir=project_dir)

    assert cmd == [
        "/usr/bin/uv",
        "run",
        "--project",
        str(project_dir),
        "--group",
        "gui",
        "arch-backend",
        "--port",
        "8123",
    ]


def test_backend_start_command_names_a_dependency_selector_this_project_defines() -> None:
    """The launcher's dependency selector names something pyproject.toml declares.

    uv aborts on a selector it cannot resolve, and this command's output goes to
    .arch/backend.log rather than the terminal, so a wrong one fails the launch quietly.
    """
    import tomllib

    repo_root = Path(backend_probe.__file__).resolve().parents[3]
    manifest = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    extras = set(manifest.get("project", {}).get("optional-dependencies", {}))
    groups = set(manifest.get("dependency-groups", {}))

    cmd = backend_probe.backend_start_command(port=8123, project_dir=repo_root)
    for flag, declared in (("--extra", extras), ("--group", groups)):
        if flag in cmd:
            selector = cmd[cmd.index(flag) + 1]
            assert selector in declared, (
                f"backend_start_command passes {flag} {selector!r}, which pyproject.toml "
                f"does not declare (available: {sorted(declared)})"
            )


def test_ensure_backend_running_starts_backend_in_workspace_using_project_launcher(monkeypatch, tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"
    project_dir = tmp_path / "tooling"
    workspace_dir.mkdir()
    project_dir.mkdir()

    popen_calls: dict[str, object] = {}
    probe_ports: list[int] = []
    probe_results = iter([False, True])

    monkeypatch.setattr(backend_control, "resolve_backend_port", lambda start=None, explicit_port=None: 8123)
    monkeypatch.setattr(backend_control, "read_backend_state", lambda start=None: None)
    monkeypatch.setattr(backend_control, "configured_backend_url", lambda: None)
    monkeypatch.setattr(
        backend_control,
        "backend_log_path",
        lambda start=None: workspace_dir / ".arch" / "backend.log",
    )
    monkeypatch.setattr(
        backend_control,
        "backend_start_command",
        lambda port, project_dir=None: popen_calls.setdefault("command", ["launcher", str(port), str(project_dir)]),
    )
    monkeypatch.setattr(backend_control.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(backend_control.time, "monotonic", lambda: 0.0)

    def fake_probe_backend(port, timeout_s=1.0):
        probe_ports.append(port)
        return next(probe_results)

    monkeypatch.setattr(backend_control, "probe_backend", fake_probe_backend)

    class FakePopen:
        def __init__(self, command, cwd=None, **kwargs):
            popen_calls["spawned_command"] = command
            popen_calls["cwd"] = cwd

    monkeypatch.setattr(backend_control.subprocess, "Popen", FakePopen)

    port = backend_control.ensure_backend_running(port=8123, cwd=workspace_dir, project_dir=project_dir)

    assert port == 8123
    assert popen_calls["command"] == ["launcher", "8123", str(project_dir)]
    assert popen_calls["spawned_command"] == ["launcher", "8123", str(project_dir)]
    assert popen_calls["cwd"] == str(workspace_dir)
    assert probe_ports == [8123, 8123]


def test_module_registry_registers_matrix_diagram_kind() -> None:
    registry = module_registry_from_app(_build_app())

    assert registry.find_diagram_type("matrix") is not None


def test_matches_arch_backend_process_for_console_script_path() -> None:
    argv = [
        "/home/user/project/.venv/bin/python3",
        "/home/user/project/.venv/bin/arch-backend",
        "--port",
        "8000",
    ]

    assert backend_process._matches_arch_backend_process(argv) is True


def test_matches_arch_backend_process_for_direct_binary() -> None:
    assert backend_process._matches_arch_backend_process(["arch-backend", "--port", "8000"]) is True


def test_matches_arch_backend_process_for_module_invocation() -> None:
    assert (
        backend_process._matches_arch_backend_process(
            ["python3", "-m", "src.infrastructure.backend.arch_backend", "--port", "8000"]
        )
        is True
    )


def test_matches_arch_backend_process_does_not_match_uv_launcher() -> None:
    # ``uv run ... arch-backend ...`` is the launcher, not the backend itself.
    assert (
        backend_process._matches_arch_backend_process(
            ["/home/user/.local/bin/uv", "run", "--extra", "gui", "arch-backend", "--port", "8000"]
        )
        is False
    )


def test_matches_arch_backend_process_does_not_match_bash_invoker() -> None:
    assert backend_process._matches_arch_backend_process(["/bin/bash", "-c", "arch-backend --port 8000"]) is False


def test_stop_backend_resolves_multiple_to_socket_owner(monkeypatch) -> None:
    """When multiple processes declare the same port, prefer the one with the actual socket."""
    socket_owner = {"pid": 1001, "ports": [8000], "declared_port": 8000}
    no_socket = {"pid": 1002, "ports": [], "declared_port": 8000}

    monkeypatch.setattr(backend_control, "read_backend_state", lambda start=None: None)
    monkeypatch.setattr(backend_control, "find_arch_backend_instances", lambda: [socket_owner, no_socket])

    stopped: list[int] = []

    def fake_stop_pid(pid, *, cwd=None, timeout_s=5.0, port=None):
        stopped.append(pid)
        return {"stopped": True, "pid": pid, "port": port}

    monkeypatch.setattr(backend_control, "_stop_pid", fake_stop_pid)
    # The non-socket declarant (1002) is SIGTERMed during cleanup; mock os.kill so the
    # test never signals a real, arbitrary PID (which fails non-deterministically in CI).
    killed: list[int] = []
    monkeypatch.setattr(backend_control.os, "kill", lambda pid, sig: killed.append(pid))
    monkeypatch.setattr(backend_control, "_wait_for_exit", lambda pid, **kwargs: True)

    result = backend_control.stop_backend(port=8000)

    assert result["stopped"] is True
    assert stopped == [1001]
    assert killed == [1002]


def test_stop_backend_cleans_up_non_socket_declarants(monkeypatch) -> None:
    """After stopping the socket owner, also SIGTERM non-socket declarants."""
    import signal as signal_module

    socket_owner = {"pid": 1001, "ports": [8000], "declared_port": 8000}
    declarant = {"pid": 1002, "ports": [], "declared_port": 8000}

    monkeypatch.setattr(backend_control, "read_backend_state", lambda start=None: None)
    monkeypatch.setattr(backend_control, "find_arch_backend_instances", lambda: [socket_owner, declarant])

    stopped_via_stop_pid: list[int] = []
    killed: list[tuple[int, int]] = []
    alive: set[int] = {1002}

    def fake_stop_pid(pid, *, cwd=None, timeout_s=5.0, port=None):
        stopped_via_stop_pid.append(pid)
        return {"stopped": True, "pid": pid, "port": port}

    def fake_kill(pid: int, sig: int) -> None:
        killed.append((pid, sig))
        alive.discard(pid)

    monkeypatch.setattr(backend_control, "_stop_pid", fake_stop_pid)
    monkeypatch.setattr(backend_control.os, "kill", fake_kill)
    monkeypatch.setattr(backend_control, "_process_exists", lambda pid: pid in alive)

    result = backend_control.stop_backend(port=8000)

    assert result["stopped"] is True
    assert stopped_via_stop_pid == [1001]
    sigtermed = [pid for pid, sig in killed if sig == signal_module.SIGTERM]
    assert 1002 in sigtermed


def test_stop_backend_tolerates_unkillable_declarant(monkeypatch) -> None:
    """A declarant we lack permission to signal must not abort an otherwise-successful stop."""
    socket_owner = {"pid": 1001, "ports": [8000], "declared_port": 8000}
    declarant = {"pid": 1002, "ports": [], "declared_port": 8000}

    monkeypatch.setattr(backend_control, "read_backend_state", lambda start=None: None)
    monkeypatch.setattr(backend_control, "find_arch_backend_instances", lambda: [socket_owner, declarant])
    monkeypatch.setattr(
        backend_control, "_stop_pid", lambda pid, **kwargs: {"stopped": True, "pid": pid, "port": kwargs.get("port")}
    )

    def raise_eperm(pid: int, sig: int) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(backend_control.os, "kill", raise_eperm)

    result = backend_control.stop_backend(port=8000)

    assert result["stopped"] is True


def test_restart_daemon_cleans_up_leftover_unhealthy_process(monkeypatch, tmp_path: Path) -> None:
    """--restart --daemon auto-stops a surviving declarant instead of aborting."""
    stop_calls: list[int | None] = []

    def fake_stop_backend(*, port=None, cwd=None, timeout_s=5.0):
        stop_calls.append(port)
        return {"stopped": True, "pid": 1001, "port": port}

    monkeypatch.setattr(backend_control, "stop_backend", fake_stop_backend)
    monkeypatch.setattr(arch_backend, "resolve_backend_port", lambda start=None, explicit_port=None: 8000)
    monkeypatch.setattr(arch_backend, "read_backend_state", lambda: None)
    monkeypatch.setattr(
        backend_control,
        "backend_status",
        lambda port=None, cwd=None: {
            "running": False,
            "reason": "unhealthy_backend",
            "pid": 1002,
            "port": 8000,
        },
    )
    monkeypatch.setattr(arch_backend, "backend_log_path", lambda start=None: tmp_path / "backend.log")

    started_pids: list[int] = []

    def fake_start_daemon(*, argv, log_path):
        started_pids.append(9999)
        return 9999

    monkeypatch.setattr(arch_backend, "_start_daemon", fake_start_daemon)
    monkeypatch.setattr(arch_backend, "probe_backend", lambda port, timeout_s=1.0: True)

    arch_backend.main(["--restart", "--daemon"])

    assert started_pids == [9999], "daemon should have been started after leftover cleanup"
    assert len(stop_calls) >= 2, "stop should have been called for restart and for leftover cleanup"


def test_stop_backend_stops_all_when_multiple_own_sockets(monkeypatch) -> None:
    """When multiple processes own listening sockets on the same port, stop all."""
    instance_a = {"pid": 1001, "ports": [8000], "declared_port": 8000}
    instance_b = {"pid": 1002, "ports": [8000], "declared_port": 8000}

    monkeypatch.setattr(backend_control, "read_backend_state", lambda start=None: None)
    monkeypatch.setattr(backend_control, "find_arch_backend_instances", lambda: [instance_a, instance_b])

    stopped: list[int] = []

    def fake_stop_pid(pid, *, cwd=None, timeout_s=5.0, port=None):
        stopped.append(pid)
        return {"stopped": True, "pid": pid, "port": port}

    monkeypatch.setattr(backend_control, "_stop_pid", fake_stop_pid)

    result = backend_control.stop_backend(port=8000)

    assert result["stopped"] is True
    assert set(stopped) == {1001, 1002}
    assert set(result["pids"]) == {1001, 1002}


def test_daemon_argv_strips_restart_and_stop_flags() -> None:
    result = arch_backend._daemon_argv(["--restart", "--repo-root", "/some/path", "--daemon", "--port", "8123"])
    assert "--restart" not in result
    assert "--stop" not in result
    assert "--daemon" not in result
    assert "--port" in result
    assert "--repo-root" in result


def test_stop_outputs_all_pids_when_multiple_stopped(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        backend_control,
        "stop_backend",
        lambda port=None, cwd=None, timeout_s=5.0: {
            "stopped": True,
            "pid": 657,
            "pids": [657, 658],
            "port": 8000,
        },
    )
    monkeypatch.setattr(arch_backend, "resolve_backend_port", lambda start=None, explicit_port=None: 8000)

    arch_backend.main(["--stop"])

    out = capsys.readouterr().out
    assert "657" in out
    assert "658" in out


def test_unified_backend_routes_split_mcp_paths() -> None:
    app = _build_app()
    actual_paths = {getattr(route, "path", None) for route in app.routes}

    assert "/mcp/read" in actual_paths
    assert "/mcp/read/" in actual_paths
    assert "/mcp/write" in actual_paths
    assert "/mcp/write/" in actual_paths


def test_unified_backend_routes_assurance_mcp_paths() -> None:
    """All four MCP endpoints are mounted: arch read/write + assurance read/write."""
    app = _build_app()
    actual_paths = {getattr(route, "path", None) for route in app.routes}

    assert "/mcp/assurance-read" in actual_paths
    assert "/mcp/assurance-read/" in actual_paths
    assert "/mcp/assurance-write" in actual_paths
    assert "/mcp/assurance-write/" in actual_paths


def test_unified_backend_installs_module_registry_on_app_state() -> None:
    app = _build_app()

    registry = module_registry_from_app(app)

    assert isinstance(registry, ModuleRegistry)
    assert registry.find_ontology("archimate-4-0") is not None
    assert registry.find_diagram_type("archimate-business") is not None
    assert registry.find_diagram_type("archimate-layered") is not None


def test_module_registry_dependency_reads_installed_app_state() -> None:
    app = _build_app()

    class _Request:
        def __init__(self, app_obj) -> None:
            self.app = app_obj

    registry = module_registry_dependency(_Request(app))

    assert registry is module_registry_from_app(app)


def test_stop_backend_returns_not_running_when_no_state(monkeypatch) -> None:
    monkeypatch.setattr(backend_control, "read_backend_state", lambda start=None: None)
    monkeypatch.setattr(backend_control, "find_arch_backend_instances", lambda: [])

    result = backend_control.stop_backend()

    assert result == {"stopped": False, "reason": "not_running"}


def test_backend_status_reports_not_running_when_no_state(monkeypatch) -> None:
    monkeypatch.setattr(backend_control, "read_backend_state", lambda start=None: None)
    monkeypatch.setattr(backend_control, "find_arch_backend_instance_for_port", lambda port: None)
    monkeypatch.setattr(backend_control, "probe_backend", lambda port, timeout_s=1.0: False)
    monkeypatch.setattr(backend_control, "port_in_use", lambda host="127.0.0.1", port=8000: False)

    result = backend_control.backend_status()

    assert result == {"running": False, "reason": "not_running"}


def test_find_arch_backend_instances_excludes_current_status_process(monkeypatch, tmp_path: Path) -> None:
    proc_root = tmp_path / "proc"
    current = proc_root / "123"
    other = proc_root / "456"
    current.mkdir(parents=True)
    other.mkdir(parents=True)
    (current / "cmdline").write_bytes(b"arch-backend\x00--status\x00")
    (current / "stat").write_text("123 (arch-backend) R 0 0 0\n", encoding="utf-8")
    (other / "cmdline").write_bytes(b"arch-backend\x00--port\x008123\x00")
    (other / "stat").write_text("456 (arch-backend) S 0 0 0\n", encoding="utf-8")

    monkeypatch.setattr(backend_process, "_PROC_DIR", proc_root)
    monkeypatch.setattr(backend_process, "_list_listening_socket_inodes", lambda: {})
    monkeypatch.setattr(backend_process.os, "getpid", lambda: 123)

    result = backend_process.find_arch_backend_instances()

    assert [instance["pid"] for instance in result] == [456]


def test_backend_status_reports_unmanaged_backend(monkeypatch) -> None:
    monkeypatch.setattr(backend_control, "read_backend_state", lambda start=None: None)
    monkeypatch.setattr(backend_control, "find_arch_backend_instance_for_port", lambda port: None)
    monkeypatch.setattr(backend_control, "probe_backend", lambda port, timeout_s=1.0: True)

    result = backend_control.backend_status(port=8000)

    assert result == {"running": False, "reason": "unmanaged_backend", "port": 8000}


def test_backend_status_reports_port_in_use(monkeypatch) -> None:
    monkeypatch.setattr(backend_control, "read_backend_state", lambda start=None: None)
    monkeypatch.setattr(backend_control, "find_arch_backend_instance_for_port", lambda port: None)
    monkeypatch.setattr(backend_control, "probe_backend", lambda port, timeout_s=1.0: False)
    monkeypatch.setattr(backend_control, "port_in_use", lambda host="127.0.0.1", port=8000: True)

    result = backend_control.backend_status(port=8000)

    assert result == {"running": False, "reason": "port_in_use", "port": 8000}


def test_backend_status_reports_untracked_arch_backend_as_running(monkeypatch) -> None:
    monkeypatch.setattr(backend_control, "read_backend_state", lambda start=None: None)
    monkeypatch.setattr(
        backend_control,
        "find_arch_backend_instance_for_port",
        lambda port: {
            "pid": 654,
            "ports": [port],
            "declared_port": port,
            "process_state": "S",
            "stdin": "/dev/null",
            "stdout": "/tmp/backend.log",
            "stderr": "/tmp/backend.log",
        },
    )
    monkeypatch.setattr(backend_control, "backend_log_path", lambda start=None: Path("/tmp/backend.log"))
    monkeypatch.setattr(backend_control, "probe_backend", lambda port, timeout_s=1.0: True)

    result = backend_control.backend_status(port=8000)

    assert result == {
        "running": True,
        "reason": "ok_untracked",
        "pid": 654,
        "port": 8000,
        "process_state": "S",
        "stdin": "/dev/null",
        "stdout": "/tmp/backend.log",
        "stderr": "/tmp/backend.log",
        "log_path": "/tmp/backend.log",
    }


def test_backend_status_reports_stopped_arch_backend(monkeypatch) -> None:
    monkeypatch.setattr(backend_control, "read_backend_state", lambda start=None: None)
    monkeypatch.setattr(
        backend_control,
        "find_arch_backend_instance_for_port",
        lambda port: {
            "pid": 654,
            "ports": [port],
            "declared_port": port,
            "process_state": "T",
            "stdin": "/dev/pts/8",
            "stdout": "/tmp/backend.log",
            "stderr": "/tmp/backend.log",
        },
    )
    monkeypatch.setattr(backend_control, "backend_log_path", lambda start=None: Path("/tmp/backend.log"))

    result = backend_control.backend_status(port=8000)

    assert result == {
        "running": False,
        "reason": "stopped_backend",
        "pid": 654,
        "port": 8000,
        "process_state": "T",
        "stdin": "/dev/pts/8",
        "stdout": "/tmp/backend.log",
        "stderr": "/tmp/backend.log",
        "log_path": "/tmp/backend.log",
    }


def test_backend_status_reports_unhealthy_arch_backend(monkeypatch) -> None:
    monkeypatch.setattr(backend_control, "read_backend_state", lambda start=None: None)
    monkeypatch.setattr(
        backend_control,
        "find_arch_backend_instance_for_port",
        lambda port: {
            "pid": 654,
            "ports": [port],
            "declared_port": port,
            "process_state": "S",
            "stdin": "/dev/null",
            "stdout": "/tmp/backend.log",
            "stderr": "/tmp/backend.log",
        },
    )
    monkeypatch.setattr(backend_control, "backend_log_path", lambda start=None: Path("/tmp/backend.log"))
    monkeypatch.setattr(backend_control, "probe_backend", lambda port, timeout_s=1.0: False)

    result = backend_control.backend_status(port=8000)

    assert result == {
        "running": False,
        "reason": "unhealthy_backend",
        "pid": 654,
        "port": 8000,
        "process_state": "S",
        "stdin": "/dev/null",
        "stdout": "/tmp/backend.log",
        "stderr": "/tmp/backend.log",
        "log_path": "/tmp/backend.log",
    }


def test_port_in_use_returns_false_when_socket_unavailable(monkeypatch) -> None:
    class _SocketModule:
        AF_INET = object()
        SOCK_STREAM = object()

        @staticmethod
        def socket(*args, **kwargs):
            raise PermissionError("sandbox")

    monkeypatch.setattr(backend_probe, "socket", _SocketModule)

    assert backend_probe.port_in_use(port=8000) is False


def test_backend_status_removes_stale_pid(monkeypatch) -> None:
    removed: list[object] = []

    monkeypatch.setattr(backend_control, "read_backend_state", lambda start=None: {"pid": 123, "port": 8000})
    monkeypatch.setattr(backend_control, "_process_exists", lambda pid: False)
    monkeypatch.setattr(backend_control, "remove_backend_state", lambda start=None: removed.append(start))

    result = backend_control.backend_status(port=8000)

    assert result == {"running": False, "reason": "stale_pid", "pid": 123, "port": 8000}
    assert removed == [None]


def test_backend_status_reports_tracked_stopped_backend_without_probe(monkeypatch) -> None:
    probed: list[int] = []

    monkeypatch.setattr(backend_control, "read_backend_state", lambda start=None: {"pid": 123, "port": 8000})
    monkeypatch.setattr(backend_control, "_process_exists", lambda pid: True)
    monkeypatch.setattr(backend_control, "_read_process_state", lambda pid: "T")
    monkeypatch.setattr(
        backend_control,
        "backend_process_diagnostics",
        lambda pid: {"stdin": "/dev/pts/8", "stdout": "/tmp/backend.log", "stderr": "/tmp/backend.log"},
    )
    monkeypatch.setattr(backend_control, "backend_log_path", lambda start=None: Path("/tmp/backend.log"))
    monkeypatch.setattr(backend_control, "probe_backend", lambda port, timeout_s=1.0: probed.append(port) or True)

    result = backend_control.backend_status(port=8000)

    assert result == {
        "running": False,
        "reason": "stopped_backend",
        "pid": 123,
        "port": 8000,
        "process_state": "T",
        "stdin": "/dev/pts/8",
        "stdout": "/tmp/backend.log",
        "stderr": "/tmp/backend.log",
        "log_path": "/tmp/backend.log",
    }
    assert probed == []


def test_stop_backend_stops_matching_instance_on_configured_port(monkeypatch) -> None:
    monkeypatch.setattr(backend_control, "read_backend_state", lambda start=None: None)
    monkeypatch.setattr(
        backend_control,
        "find_arch_backend_instances",
        lambda: [{"pid": 456, "ports": [8123], "declared_port": 8123}],
    )
    monkeypatch.setattr(
        backend_control,
        "_stop_pid",
        lambda pid, cwd=None, timeout_s=5.0, port=None: {"stopped": True, "pid": pid, "port": port},
    )

    result = backend_control.stop_backend(port=8123)

    assert result == {"stopped": True, "pid": 456, "port": 8123}


def test_stop_backend_returns_single_other_port_when_only_other_instance_exists(monkeypatch) -> None:
    monkeypatch.setattr(backend_control, "read_backend_state", lambda start=None: None)
    monkeypatch.setattr(
        backend_control,
        "find_arch_backend_instances",
        lambda: [{"pid": 456, "ports": [8124], "declared_port": 8124}],
    )

    result = backend_control.stop_backend(port=8123)

    assert result == {
        "stopped": False,
        "reason": "single_other_port",
        "pid": 456,
        "port": 8124,
        "expected_port": 8123,
    }


def test_stop_backend_removes_stale_pid(monkeypatch) -> None:
    removed: list[object] = []

    monkeypatch.setattr(backend_control, "read_backend_state", lambda start=None: {"pid": 123, "port": 8000})
    monkeypatch.setattr(backend_control, "remove_backend_state", lambda start=None: removed.append(start))

    def fake_kill(pid: int, sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(backend_control.os, "kill", fake_kill)

    result = backend_control.stop_backend()

    assert result == {"stopped": False, "reason": "stale_pid", "pid": 123}
    assert removed == [None]


def test_stop_pid_continues_stopped_process_before_terminating(monkeypatch) -> None:
    signals: list[int] = []
    alive = iter([True, False])

    monkeypatch.setattr(backend_control, "read_backend_state", lambda start=None: None)
    monkeypatch.setattr(backend_control, "_read_process_state", lambda pid: "T")
    monkeypatch.setattr(backend_control, "_process_exists", lambda pid: next(alive))

    def fake_kill(pid: int, sig: int) -> None:
        signals.append(sig)

    monkeypatch.setattr(backend_control.os, "kill", fake_kill)

    result = backend_control._stop_pid(123, port=8000)

    assert result == {"stopped": True, "pid": 123, "port": 8000}
    import signal as signal_module

    assert signals[:2] == [signal_module.SIGCONT, signal_module.SIGTERM]


def test_stop_pid_escalates_to_sigkill_after_timeout(monkeypatch) -> None:
    signals: list[int] = []
    kill_phase = {"sigkill_sent": False, "checks_after_sigkill": 0}

    monkeypatch.setattr(backend_control, "read_backend_state", lambda start=None: None)
    monkeypatch.setattr(backend_control, "_read_process_state", lambda pid: "S")
    monkeypatch.setattr(backend_control.time, "sleep", lambda s: None)

    now = {"value": 0.0}

    def fake_monotonic() -> float:
        now["value"] += 0.2
        return now["value"]

    monkeypatch.setattr(backend_control.time, "monotonic", fake_monotonic)

    def fake_process_exists(pid: int) -> bool:
        if not kill_phase["sigkill_sent"]:
            return True
        kill_phase["checks_after_sigkill"] += 1
        return kill_phase["checks_after_sigkill"] < 2

    monkeypatch.setattr(backend_control, "_process_exists", fake_process_exists)

    import signal as signal_module

    def fake_kill(pid: int, sig: int) -> None:
        signals.append(sig)
        if sig == signal_module.SIGKILL:
            kill_phase["sigkill_sent"] = True

    monkeypatch.setattr(backend_control.os, "kill", fake_kill)

    result = backend_control._stop_pid(123, port=8000, timeout_s=1.0)

    assert result == {"stopped": True, "pid": 123, "port": 8000}
    assert signals == [signal_module.SIGTERM, signal_module.SIGKILL]


def test_arch_backend_stop_prints_not_running(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        backend_control,
        "stop_backend",
        lambda **kwargs: {"stopped": False, "reason": "not_running"},
    )

    arch_backend.main(["--stop"])

    out = capsys.readouterr().out
    assert "not running" in out


def test_arch_backend_status_prints_running(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        backend_control,
        "backend_status",
        lambda port=8000: {"running": True, "reason": "ok", "pid": 321, "port": port},
    )

    arch_backend.main(["--status"])

    out = capsys.readouterr().out
    assert "running on port 8000" in out


def test_arch_backend_status_prints_stopped_backend(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        backend_control,
        "backend_status",
        lambda port=8000: {
            "running": False,
            "reason": "stopped_backend",
            "pid": 321,
            "port": port,
            "process_state": "T",
            "stdin": "/dev/pts/8",
            "stdout": "/tmp/backend.log",
            "stderr": "/tmp/backend.log",
            "log_path": "/tmp/backend.log",
        },
    )

    arch_backend.main(["--status"])

    out = capsys.readouterr().out
    assert "backend process pid 321 is stopped on port 8000" in out
    assert "process state: T" in out
    assert "stdin=/dev/pts/8" in out
    assert "log: /tmp/backend.log" in out


def test_arch_backend_start_returns_when_untracked_backend_already_running(monkeypatch, capsys) -> None:
    monkeypatch.setattr(arch_backend, "read_backend_state", lambda: None)
    monkeypatch.setattr(
        backend_control,
        "backend_status",
        lambda port=8000: {"running": True, "reason": "ok_untracked", "pid": 777, "port": port},
    )

    arch_backend.main([])

    out = capsys.readouterr().out
    assert "backend already running on port 8000 (pid 777)" in out


def test_arch_backend_start_refuses_unhealthy_backend(monkeypatch) -> None:
    monkeypatch.setattr(arch_backend, "read_backend_state", lambda: None)
    monkeypatch.setattr(
        backend_control,
        "backend_status",
        lambda port=8000: {"running": False, "reason": "stopped_backend", "pid": 777, "port": port},
    )

    try:
        arch_backend.main([])
    except SystemExit as exc:
        assert "is on port 8000 but is not healthy" in str(exc)
    else:
        raise AssertionError("expected SystemExit")


def test_redirect_stdio_to_backend_log_detaches_stdin(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / ".arch" / "backend.log"
    opened: list[tuple[object, int, object | None]] = []
    duped: list[tuple[int, int]] = []
    closed: list[int] = []

    def fake_open(path: object, flags: int, mode: object | None = None) -> int:
        opened.append((path, flags, mode))
        return 10 if Path(path) == log_path else 11

    monkeypatch.setattr(arch_backend, "backend_log_path", lambda start=None: log_path)
    monkeypatch.setattr(arch_backend.os, "open", fake_open)
    monkeypatch.setattr(arch_backend.os, "dup2", lambda src, dst: duped.append((src, dst)))
    monkeypatch.setattr(arch_backend.os, "close", lambda fd: closed.append(fd))

    class _FakeStream:
        def __init__(self, fd: int) -> None:
            self._fd = fd

        def fileno(self) -> int:
            return self._fd

    monkeypatch.setattr(arch_backend.sys, "stdin", _FakeStream(0))
    monkeypatch.setattr(arch_backend.sys, "stdout", _FakeStream(1))
    monkeypatch.setattr(arch_backend.sys, "stderr", _FakeStream(2))

    result = arch_backend._redirect_stdio_to_backend_log(start=tmp_path)

    assert result == log_path
    assert opened == [
        (log_path, arch_backend.os.O_WRONLY | arch_backend.os.O_CREAT | arch_backend.os.O_APPEND, 0o644),
        (arch_backend.os.devnull, arch_backend.os.O_RDONLY, None),
    ]
    assert duped == [(11, 0), (10, 1), (10, 2)]
    assert closed == [10, 11]


def test_start_daemon_detaches_stdin_and_session(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    class _Proc:
        pid = 4321

    def fake_popen(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return _Proc()

    monkeypatch.setattr(arch_backend.sys, "argv", ["arch-backend", "--daemon", "--port", "8123"])
    monkeypatch.setattr(arch_backend.subprocess, "Popen", fake_popen)

    log_path = tmp_path / ".arch" / "backend.log"
    pid = arch_backend._start_daemon(argv=None, log_path=log_path)

    assert pid == 4321
    assert calls
    assert calls[0]["command"] == ["arch-backend", "--port", "8123"]
    assert calls[0]["stdin"] is arch_backend.subprocess.DEVNULL
    assert calls[0]["stderr"] is arch_backend.subprocess.STDOUT
    assert calls[0]["start_new_session"] is True
    assert calls[0]["cwd"] == str(Path.cwd())


def test_arch_backend_daemon_waits_for_probe(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(arch_backend, "read_backend_state", lambda: None)
    monkeypatch.setattr(
        backend_control,
        "backend_status",
        lambda port=8000: {"running": False, "reason": "not_running", "port": port},
    )
    monkeypatch.setattr(arch_backend, "backend_log_path", lambda start=None: tmp_path / ".arch" / "backend.log")
    monkeypatch.setattr(arch_backend, "_start_daemon", lambda argv, log_path: 4321)
    monkeypatch.setattr(arch_backend, "probe_backend", lambda port: True)

    arch_backend.main(["--daemon", "--port", "8123"])

    out = capsys.readouterr().out
    assert "backend started on port 8123 (pid 4321)" in out


def test_arch_backend_redirects_stdio_when_background_tty_job(monkeypatch, tmp_path: Path) -> None:
    redirected: list[Path | None] = []

    monkeypatch.setattr(arch_backend, "_is_background_tty_job", lambda: True)
    monkeypatch.setattr(
        arch_backend,
        "_redirect_stdio_to_backend_log",
        lambda start=None: redirected.append(start) or tmp_path / ".arch" / "backend.log",
    )
    monkeypatch.setattr(
        backend_control, "backend_status",
        lambda port=8000: {"running": False, "reason": "not_running"},
    )
    monkeypatch.setattr(arch_backend, "read_backend_state", lambda: None)
    monkeypatch.setattr(
        arch_backend.gui_server,
        "resolve_server_roots",
        lambda repo_root, enterprise_root: (tmp_path, None),
    )
    monkeypatch.setattr(arch_backend, "_build_app", lambda credentials=None: object())
    monkeypatch.setattr(arch_backend, "_serve", lambda app, **kwargs: None)

    arch_backend.main(["--repo-root", str(tmp_path)])

    assert redirected == [Path.cwd()]


def test_arch_backend_status_prints_unmanaged_backend(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        backend_control,
        "backend_status",
        lambda port=8000: {"running": False, "reason": "unmanaged_backend", "port": port},
    )

    arch_backend.main(["--status"])

    out = capsys.readouterr().out
    assert "not managed by this workspace" in out


def test_arch_backend_stop_prompts_for_single_other_port_and_stops(monkeypatch, capsys) -> None:
    calls: list[int] = []

    def fake_stop_backend(*, port=None, cwd=None, timeout_s=5.0):
        calls.append(int(port))
        if len(calls) == 1:
            return {"stopped": False, "reason": "single_other_port", "pid": 321, "port": 8124, "expected_port": 8123}
        return {"stopped": True, "pid": 321, "port": 8124}

    monkeypatch.setattr(backend_control, "stop_backend", fake_stop_backend)
    monkeypatch.setattr(_lifecycle_cli, "_confirm_stop_other_instance", lambda **kwargs: True)

    arch_backend.main(["--stop", "--port", "8123"])

    out = capsys.readouterr().out
    assert "stopped backend pid 321" in out
    assert calls == [8123, 8124]


def test_arch_backend_status_prints_removed_stale_backend(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        backend_control,
        "backend_status",
        lambda port=8000: {"running": False, "reason": "stale_pid", "pid": 321, "port": port},
    )

    arch_backend.main(["--status"])

    out = capsys.readouterr().out
    assert "removed stale backend pid 321" in out


def test_arch_backend_restart_stops_then_returns_to_startup(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.setattr(arch_backend, "backend_min_log_level", lambda: "WARNING")
    monkeypatch.setattr(
        backend_control,
        "stop_backend",
        lambda **kwargs: {"stopped": True, "pid": 123, "port": 8000},
    )
    monkeypatch.setattr(arch_backend, "read_backend_state", lambda: None)
    monkeypatch.setattr(
        arch_backend.gui_server,
        "resolve_server_roots",
        lambda repo_root, enterprise_root: (tmp_path, None),
    )
    monkeypatch.setattr(
        backend_control,
        "backend_status",
        lambda port=8000: {"running": False, "reason": "not_running"},
    )
    monkeypatch.setattr(arch_backend, "_build_app", lambda credentials=None: object())
    ran: dict[str, object] = {}

    def fake_serve(app, **kwargs: object) -> None:
        ran.update(kwargs)

    # `_serve` is the seam, not `uvicorn.run`: the launch now builds a Config and runs an
    # `_AnnouncingServer`, so a stub on `uvicorn.run` would miss and this test would start a real
    # server and hang. What `_serve` passes uvicorn is asserted in `test_graceful_shutdown`.
    monkeypatch.setattr(arch_backend, "_serve", fake_serve)

    arch_backend.main(["--restart", "--repo-root", str(tmp_path)])

    out = capsys.readouterr().out
    assert "stopped backend pid 123" in out
    assert ran == {"host": "127.0.0.1", "port": 8000}


def test_arch_backend_build_failure_does_not_write_backend_state(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(arch_backend, "read_backend_state", lambda: None)
    monkeypatch.setattr(
        backend_control,
        "backend_status",
        lambda port=8000: {"running": False, "reason": "not_running"},
    )
    monkeypatch.setattr(
        arch_backend.gui_server,
        "resolve_server_roots",
        lambda repo_root, enterprise_root: (tmp_path, None),
    )
    wrote: list[object] = []
    monkeypatch.setattr(arch_backend, "write_backend_state", lambda port: wrote.append(port))
    monkeypatch.setattr(
        arch_backend,
        "_build_app",
        lambda credentials=None: (_ for _ in ()).throw(ModuleNotFoundError("fastapi")),
    )

    try:
        arch_backend.main(["--repo-root", str(tmp_path)])
    except ModuleNotFoundError as exc:
        assert "fastapi" in str(exc)
    else:
        raise AssertionError("expected ModuleNotFoundError")

    assert wrote == []


def test_arch_backend_refuses_to_start_when_port_used_by_other_process(monkeypatch) -> None:
    monkeypatch.setattr(arch_backend, "read_backend_state", lambda: None)
    monkeypatch.setattr(
        backend_control,
        "backend_status",
        lambda port=8000: {"running": False, "reason": "port_in_use", "port": port},
    )

    try:
        arch_backend.main([])
    except SystemExit as exc:
        assert "already in use" in str(exc)
    else:
        raise AssertionError("expected SystemExit")


# --- W3/W4: artifact_write_cli requires a running backend ---

from src.infrastructure.write import artifact_write_cli  # noqa: E402


def test_write_cli_errors_when_backend_absent(monkeypatch, tmp_path: Path, capsys) -> None:
    """artifact_write_cli exits with error when no backend state exists."""
    monkeypatch.setattr(artifact_write_cli, "read_backend_state", lambda path: None)

    result = artifact_write_cli.main(["--repo-root", str(tmp_path), "delete-entity", "ENT@123.abc"])

    assert result == 1
    err = capsys.readouterr().err
    assert "arch-backend" in err


def test_write_cli_errors_when_backend_unhealthy(monkeypatch, tmp_path: Path, capsys) -> None:
    """artifact_write_cli exits with error when backend state exists but probe fails."""
    monkeypatch.setattr(artifact_write_cli, "read_backend_state", lambda path: {"port": 8123})
    monkeypatch.setattr(artifact_write_cli, "probe_backend", lambda port: False)

    result = artifact_write_cli.main(["--repo-root", str(tmp_path), "delete-entity", "ENT@123.abc"])

    assert result == 1
    err = capsys.readouterr().err
    assert "arch-backend" in err


def test_write_cli_routes_delete_entity_through_backend(monkeypatch, tmp_path: Path) -> None:
    """delete-entity targets the canonical entity detail route when a backend is available."""
    import json as json_mod  # noqa: PLC0415

    monkeypatch.setattr(artifact_write_cli, "read_backend_state", lambda path: {"port": 8123})
    monkeypatch.setattr(artifact_write_cli, "probe_backend", lambda port: True)

    requests_captured: list[dict[str, object]] = []

    class _FakeResp:
        def read(self): return json_mod.dumps({"artifact_id": "ENT@123.abc", "path": "x.yaml", "warnings": []}).encode()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake_urlopen(req, timeout=10.0):
        requests_captured.append({"url": req.full_url, "method": req.get_method(), "body": req.data})
        return _FakeResp()

    monkeypatch.setattr(artifact_write_cli, "urlopen", fake_urlopen)

    result = artifact_write_cli.main(["--repo-root", str(tmp_path), "delete-entity", "ENT@123.abc"])

    assert result == 0
    # Identity is in the path and the dry-run flag in the query: a DELETE has no body for either.
    assert requests_captured[0]["method"] == "DELETE"
    assert "/api/entities/ENT%40123.abc" in requests_captured[0]["url"]
    assert requests_captured[0]["body"] is None
