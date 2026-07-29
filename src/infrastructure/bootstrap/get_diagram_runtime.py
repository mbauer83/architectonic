"""Fetch the supported PlantUML and Graphviz runtime for this project."""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

from src.application.verification.artifact_verifier_syntax import PLANTUML_JAR_RELPATHS
from src.infrastructure.bootstrap.get_plantuml import PLANTUML_VERSION
from src.infrastructure.bootstrap.get_plantuml import download as download_plantuml

GRAPHVIZ_VERSION = "14.1.5"
GRAPHVIZ_MIN_VERSION = "2.49.0"
GRAPHVIZ_TAR_XZ_URL = (
    "https://gitlab.com/api/v4/projects/4207231/packages/generic/"
    f"graphviz-releases/{GRAPHVIZ_VERSION}/graphviz-{GRAPHVIZ_VERSION}.tar.xz"
)
GRAPHVIZ_TAR_XZ_SHA256 = "b017378835f7ca12f1a3f1db5c338d7e7af16b284b7007ad73ccec960c1b45b3"


def _repo_root() -> Path:
    candidate = Path(__file__).resolve()
    for _ in range(6):
        candidate = candidate.parent
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise SystemExit("Could not locate repository root from pyproject.toml")


def _parse_version(text: str) -> tuple[int, ...] | None:
    import re

    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())


def _dot_version(dot_path: Path | str) -> tuple[int, ...] | None:  # pragma: no cover — subprocess Graphviz probe
    proc = subprocess.run([str(dot_path), "-V"], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return None
    return _parse_version((proc.stdout + proc.stderr).strip())


def _download_bytes(url: str) -> bytes:  # pragma: no cover — network download, not testable in unit tests
    with urllib.request.urlopen(url) as resp:  # noqa: S310
        return resp.read()


def _sha256hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().lower()


def _ensure_graphviz_from_source(root: Path, *, force: bool) -> Path:  # pragma: no cover
    tools_dir = root / "tools"
    output_dir = tools_dir / "graphviz"
    dot_name = "dot.exe" if os.name == "nt" else "dot"
    dot_path = output_dir / "bin" / dot_name
    if dot_path.exists() and not force:
        return dot_path

    archive_path = tools_dir / f"graphviz-{GRAPHVIZ_VERSION}.tar.xz"
    src_parent = tools_dir / "_graphviz-src"
    src_dir = src_parent / f"graphviz-{GRAPHVIZ_VERSION}"

    print(f"Downloading Graphviz {GRAPHVIZ_VERSION} source …")
    tar_bytes = _download_bytes(GRAPHVIZ_TAR_XZ_URL)
    actual_sha = _sha256hex(tar_bytes)
    if actual_sha != GRAPHVIZ_TAR_XZ_SHA256:
        raise SystemExit(f"Graphviz SHA-256 mismatch: expected {GRAPHVIZ_TAR_XZ_SHA256}, got {actual_sha}")

    tools_dir.mkdir(parents=True, exist_ok=True)
    archive_path.write_bytes(tar_bytes)
    shutil.rmtree(src_parent, ignore_errors=True)
    src_parent.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive_path, mode="r:xz") as tf:
        tf.extractall(src_parent)

    if not src_dir.exists():
        raise SystemExit(f"Expected extracted source directory missing: {src_dir}")

    shutil.rmtree(output_dir, ignore_errors=True)

    configure = src_dir / "configure"
    if not configure.exists():
        raise SystemExit(f"Expected configure script missing: {configure}")

    print(f"Building Graphviz {GRAPHVIZ_VERSION} into {output_dir} …")
    subprocess.run(
        [str(configure), f"--prefix={output_dir}"],
        cwd=src_dir,
        check=True,
    )
    subprocess.run(
        ["make", f"-j{max(1, os.cpu_count() or 1)}"],
        cwd=src_dir,
        check=True,
    )
    subprocess.run(["make", "install"], cwd=src_dir, check=True)

    if not dot_path.exists():
        raise SystemExit(f"Graphviz build completed but dot was not found at {dot_path}")
    return dot_path


# Per-platform install plans, ordered by preference: (package-manager binary, commands to run).
# The first plan whose binary is on PATH wins.
_GRAPHVIZ_INSTALL_PLANS: dict[str, list[tuple[str, list[list[str]]]]] = {
    "darwin": [("brew", [["brew", "install", "graphviz"]])],
    "linux": [
        ("apt-get", [["apt-get", "update"], ["apt-get", "install", "-y", "graphviz"]]),
        ("dnf", [["dnf", "install", "-y", "graphviz"]]),
        ("pacman", [["pacman", "-Sy", "--noconfirm", "graphviz"]]),
    ],
    "windows": [
        (
            "winget",
            [["winget", "install", "--id", "Graphviz.Graphviz", "-e",
              "--accept-source-agreements", "--accept-package-agreements"]],
        ),
        ("choco", [["choco", "install", "graphviz", "-y"]]),
    ],
}


def _install_graphviz_system() -> None:  # pragma: no cover — subprocess package manager, not testable in unit tests
    plans = _GRAPHVIZ_INSTALL_PLANS.get(platform.system().lower(), [])
    commands = next((cmds for tool, cmds in plans if shutil.which(tool)), None)
    if not commands:
        raise SystemExit("No supported system package manager found for Graphviz installation")
    for cmd in commands:
        print(f"Running: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)


def _plantuml_path(root: Path) -> Path:
    """Where this command puts the jar: the canonical location, shared with `get-plantuml`.

    Both provision the same artefact through the same downloader, so both read the location
    from PLANTUML_JAR_RELPATHS rather than naming a path of their own.
    """
    return root / PLANTUML_JAR_RELPATHS[0]


def _check_runtime(root: Path) -> int:  # pragma: no cover — subprocess JVM/Graphviz check, not testable in unit tests
    from src.application.verification.artifact_verifier_syntax import find_graphviz_dot
    from src.infrastructure.bootstrap.check_diagram_runtime import main as check_runtime

    dot = find_graphviz_dot()
    if dot is not None:
        os.environ["GRAPHVIZ_DOT"] = str(dot)
    try:
        check_runtime(["--jar", str(_plantuml_path(root)), "--min-graphviz", GRAPHVIZ_MIN_VERSION])
    except SystemExit as exc:
        return int(exc.code or 1)
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Re-download and rebuild even if present")
    parser.add_argument(
        "--graphviz-mode",
        choices=("auto", "source", "system", "none"),
        default="auto",
        help="How to provision Graphviz (default: auto)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only verify the currently installed runtime",
    )
    args = parser.parse_args(argv)

    root = _repo_root()
    plantuml_path = _plantuml_path(root)

    if args.check:
        sys.exit(_check_runtime(root))

    rc = download_plantuml(PLANTUML_VERSION, plantuml_path, force=args.force)
    if rc != 0:
        sys.exit(rc)

    if args.graphviz_mode != "none":
        chosen_mode = args.graphviz_mode
        if chosen_mode == "auto":
            chosen_mode = "source" if platform.system().lower() == "linux" else "system"

        if chosen_mode == "system":
            _install_graphviz_system()
        else:
            dot_path = _ensure_graphviz_from_source(root, force=args.force)
            os.environ["GRAPHVIZ_DOT"] = str(dot_path)

    sys.exit(_check_runtime(root))


if __name__ == "__main__":
    main()
