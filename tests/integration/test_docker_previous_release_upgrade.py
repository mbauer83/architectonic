"""Container acceptance for upgrading a mounted previous-release deployment.

This test is opt-in because it requires a Docker daemon and an image built from the
current checkout. The ordinary integration suite covers the same fixture through the
public CLI; this boundary test proves the container entrypoint applies it before serving
and then reaches its production health check.
"""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import stat
import subprocess
import tarfile
import time
import uuid
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from src.domain.assurance.signals_schema import SIGNALS_SCHEMA_VERSION
from src.domain.guidance.guidance import GUIDANCE_FORMAT
from src.infrastructure.workspace.engagement_repo_template import create_engagement_repo
from tests.support.previous_release_deployment import (
    GUIDANCE_BODY,
    UNRELATED_NOTE_BODY,
    build_previous_release_deployment,
    signals_schema_version,
)

_ENABLED = os.environ.get("ARCH_DOCKER_ACCEPTANCE") == "1"
_IMAGE = os.environ.get("ARCH_DOCKER_IMAGE", "architectonic:upgrade-acceptance")
_VOLUME_EXPORT = os.environ.get("ARCH_DOCKER_VOLUME_EXPORT")
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_HISTORY_COMMIT = "85803c3"  # the published initial commit — the oldest upgradeable model state
_ENGAGEMENT_SUBTREE = "engagements/ENG-ARCH-REPO/architecture-repository"


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        check=check,
        capture_output=True,
        text=True,
        timeout=180,
    )


def _docker_logs(container: str) -> str:
    result = subprocess.run(
        ["docker", "logs", container],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=180,
    )
    return result.stdout


def _make_container_writable(root: Path) -> None:
    """Allow the image's fixed non-root uid to mutate this disposable fixture."""
    for path in (root, *root.rglob("*")):
        mode = path.stat().st_mode
        permissions = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP
        permissions |= stat.S_IROTH | stat.S_IWOTH
        if path.is_dir():
            permissions |= stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        path.chmod(stat.S_IMODE(mode) | permissions)


def _container_settings(settings_path: Path) -> None:
    raw: object = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
    data = raw if isinstance(raw, dict) else {}
    data["deployment"] = {
        "workspace_root": "/deployment/workspace",
        "assurance_db_path": "/deployment/.arch-assurance/store.db",
        "signals_db_path": "/deployment/.arch-assurance/security-signals.db",
        "guidance_cache_root": "/deployment/guidance-cache",
    }
    settings_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )


def _historical_engagement(destination: Path) -> None:
    archived = subprocess.run(
        ["git", "archive", "--format=tar", f"{_HISTORY_COMMIT}:{_ENGAGEMENT_SUBTREE}"],
        cwd=_PROJECT_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
    )
    destination.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archived.stdout), mode="r:") as archive:
        archive.extractall(destination, filter="data")
    _git(destination, "init", "-q")
    _git(destination, "config", "user.email", "acceptance@local.invalid")
    _git(destination, "config", "user.name", "Upgrade Acceptance")
    _git(destination, "add", "-A")
    _git(destination, "commit", "-q", "-m", f"model snapshot {_HISTORY_COMMIT}")


def _wait_for_health(container: str, timeout_seconds: float = 150.0) -> str:
    deadline = time.monotonic() + timeout_seconds
    last = "starting"
    while time.monotonic() < deadline:
        inspected = _docker(
            "inspect", "--format", "{{.State.Status}} {{.State.Health.Status}}", container,
            check=False,
        )
        if inspected.returncode != 0:
            return f"inspect-failed: {inspected.stderr.strip()}"
        last = inspected.stdout.strip()
        if last == "running healthy" or last.startswith("exited "):
            return last
        time.sleep(2)
    return last


def _run_detached(container: str, mounts: list[str], environment: list[str]) -> None:
    args = ["run", "--detach", "--name", container]
    for mount in mounts:
        args.extend(("--mount", mount))
    for entry in environment:
        args.extend(("--env", entry))
    result = _docker(*args, _IMAGE)
    assert result.stdout.strip() != ""


def _assert_healthy(container: str) -> str:
    health = _wait_for_health(container)
    logs = _docker_logs(container)
    assert health == "running healthy", f"container state: {health}\n{logs}"
    return logs


