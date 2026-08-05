"""Several workspaces on one machine: each talks to its own backend, or to none.

The defect these cover was observed, not imagined: two checkouts of this project, each shipping
`backend.port: 8000`, and an MCP bridge in the second one that proxied a whole session's tool calls
into the first one's model. Nothing failed — both backends answered every request correctly, about
different repositories.

Two levels here. The lifecycle tests drive `ensure_backend_running`, `backend_status` and
`stop_backend` against injected observations, so every process state is reachable. The socket tests
at the end use real HTTP servers on real ports, with no probe stubbed at all, because the mechanism
being tested *is* the probing.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

from src.domain.deployment.backend_endpoint import (
    AttachToBackend,
    BackendIdentity,
    EndpointObservation,
    PortPreference,
    RefuseEndpoint,
    StartBackendOn,
    WorkspaceClaim,
    derived_port,
)
from src.infrastructure.backend import backend_control, backend_endpoint, backend_launch, backend_probe
from src.infrastructure.mcp import arch_mcp_stdio

DEFAULT_PREFERENCE = PortPreference(port=8000, authority="settings_document")


# ── Workspace fixtures ────────────────────────────────────────────────────────


def _workspace(root: Path, *, name: str, with_init_state: bool = True) -> Path:
    """A workspace directory declaring its own engagement and enterprise repositories."""
    workspace = root / name
    engagement = workspace / "engagement"
    enterprise = workspace / "enterprise"
    for path in (workspace, engagement, enterprise):
        path.mkdir(parents=True, exist_ok=True)
    (workspace / "arch-workspace.yaml").write_text(
        yaml.safe_dump(
            {
                "engagement": {"local": "engagement"},
                "enterprise": {"local": "enterprise"},
            }
        ),
        encoding="utf-8",
    )
    if with_init_state:
        (workspace / ".arch").mkdir(exist_ok=True)
        (workspace / ".arch" / "init-state.yaml").write_text(
            yaml.safe_dump(
                {
                    "workspace_root": str(workspace),
                    "engagement_root": str(engagement),
                    "enterprise_root": str(enterprise),
                    "initialized_at": "2026-08-04T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
    return workspace


def _claim_of(workspace: Path) -> WorkspaceClaim:
    return WorkspaceClaim(
        engagement_root=(workspace / "engagement").resolve(),
        enterprise_root=(workspace / "enterprise").resolve(),
    )


def _identity_of(workspace: Path) -> BackendIdentity:
    claim = _claim_of(workspace)
    return BackendIdentity(
        repo_roots=(str(claim.engagement_root), str(claim.enterprise_root)),
        software_version="9.9.9",
    )


def _record_backend(workspace: Path, *, port: int, pid: int) -> None:
    (workspace / ".arch").mkdir(exist_ok=True)
    (workspace / ".arch" / "backend.pid").write_text(json.dumps({"pid": pid, "port": port}), encoding="utf-8")


def _install_machine(monkeypatch, backends: dict[int, Path], *, silent_ports: tuple[int, ...] = ()) -> list[int]:
    """Describe the machine: which port each workspace's backend answers on. Records probed ports."""
    probed: list[int] = []

    def observe(port: int, *, timeout_s: float = 1.0) -> EndpointObservation:
        probed.append(port)
        if port in backends:
            return EndpointObservation(
                port=port, socket_taken=True, answers_probe=True, identity=_identity_of(backends[port])
            )
        if port in silent_ports:
            return EndpointObservation(port=port, socket_taken=True, answers_probe=False)
        return EndpointObservation(port=port, socket_taken=False, answers_probe=False)

    monkeypatch.setattr(backend_endpoint, "observe_endpoint", observe)
    monkeypatch.setattr(
        backend_endpoint,
        "probe_identity_on_port",
        lambda port, timeout_s=1.0: _identity_of(backends[port]) if port in backends else None,
    )
    monkeypatch.setattr(backend_control, "probe_backend", lambda port, timeout_s=1.0: port in backends)
    monkeypatch.setattr(
        backend_endpoint,
        "backend_port_preference",
        lambda start=None, explicit_port=None: DEFAULT_PREFERENCE,
    )
    monkeypatch.setattr(
        backend_control, "resolve_backend_port", lambda start=None, explicit_port=None: DEFAULT_PREFERENCE.port
    )
    return probed


