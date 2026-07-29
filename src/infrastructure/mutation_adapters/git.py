from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path


def run_git(
    repo: Path,
    args: Sequence[str],
    *,
    timeout: float | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a synchronous git mutation or probe through the mediated adapter."""
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        env=dict(env) if env is not None else os.environ.copy(),
    )
