from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.infrastructure.write import artifact_write_cli


@pytest.fixture()
def live_backend(monkeypatch):
    """Simulate a backend serving this repository: state resolves, it answers, and it says so.

    The third part is not decoration: the CLI sends writes, so it confirms that the backend at the
    recorded port serves the repository it was given rather than a neighbouring workspace's.
    """
    monkeypatch.setattr(artifact_write_cli, "read_backend_state", lambda path: {"port": 8000})
    monkeypatch.setattr(artifact_write_cli, "probe_backend", lambda port: True)
    monkeypatch.setattr(artifact_write_cli, "port_serves_workspace", lambda port, claim: True)


class _FakeResp:
    def __init__(self, payload: dict) -> None:
        self._data = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> "_FakeResp":
        return self

    def __exit__(self, *args: object) -> None:
        pass


def test_cli_delete_entity_dry_run(tmp_path: Path, capsys, live_backend, monkeypatch) -> None:
    eid = "REQ@1000000000.TestAa.delete-me"
    monkeypatch.setattr(
        artifact_write_cli,
        "urlopen",
        lambda req, timeout=10.0: _FakeResp({"artifact_id": eid, "path": "model/x.md", "warnings": []}),
    )

    rc = artifact_write_cli.main(["--repo-root", str(tmp_path), "delete-entity", eid, "--dry-run"])
    captured = capsys.readouterr()

    assert rc == 0
    assert "Would delete entity" in captured.out


def test_cli_delete_diagram_dry_run(tmp_path: Path, capsys, live_backend, monkeypatch) -> None:
    did = "diag-delete"
    monkeypatch.setattr(
        artifact_write_cli,
        "urlopen",
        lambda req, timeout=10.0: _FakeResp({"artifact_id": did, "path": "diagrams/x.puml", "warnings": []}),
    )

    rc = artifact_write_cli.main(["--repo-root", str(tmp_path), "delete-diagram", did, "--dry-run"])
    captured = capsys.readouterr()

    assert rc == 0
    assert "Would delete diagram" in captured.out


def test_cli_refuses_to_write_to_a_backend_serving_another_repository(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    """A recorded port outlives the backend that wrote it; the next occupant may be a neighbour's."""
    monkeypatch.setattr(artifact_write_cli, "read_backend_state", lambda path: {"port": 8000})
    monkeypatch.setattr(artifact_write_cli, "probe_backend", lambda port: True)
    monkeypatch.setattr(artifact_write_cli, "port_serves_workspace", lambda port, claim: False)
    sent: list[object] = []
    monkeypatch.setattr(artifact_write_cli, "urlopen", lambda req, timeout=10.0: sent.append(req))

    rc = artifact_write_cli.main(
        ["--repo-root", str(tmp_path), "delete-entity", "REQ@1000000000.TestAa.delete-me"]
    )

    assert rc == 1
    assert sent == [], "no write may be sent to a backend that does not serve this repository"
    assert "does not serve" in capsys.readouterr().err