def _no_spawning(monkeypatch) -> list[tuple[int, str]]:
    """Record what would have been started, and let the caller assert the port it was told to use."""
    started: list[tuple[int, str]] = []

    def fake_start(port: int, *, workspace: Path, project_dir: Path | None) -> int:
        started.append((port, str(workspace)))
        return port

    monkeypatch.setattr(backend_launch, "_start_backend", fake_start)
    monkeypatch.setattr(backend_launch, "configured_backend_url", lambda: None)
    return started


# ── ensure_backend_running ────────────────────────────────────────────────────


def test_a_workspace_reuses_its_own_backend(monkeypatch, tmp_path: Path) -> None:
    ours = _workspace(tmp_path, name="ours")
    _install_machine(monkeypatch, {8000: ours})
    started = _no_spawning(monkeypatch)

    port = backend_launch.ensure_backend_running(cwd=ours)

    assert port == 8000
    assert started == []


def test_a_workspace_never_attaches_to_a_neighbours_backend(monkeypatch, tmp_path: Path) -> None:
    ours = _workspace(tmp_path, name="ours")
    theirs = _workspace(tmp_path, name="theirs")
    _install_machine(monkeypatch, {8000: theirs})
    started = _no_spawning(monkeypatch)

    port = backend_launch.ensure_backend_running(cwd=ours)

    assert port == derived_port(_claim_of(ours).fingerprint)
    assert started == [(port, str(ours))]


def test_two_workspaces_land_on_two_different_ports(monkeypatch, tmp_path: Path) -> None:
    ours = _workspace(tmp_path, name="ours")
    theirs = _workspace(tmp_path, name="theirs")
    _install_machine(monkeypatch, {})
    _no_spawning(monkeypatch)

    first = backend_launch.ensure_backend_running(cwd=ours)
    _install_machine(monkeypatch, {first: ours})
    second = backend_launch.ensure_backend_running(cwd=theirs)

    assert first == 8000
    assert second == derived_port(_claim_of(theirs).fingerprint)
    assert second != first


def test_a_workspace_finds_its_backend_at_the_port_it_recorded(monkeypatch, tmp_path: Path) -> None:
    ours = _workspace(tmp_path, name="ours")
    theirs = _workspace(tmp_path, name="theirs")
    own_port = 8321
    _record_backend(ours, port=own_port, pid=4242)
    _install_machine(monkeypatch, {8000: theirs, own_port: ours})
    started = _no_spawning(monkeypatch)

    assert backend_launch.ensure_backend_running(cwd=ours) == own_port
    assert started == []


def test_a_record_taken_over_by_a_neighbour_is_not_attached_to(monkeypatch, tmp_path: Path) -> None:
    ours = _workspace(tmp_path, name="ours")
    theirs = _workspace(tmp_path, name="theirs")
    _record_backend(ours, port=8321, pid=4242)
    _install_machine(monkeypatch, {8321: theirs})
    started = _no_spawning(monkeypatch)

    port = backend_launch.ensure_backend_running(cwd=ours)

    assert port == 8000
    assert started == [(8000, str(ours))]


def test_without_autostart_a_neighbours_backend_is_refused_by_name(monkeypatch, tmp_path: Path) -> None:
    ours = _workspace(tmp_path, name="ours")
    theirs = _workspace(tmp_path, name="theirs")
    _install_machine(monkeypatch, {8000: theirs})
    _no_spawning(monkeypatch)

    with pytest.raises(RuntimeError) as raised:
        backend_launch.ensure_backend_running(cwd=ours, start_if_missing=False)

    assert str(_claim_of(theirs).engagement_root) in str(raised.value)


