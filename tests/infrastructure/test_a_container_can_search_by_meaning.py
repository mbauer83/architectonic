"""A container deployment can turn semantic search on, and fetches the model once, not per start.

The weights are not in the image: a build that downloaded them would download them again on every
uncached build, and every image would carry 31 MB its deployment may never use. They go into a named
volume at the directory the backend reads, on the first start that asks for them.

These read the shipped entrypoint and compose files, because those are what an operator deploys; the
settings step is executed as the entrypoint runs it.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from src.infrastructure.bootstrap.embedding_model_asset import MODEL_RELPATH

ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = (ROOT / "docker" / "entrypoint.sh").read_text(encoding="utf-8")
MODELS_IN_CONTAINER = f"/app/{Path(MODEL_RELPATH).parts[0]}"


@pytest.mark.parametrize("compose", ["docker-compose.yml", "docker-compose.demo.yml"])
def test_the_model_directory_the_backend_reads_is_a_named_volume(compose: str) -> None:
    """So a restart or a rebuild finds what the first start downloaded."""
    services = yaml.safe_load((ROOT / compose).read_text(encoding="utf-8"))
    mounts = services["services"]["app"]["volumes"]
    named = [m.split(":")[0] for m in mounts if m.split(":")[1:2] == [MODELS_IN_CONTAINER]]
    assert named and named[0] in services["volumes"]


def test_the_image_does_not_fetch_the_model() -> None:
    assert "get-embedding-model" not in (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_the_model_is_fetched_before_the_backend_starts_and_only_when_search_is_on() -> None:
    fetch = ENTRYPOINT.index("if get-embedding-model")
    assert ENTRYPOINT.index("storage_read_model_semantic_search") < fetch < ENTRYPOINT.index("exec arch-backend")


def test_the_demo_turns_it_on_unless_told_otherwise() -> None:
    assert 'ARCH_SEMANTIC_SEARCH="${ARCH_SEMANTIC_SEARCH:-true}"' in ENTRYPOINT


def _settings_step() -> str:
    match = re.search(r"python - \"\$SETTINGS_PATH\" <<'PY'\n(.*?)\nPY\n", ENTRYPOINT, re.DOTALL)
    assert match is not None
    return match.group(1)


def _run_settings_step(tmp_path: Path, semantic: str | None) -> dict:
    settings = tmp_path / "settings.yaml"
    settings.write_text(yaml.safe_dump({"storage": {"read_model": {"semantic_search": True}}}), encoding="utf-8")
    env = {**os.environ, "ARCH_ASSURANCE_ON": "false"}
    env.pop("ARCH_SEMANTIC_SEARCH", None)
    if semantic is not None:
        env["ARCH_SEMANTIC_SEARCH"] = semantic
    subprocess.run([sys.executable, "-", str(settings)], input=_settings_step(), text=True, env=env, check=True)
    return yaml.safe_load(settings.read_text(encoding="utf-8"))


def test_unset_leaves_what_the_settings_document_says(tmp_path: Path) -> None:
    assert _run_settings_step(tmp_path, None)["storage"]["read_model"] == {"semantic_search": True}


@pytest.mark.parametrize(("stated", "expected"), [("true", True), ("false", False), ("off", False)])
def test_a_stated_switch_is_written_into_the_settings(tmp_path: Path, stated: str, expected: bool) -> None:
    assert _run_settings_step(tmp_path, stated)["storage"]["read_model"]["semantic_search"] is expected