@pytest.mark.skipif(
    not _ENABLED,
    reason="set ARCH_DOCKER_ACCEPTANCE=1 after building the current acceptance image",
)
def test_previous_release_volume_upgrades_before_healthy(tmp_path: Path) -> None:
    _docker("image", "inspect", _IMAGE)
    deployment = build_previous_release_deployment(tmp_path / "deployment")
    _container_settings(deployment.manifest.settings_document.path)
    engagement = deployment.root / "engagement"
    _historical_engagement(engagement)
    create_engagement_repo(deployment.root / "enterprise")
    (deployment.root / "workspace").mkdir()
    added_schema = engagement / ".arch-repo" / "schemata" / "attributes.resource.schema.json"
    assert not added_schema.exists()
    _make_container_writable(deployment.root)

    container = f"architectonic-upgrade-{uuid.uuid4().hex[:12]}"
    _run_detached(
        container,
        [
            f"type=bind,src={deployment.root},dst=/deployment",
            "type=bind,src="
            f"{deployment.manifest.settings_document.path},dst=/app/config/settings.yaml",
        ],
        [
            "ARCH_WORKSPACE_CONFIG=/deployment/no-workspace-config.yaml",
            "ARCH_REPO_ROOT=/deployment/engagement",
            "ARCH_ENTERPRISE_ROOT=/deployment/enterprise",
            "ARCH_ENABLE_ASSURANCE=false",
            "ARCH_READ_ONLY=1",
            "GIT_CONFIG_COUNT=2",
            "GIT_CONFIG_KEY_0=safe.directory",
            "GIT_CONFIG_VALUE_0=/deployment/engagement",
            "GIT_CONFIG_KEY_1=safe.directory",
            "GIT_CONFIG_VALUE_1=/deployment/enterprise",
        ],
    )

    try:
        logs = _assert_healthy(container)
        upgrade_at = logs.index("Upgrading persisted formats")
        current_at = logs.index("Persisted formats current — proceeding")
        serve_at = logs.index("Starting arch-backend")
        assert upgrade_at < current_at < serve_at
        assert deployment.guidance_doc.read_text(encoding="utf-8") == (
            f"guidance_format: {GUIDANCE_FORMAT}\n{GUIDANCE_BODY}"
        )
        assert signals_schema_version(deployment.signals_db) == SIGNALS_SCHEMA_VERSION
        assert deployment.unrelated_note.read_text(encoding="utf-8") == UNRELATED_NOTE_BODY
        assert added_schema.is_file()
    finally:
        _docker("rm", "--force", container, check=False)


def _volume_data(export: Path, volume: str) -> Path:
    """Locate one exported volume inside the export set.

    Docker Compose prefixes volume names with its project name, which defaults to the checkout
    directory. Discovered rather than hardcoded: the repository is being renamed, and a test that
    embeds the old name fails after the move for a reason that has nothing to do with what it
    verifies. `ARCH_DOCKER_COMPOSE_PROJECT` pins the prefix when the export came from a differently
    named directory than the one running the test.
    """
    prefix = os.environ.get("ARCH_DOCKER_COMPOSE_PROJECT")
    candidates = (
        [export / f"{prefix}_{volume}"] if prefix
        else sorted(export.glob(f"*_{volume}")) or [export / volume]
    )
    for candidate in candidates:
        if (candidate / "_data").is_dir():
            return candidate / "_data"
    raise AssertionError(
        f"no exported volume matching '*_{volume}' under {export} "
        f"(found: {sorted(p.name for p in export.iterdir()) if export.is_dir() else 'nothing'}). "
        "Set ARCH_DOCKER_COMPOSE_PROJECT if the export used a different Compose project name."
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.skipif(
    not _ENABLED or _VOLUME_EXPORT is None,
    reason="set ARCH_DOCKER_ACCEPTANCE=1 and ARCH_DOCKER_VOLUME_EXPORT to an exported volume set",
)
def test_exported_compose_volumes_upgrade_before_healthy(tmp_path: Path) -> None:
    assert _VOLUME_EXPORT is not None
    export = Path(_VOLUME_EXPORT).resolve()
    source_data = _volume_data(export, "arch-data")
    source_groups = source_data / "engagement" / ".arch-repo" / "groups.yaml"
    original_digest = _sha256(source_groups)
    assert "meta_ontology: archimate-next" in source_groups.read_text(encoding="utf-8")

    copied: dict[str, Path] = {}
    for volume in ("arch-data", "arch-state", "arch-assurance", "arch-home"):
        destination = tmp_path / volume
        shutil.copytree(_volume_data(export, volume), destination)
        copied[volume] = destination
    _make_container_writable(tmp_path)

    container = f"architectonic-export-upgrade-{uuid.uuid4().hex[:12]}"
    _run_detached(
        container,
        [
            f"type=bind,src={copied['arch-data']},dst=/data",
            f"type=bind,src={copied['arch-state']},dst=/app/.arch",
            f"type=bind,src={copied['arch-assurance']},dst=/app/.arch-assurance",
            f"type=bind,src={copied['arch-home']},dst=/home/arch",
        ],
        [
            "ARCH_WORKSPACE_CONFIG=/app/no-workspace-config.yaml",
            "ARCH_REPO_ROOT=/data/engagement",
            "ARCH_ENTERPRISE_ROOT=/data/enterprise",
            "ARCH_ENABLE_ASSURANCE=false",
            "ARCH_READ_ONLY=1",
            "GIT_CONFIG_COUNT=2",
            "GIT_CONFIG_KEY_0=safe.directory",
            "GIT_CONFIG_VALUE_0=/data/engagement",
            "GIT_CONFIG_KEY_1=safe.directory",
            "GIT_CONFIG_VALUE_1=/data/enterprise",
        ],
    )

    try:
        logs = _assert_healthy(container)
        migrated_groups = copied["arch-data"] / "engagement" / ".arch-repo" / "groups.yaml"
        migrated_config = copied["arch-data"] / "engagement" / ".arch-repo" / "config.yaml"
        assert "meta_ontology: archimate-4" in migrated_groups.read_text(encoding="utf-8")
        assert "meta_ontology: archimate-next" not in migrated_groups.read_text(encoding="utf-8")
        assert "group-meta-ontology-archimate-4-rename" in migrated_config.read_text(
            encoding="utf-8"
        )
        upgrade_at = logs.index("Upgrading persisted formats")
        applied_at = logs.index("group-meta-ontology-archimate-4-rename")
        serve_at = logs.index("Starting arch-backend")
        assert upgrade_at < applied_at < serve_at
        assert _sha256(source_groups) == original_digest
    finally:
        _docker("rm", "--force", container, check=False)