def test_a_declared_port_held_by_a_neighbour_refuses_rather_than_moving(monkeypatch, tmp_path: Path) -> None:
    ours = _workspace(tmp_path, name="ours")
    theirs = _workspace(tmp_path, name="theirs")
    _install_machine(monkeypatch, {8000: theirs})
    monkeypatch.setattr(
        backend_endpoint,
        "backend_port_preference",
        lambda start=None, explicit_port=None: PortPreference(port=8000, authority="workspace_config"),
    )
    started = _no_spawning(monkeypatch)

    with pytest.raises(RuntimeError, match="arch-workspace.yaml"):
        backend_launch.ensure_backend_running(cwd=ours)

    assert started == []


def test_an_externally_named_backend_is_used_whatever_it_serves(monkeypatch, tmp_path: Path) -> None:
    """A container publishes container paths, which never match a host workspace — naming it is the decision."""
    ours = _workspace(tmp_path, name="ours")
    theirs = _workspace(tmp_path, name="theirs")
    _install_machine(monkeypatch, {8000: theirs})
    _no_spawning(monkeypatch)
    monkeypatch.setattr(backend_launch, "configured_backend_url", lambda: "http://backend.internal:8000")
    monkeypatch.setattr(backend_launch, "probe_backend_url", lambda url, timeout_s=1.0: True)
    monkeypatch.setattr(backend_launch, "probe_backend_identity", lambda url, timeout_s=1.0: _identity_of(theirs))
    monkeypatch.setattr(backend_launch, "resolve_backend_port", lambda start=None, explicit_port=None: 8000)

    assert backend_launch.ensure_backend_running(cwd=ours) == 8000


def test_an_unreachable_external_backend_is_reported_as_such(monkeypatch, tmp_path: Path) -> None:
    ours = _workspace(tmp_path, name="ours")
    _install_machine(monkeypatch, {})
    _no_spawning(monkeypatch)
    monkeypatch.setattr(backend_launch, "configured_backend_url", lambda: "http://backend.internal:8000")
    monkeypatch.setattr(backend_launch, "probe_backend_url", lambda url, timeout_s=1.0: False)

    with pytest.raises(RuntimeError, match="not reachable"):
        backend_launch.ensure_backend_running(cwd=ours)


def test_a_started_backend_counts_only_once_it_serves_this_workspace(monkeypatch, tmp_path: Path) -> None:
    """A neighbour claiming the chosen port in the start-up window must not read as our own start."""
    ours = _workspace(tmp_path, name="ours")
    theirs = _workspace(tmp_path, name="theirs")
    monkeypatch.setattr(backend_launch, "probe_backend", lambda port, timeout_s=1.0: True)
    monkeypatch.setattr(backend_launch, "port_serves_workspace", lambda port, claim, timeout_s=1.0: False)
    monkeypatch.setattr(backend_launch, "workspace_claim", lambda start=None: _claim_of(ours))
    monkeypatch.setattr(backend_launch.time, "sleep", lambda seconds: None)
    ticks = iter([0.0, 1.0, backend_launch.STARTUP_DEADLINE_SECONDS + 1.0])
    monkeypatch.setattr(backend_launch.time, "monotonic", lambda: next(ticks))
    _install_machine(monkeypatch, {8000: theirs})

    with pytest.raises(RuntimeError, match="Timed out"):
        backend_launch._await_own_backend(8123, workspace=ours, log_path=ours / ".arch" / "backend.log")


# ── status and stop stay inside the workspace ─────────────────────────────────


