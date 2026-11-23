"""Exercise CLI mutations against a backend in a separate process."""
from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from tools.quality.fixture_backend import fixture_backend, state_dir_for


@pytest.fixture
def served_repo(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    with fixture_backend() as backend:
        root = backend.workspace.engagement_root
        monkeypatch.setenv("ARCH_BACKEND_STATE_DIR", str(state_dir_for(backend.workspace)))
        active = True

        def forbid_client_write(event: str, args: tuple) -> None:
            if not active or event != "open":
                return
            path, _, flags = args
            if isinstance(path, str) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
                assert not Path(path).resolve().is_relative_to(root), f"CLI opened {path} for writing"

        sys.addaudithook(forbid_client_write)
        try:
            yield root
        finally:
            active = False
