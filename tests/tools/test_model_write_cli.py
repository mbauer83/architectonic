from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.infrastructure.write import artifact_write_cli


@pytest.fixture()
def live_backend(monkeypatch):
    """Simulate a running backend: state resolves and probe succeeds."""
    monkeypatch.setattr(artifact_write_cli, "read_backend_state", lambda path: {"port": 8000})
    monkeypatch.setattr(artifact_write_cli, "probe_backend", lambda port: True)


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