def test_status_reports_a_neighbours_backend_as_foreign_not_as_running(monkeypatch, tmp_path: Path) -> None:
    ours = _workspace(tmp_path, name="ours")
    theirs = _workspace(tmp_path, name="theirs")
    _install_machine(monkeypatch, {8000: theirs})
    monkeypatch.setattr(
        backend_control,
        "find_arch_backend_instance_for_port",
        lambda port: {
            "pid": 5150, "argv": ["arch-backend"], "ports": [port], "declared_port": port,
            "process_state": "S", "stdin": None, "stdout": None, "stderr": None,
        },
    )

    status = backend_control.backend_status(cwd=ours)

    assert status["running"] is False
    assert status["reason"] == "foreign_workspace"
    assert str(_claim_of(theirs).engagement_root) in status["served_roots"]


def test_status_does_not_trust_a_record_whose_port_a_neighbour_now_holds(monkeypatch, tmp_path: Path) -> None:
    ours = _workspace(tmp_path, name="ours")
    theirs = _workspace(tmp_path, name="theirs")
    _record_backend(ours, port=8000, pid=4242)
    _install_machine(monkeypatch, {8000: theirs})
    monkeypatch.setattr(backend_control, "_process_exists", lambda pid: True)
    monkeypatch.setattr(backend_control, "_read_process_state", lambda pid: "S")
    monkeypatch.setattr(
        backend_control,
        "backend_process_diagnostics",
        lambda pid: {"process_state": "S", "ports": [8000], "stdin": None, "stdout": None, "stderr": None, "argv": []},
    )

    status = backend_control.backend_status(cwd=ours)

    assert status["running"] is False
    assert status["reason"] == "foreign_workspace"


def test_stop_never_signals_a_neighbours_backend(monkeypatch, tmp_path: Path) -> None:
    ours = _workspace(tmp_path, name="ours")
    theirs = _workspace(tmp_path, name="theirs")
    _install_machine(monkeypatch, {8000: theirs})
    signalled: list[int] = []
    monkeypatch.setattr(backend_control.os, "kill", lambda pid, sig: signalled.append(pid))
    monkeypatch.setattr(
        backend_control,
        "find_arch_backend_instances",
        lambda: [{
            "pid": 5150, "argv": ["arch-backend"], "ports": [8000], "declared_port": 8000,
            "process_state": "S", "stdin": None, "stdout": None, "stderr": None,
        }],
    )

    result = backend_control.stop_backend(cwd=ours)

    assert result == {
        "stopped": False,
        "reason": "foreign_workspace",
        "port": 8000,
        "served_roots": list(_identity_of(theirs).repo_roots),
    }
    assert signalled == []


def test_stop_does_not_offer_a_neighbours_backend_on_another_port(monkeypatch, tmp_path: Path) -> None:
    ours = _workspace(tmp_path, name="ours")
    theirs = _workspace(tmp_path, name="theirs")
    _install_machine(monkeypatch, {8321: theirs})
    signalled: list[int] = []
    monkeypatch.setattr(backend_control.os, "kill", lambda pid, sig: signalled.append(pid))
    monkeypatch.setattr(
        backend_control,
        "find_arch_backend_instances",
        lambda: [{
            "pid": 5150, "argv": ["arch-backend"], "ports": [8321], "declared_port": 8321,
            "process_state": "S", "stdin": None, "stdout": None, "stderr": None,
        }],
    )

    result = backend_control.stop_backend(cwd=ours)

    assert result["reason"] == "foreign_workspace"
    assert result["port"] == 8321
    assert signalled == []


def _instance(pid: int, port: int) -> dict[str, object]:
    return {
        "pid": pid, "argv": ["arch-backend"], "ports": [port], "declared_port": port,
        "process_state": "S", "stdin": None, "stdout": None, "stderr": None,
    }


def test_status_finds_our_own_relocated_backend_without_a_record(monkeypatch, tmp_path: Path) -> None:
    """A record can be lost; the backend it named is still ours, and still running."""
    ours = _workspace(tmp_path, name="ours")
    theirs = _workspace(tmp_path, name="theirs")
    _install_machine(monkeypatch, {8000: theirs, 8188: ours})
    monkeypatch.setattr(
        backend_control, "find_arch_backend_instances", lambda: [_instance(5150, 8000), _instance(4242, 8188)]
    )
    monkeypatch.setattr(backend_control, "find_arch_backend_instance_for_port", lambda port: _instance(5150, port))

    status = backend_control.backend_status(cwd=ours)

    assert status["running"] is True
    assert status["port"] == 8188
    assert status["pid"] == 4242


