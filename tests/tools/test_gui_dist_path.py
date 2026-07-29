"""Regression: the backend resolves the built GUI at <repo>/tools/gui/dist.

The path was computed with one too few `.parent` hops (landing in src/), so gui_dist.exists()
was always False and the SPA static mount was never added — the backend served nothing from
the built GUI and every client route 404'd. This guards the depth so the mount is wired.
"""

from __future__ import annotations

from pathlib import Path

import src.infrastructure.backend.arch_backend_app as app_module


def test_gui_dist_resolves_to_repo_root_tools_gui() -> None:
    module_file = Path(app_module.__file__).resolve()
    repo_root = module_file.parents[3]

    # parents[3] must be the repository root, not an intermediate package dir.
    assert (repo_root / "pyproject.toml").exists(), f"parents[3] is not the repo root: {repo_root}"
    assert (repo_root / "tools" / "gui").is_dir(), f"tools/gui not under {repo_root}"
    # The off-by-one (parents[2]) lands in src/, where tools/gui does not exist.
    assert not (module_file.parents[2] / "tools" / "gui").exists()