def test_stop_reaches_our_own_relocated_backend_without_a_record(monkeypatch, tmp_path: Path) -> None:
    """The neighbour on the preferred port must not hide our own backend from a stop request."""
    ours = _workspace(tmp_path, name="ours")
    theirs = _workspace(tmp_path, name="theirs")
    _install_machine(monkeypatch, {8000: theirs, 8188: ours})
    monkeypatch.setattr(
        backend_control, "find_arch_backend_instances", lambda: [_instance(5150, 8000), _instance(4242, 8188)]
    )
    signalled: list[int] = []
    monkeypatch.setattr(backend_control.os, "kill", lambda pid, sig: signalled.append(pid))
    monkeypatch.setattr(backend_control, "_process_exists", lambda pid: False)

    result = backend_control.stop_backend(cwd=ours)

    assert result["stopped"] is True
    assert result["port"] == 8188
    assert signalled == [4242], "only this workspace's backend may be signalled"


def test_a_recorded_backend_is_stopped_even_when_the_preferred_port_moved(monkeypatch, tmp_path: Path) -> None:
    ours = _workspace(tmp_path, name="ours")
    _record_backend(ours, port=8188, pid=4242)
    _install_machine(monkeypatch, {8188: ours})
    signalled: list[int] = []
    monkeypatch.setattr(backend_control.os, "kill", lambda pid, sig: signalled.append(pid))
    monkeypatch.setattr(backend_control, "_process_exists", lambda pid: False)

    result = backend_control.stop_backend(cwd=ours)

    assert result == {"stopped": True, "pid": 4242, "port": 8188}
    assert signalled == [4242]


def test_a_port_named_on_the_command_line_overrides_the_record(monkeypatch, tmp_path: Path) -> None:
    """`--stop --port N` asks about N. Only that overrides where the record says our backend is."""
    ours = _workspace(tmp_path, name="ours")
    _record_backend(ours, port=8188, pid=4242)
    _install_machine(monkeypatch, {})
    monkeypatch.setattr(backend_control, "find_arch_backend_instances", lambda: [])
    monkeypatch.setattr(backend_control, "_process_exists", lambda pid: True)

    result = backend_control.stop_backend(cwd=ours, port=9999)

    assert result["stopped"] is False
    # Reported, not deleted: the record still names a live backend, on a port nobody asked about.
    assert result["reason"] == "single_other_port"
    assert result["port"] == 8188
    assert (ours / ".arch" / "backend.pid").is_file()


# ── what a workspace claims ───────────────────────────────────────────────────


def test_a_claim_comes_from_the_arch_init_state(tmp_path: Path) -> None:
    ours = _workspace(tmp_path, name="ours")

    assert backend_endpoint.workspace_claim(ours) == _claim_of(ours)


def test_a_claim_falls_back_to_the_workspace_declaration(tmp_path: Path) -> None:
    ours = _workspace(tmp_path, name="ours", with_init_state=False)

    assert backend_endpoint.workspace_claim(ours) == _claim_of(ours)


def test_environment_overrides_name_the_repositories_the_process_would_serve(
    monkeypatch, tmp_path: Path
) -> None:
    ours = _workspace(tmp_path, name="ours")
    theirs = _workspace(tmp_path, name="theirs")
    monkeypatch.setenv("ARCH_REPO_ROOT", str(theirs / "engagement"))
    monkeypatch.setenv("ARCH_ENTERPRISE_ROOT", str(theirs / "enterprise"))

    assert backend_endpoint.workspace_claim(ours) == _claim_of(theirs)


def test_an_uninitialised_directory_states_no_claim(tmp_path: Path) -> None:
    bare = tmp_path / "bare"
    bare.mkdir()

    assert backend_endpoint.workspace_claim(bare) is None


def test_a_claim_is_resolved_so_it_can_match_the_roots_a_backend_publishes(tmp_path: Path) -> None:
    """The identity endpoint publishes realpath'd roots; an unresolved claim would never match its own backend."""
    ours = _workspace(tmp_path, name="ours")
    linked = tmp_path / "linked"
    linked.symlink_to(ours)

    claim = backend_endpoint.claim_for_roots(linked / "engagement", None)

    assert claim is not None
    assert claim.engagement_root == (ours / "engagement").resolve()


def test_a_port_serving_nothing_we_can_name_never_counts_as_ours(monkeypatch, tmp_path: Path) -> None:
    ours = _workspace(tmp_path, name="ours")
    monkeypatch.setattr(backend_endpoint, "probe_identity_on_port", lambda port, timeout_s=1.0: None)

    assert backend_endpoint.port_serves_workspace(8000, _claim_of(ours)) is False
    assert backend_endpoint.port_serves_workspace(8000, None) is False


# ── the stdio bridge names the workspace it serves ────────────────────────────


def test_the_bridge_serves_the_workspace_it_was_pointed_at(monkeypatch, tmp_path: Path) -> None:
    ours = _workspace(tmp_path, name="ours")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    asked: list[Path | None] = []
    monkeypatch.setattr(arch_mcp_stdio.anyio, "run", lambda fn, url: None)
    monkeypatch.setattr(arch_mcp_stdio, "configured_backend_url", lambda: None)
    monkeypatch.setattr(
        arch_mcp_stdio,
        "ensure_backend_running",
        lambda port=None, start_if_missing=True, cwd=None, project_dir=None: (asked.append(cwd), 8123)[-1],
    )

    arch_mcp_stdio.main(["--workspace", str(ours)])

    assert asked == [ours.resolve()]


def test_the_bridge_takes_its_workspace_from_the_environment_when_no_flag_is_given(
    monkeypatch, tmp_path: Path
) -> None:
    """MCP clients that cannot set a working directory still have to be able to say which workspace."""
    ours = _workspace(tmp_path, name="ours")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(arch_mcp_stdio.ENV_WORKSPACE, str(ours))
    asked: list[Path | None] = []
    monkeypatch.setattr(arch_mcp_stdio.anyio, "run", lambda fn, url: None)
    monkeypatch.setattr(arch_mcp_stdio, "configured_backend_url", lambda: None)
    monkeypatch.setattr(
        arch_mcp_stdio,
        "ensure_backend_running",
        lambda port=None, start_if_missing=True, cwd=None, project_dir=None: (asked.append(cwd), 8123)[-1],
    )

    arch_mcp_stdio.main([])

    assert asked == [ours.resolve()]


def test_the_bridge_refuses_out_loud_rather_than_proxying_into_a_stranger(monkeypatch, tmp_path: Path) -> None:
    ours = _workspace(tmp_path, name="ours")
    theirs = _workspace(tmp_path, name="theirs")
    monkeypatch.chdir(ours)
    bridged: list[str] = []
    monkeypatch.setattr(arch_mcp_stdio.anyio, "run", lambda fn, url: bridged.append(url))
    monkeypatch.setattr(arch_mcp_stdio, "configured_backend_url", lambda: None)
    _install_machine(monkeypatch, {8000: theirs})

    def refuse(**_kwargs: object) -> int:
        raise RuntimeError(f"port 8000 is serving another workspace ({_claim_of(theirs).engagement_root})")

    monkeypatch.setattr(arch_mcp_stdio, "ensure_backend_running", refuse)

    with pytest.raises(SystemExit) as raised:
        arch_mcp_stdio.main(["--no-autostart"])

    message = str(raised.value)
    assert str(ours) in message
    assert str(_claim_of(theirs).engagement_root) in message
    assert arch_mcp_stdio.ENV_WORKSPACE in message
    assert bridged == []


# ── reading a backend's identity ──────────────────────────────────────────────


def test_an_unreachable_backend_reports_no_identity(monkeypatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise OSError("connection refused")

    monkeypatch.setattr(backend_probe, "urlopen", refuse)

    assert backend_probe.probe_backend_identity("http://127.0.0.1:1") is None


def test_an_identity_response_is_read_into_roots_and_version(monkeypatch) -> None:
    class _Response:
        status = 200

        def read(self) -> bytes:
            return json.dumps({"repo_roots": ["/a", "/b"], "software_version": "1.2.3"}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_exc: object) -> bool:
            return False

    monkeypatch.setattr(backend_probe, "urlopen", lambda *_a, **_k: _Response())

    identity = backend_probe.probe_backend_identity("http://127.0.0.1:1")

    assert identity == BackendIdentity(repo_roots=("/a", "/b"), software_version="1.2.3")


def test_a_malformed_identity_response_is_no_identity_at_all(monkeypatch) -> None:
    """Fail closed: a payload that is not an identity must never read as "serves nothing"."""

    class _Response:
        status = 200

        def read(self) -> bytes:
            return json.dumps({"repo_roots": "not-a-list"}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_exc: object) -> bool:
            return False

    monkeypatch.setattr(backend_probe, "urlopen", lambda *_a, **_k: _Response())

    assert backend_probe.probe_backend_identity("http://127.0.0.1:1") is None


# ── where a preferred port comes from ─────────────────────────────────────────


def test_a_command_line_port_is_a_statement_about_this_run(tmp_path: Path) -> None:
    preference = backend_probe.backend_port_preference(start=tmp_path, explicit_port=8321)

    assert preference == PortPreference(port=8321, authority="command")
    assert preference.is_declared


def test_an_environment_port_is_a_statement_too(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(backend_probe.ENV_BACKEND_PORT, "8322")

    assert backend_probe.backend_port_preference(start=tmp_path).is_declared


def test_a_nonsense_environment_port_is_ignored_rather_than_fatal(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(backend_probe.ENV_BACKEND_PORT, "not-a-port")

    assert backend_probe.backend_port_preference(start=tmp_path).authority == "settings_document"


def test_a_workspace_declared_port_is_a_statement_about_this_workspace(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, name="ours")
    config = yaml.safe_load((workspace / "arch-workspace.yaml").read_text(encoding="utf-8"))
    config["backend"] = {"port": 8400}
    (workspace / "arch-workspace.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")

    preference = backend_probe.backend_port_preference(start=workspace)

    assert preference == PortPreference(port=8400, authority="workspace_config")


def test_the_shipped_default_is_a_preference_a_workspace_may_yield(tmp_path: Path) -> None:
    """Every clone carries the same settings document, so its port cannot mean "mine".

    This is the distinction the whole relocation rests on: a stated port is obeyed or refused, a
    default is yielded. Without it, either two checkouts cannot both run, or a stated port moves
    silently under the operator.
    """
    preference = backend_probe.backend_port_preference(start=tmp_path)

    assert preference.authority == "settings_document"
    assert not preference.is_declared


# ── real sockets: no probe stubbed ────────────────────────────────────────────


class _FakeBackendHandler(BaseHTTPRequestHandler):
    """Answers the two endpoints the resolution mechanism actually reads."""

    served_roots: tuple[str, ...] = ()

    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's spelling
        if self.path.startswith("/api/backend-identity"):
            body = json.dumps({"repo_roots": list(self.served_roots), "software_version": "9.9.9"})
        elif self.path.startswith("/api/stats"):
            body = json.dumps({"entities": 0})
        else:
            self.send_response(404)
            self.end_headers()
            return
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: object) -> None:
        return


@pytest.fixture
def serve_backend():
    """Start a fake backend on a free port and return its port; stopped on teardown."""
    servers: list[ThreadingHTTPServer] = []

    def start(workspace: Path) -> int:
        claim = _claim_of(workspace)
        handler = type(
            "_Handler",
            (_FakeBackendHandler,),
            {"served_roots": (str(claim.engagement_root), str(claim.enterprise_root))},
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        servers.append(server)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return int(server.server_address[1])

    yield start

    for server in servers:
        server.shutdown()
        server.server_close()


def test_over_real_sockets_a_free_port_costs_one_connection_attempt(monkeypatch, tmp_path: Path) -> None:
    """No HTTP against a port nothing holds — the common case in a plan, and the one that was slow.

    A closed loopback port does not always refuse: on WSL2 the SYN is dropped, so an HTTP probe waits
    out its whole timeout. Nine such candidates took twelve seconds, and the daemon start that was
    waiting on the answer reported a timeout while its backend was coming up perfectly well.
    """
    http_probes: list[int] = []
    monkeypatch.setattr(
        backend_endpoint, "probe_backend", lambda port, timeout_s=1.0: http_probes.append(port) or False
    )
    monkeypatch.setattr(
        backend_endpoint, "probe_identity_on_port", lambda port, timeout_s=1.0: http_probes.append(port)
    )

    # 1 is a privileged port nothing in a test environment listens on.
    observation = backend_endpoint.observe_endpoint(1)

    assert observation.socket_taken is False
    assert observation.answers_probe is False
    assert http_probes == []


def test_over_real_sockets_a_workspace_attaches_to_its_own_backend(
    monkeypatch, tmp_path: Path, serve_backend
) -> None:
    ours = _workspace(tmp_path, name="ours")
    own_port = serve_backend(ours)

    plan = backend_endpoint.plan_workspace_endpoint(
        cwd=ours,
        may_start=True,
        preference=PortPreference(port=own_port, authority="settings_document"),
    )

    assert plan == AttachToBackend(port=own_port, identity=_identity_of(ours))


def test_over_real_sockets_a_neighbours_backend_pushes_us_to_our_own_port(
    monkeypatch, tmp_path: Path, serve_backend
) -> None:
    ours = _workspace(tmp_path, name="ours")
    theirs = _workspace(tmp_path, name="theirs")
    their_port = serve_backend(theirs)

    plan = backend_endpoint.plan_workspace_endpoint(
        cwd=ours,
        may_start=True,
        preference=PortPreference(port=their_port, authority="settings_document"),
    )

    assert isinstance(plan, StartBackendOn)
    assert plan.port == derived_port(_claim_of(ours).fingerprint)
    assert plan.moved_from == their_port
    assert plan.moved_because == "foreign"


def test_over_real_sockets_two_workspaces_reach_their_own_backends(
    tmp_path: Path, serve_backend
) -> None:
    ours = _workspace(tmp_path, name="ours")
    theirs = _workspace(tmp_path, name="theirs")
    our_port = serve_backend(ours)
    their_port = serve_backend(theirs)
    _record_backend(ours, port=our_port, pid=1)
    _record_backend(theirs, port=their_port, pid=2)

    for workspace, expected in ((ours, our_port), (theirs, their_port)):
        plan = backend_endpoint.plan_workspace_endpoint(
            cwd=workspace,
            may_start=False,
            # Both workspaces prefer the same port, as two clones of this project do.
            preference=PortPreference(port=our_port, authority="settings_document"),
        )
        assert isinstance(plan, AttachToBackend)
        assert plan.port == expected


def test_over_real_sockets_a_refusal_names_the_repositories_it_found(
    tmp_path: Path, serve_backend
) -> None:
    ours = _workspace(tmp_path, name="ours")
    theirs = _workspace(tmp_path, name="theirs")
    their_port = serve_backend(theirs)

    plan = backend_endpoint.plan_workspace_endpoint(
        cwd=ours,
        may_start=False,
        preference=PortPreference(port=their_port, authority="command"),
    )

    assert isinstance(plan, RefuseEndpoint)
    assert str(_claim_of(theirs).engagement_root) in plan.reason
