"""The toolchain is declared once, and everything that builds, tests or ships the product follows it.

`test_local_gates_match_ci` holds *which* commands CI runs to the list a developer runs. This holds the
other half: what they run *on*. The two can agree on every command and still disagree about the
answer, because the answer depends on the toolchain.

**The incident.** On 2026-11-09 the 0.11.0 release commit was pushed with every local gate green, and
every CI job that installs the frontend failed at `npm ci`: "Missing: glob@13.0.7 from lock file". The
lock had been written by npm 12 on a developer box, with range-keyed `overrides` that npm 12 honours;
CI's Node 20 bundles npm 10, which resolved those overrides differently and refused the lock. Nothing
declared which npm was right, so neither was wrong until a machine nobody was watching said so. Python
had the same shape, unexercised: CI, the release build and the image on 3.13, the developer box on 3.14.

**The rule.** One declaration per toolchain, read by everything rather than restated beside it:

* Node and npm: `engines` in `tools/gui/package.json`, one major each. `engine-strict` in
  `tools/gui/.npmrc` makes npm refuse to install — and so to write the lock — on anything else, here or
  in CI. CI's `actions/setup-node` reads the same field through `node-version-file`.
* Python: `.python-version`. uv builds the local environment from it, and `actions/setup-python` reads
  it through `python-version-file`.
* The `Dockerfile` cannot read either file, so this test holds its base images to them, and holds its
  frontend stage to installing with the `.npmrc` that carries the enforcement. So too the licence
  register's record of those images (`licenses/native.json`), which the published notices are built from.

**The support floor is the toolchain.** `requires-python` and the ruff/zuban targets equal
`.python-version`: a floor below it would promise a Python nothing tests. Raising one means raising the
other. `@types/node` is held to the declared Node for the reason the first version of this file was
written: types ahead of the runtime let `tsc` accept APIs the build machine does not have (measured
2026-09-01: types on 22 against a Node 20 build). The installation guide states the declared versions,
because under engine-strict and `requires-python` they are the only ones that install.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

_ROOT = Path(__file__).resolve().parents[2]
_GUI = _ROOT / "tools" / "gui"
_WORKFLOWS = sorted((_ROOT / ".github" / "workflows").glob("*.yml"))
_PACKAGE = "tools/gui/package.json"
_PYTHON_VERSION_FILE = ".python-version"

#: `FROM node:<major>…` in the image stage that builds the frontend.
_IMAGE_NODE = re.compile(r"^FROM\s+node:(\d+)", re.MULTILINE)
#: Every Python the image is built from: the uv builder stage and the runtime stage.
_IMAGE_PYTHON = re.compile(r"^FROM\s+\S*?python:?(\d+\.\d+)", re.MULTILINE)
#: One major, written `N.x` — the form npm's `engines` and setup-node's version spec both read.
_ONE_MAJOR = re.compile(r"^(\d+)\.x$")


def _engines() -> dict[str, str]:
    return json.loads((_GUI / "package.json").read_text(encoding="utf-8")).get("engines", {})


def _declared_major(tool: str) -> int:
    spec = _engines().get(tool, "")
    match = _ONE_MAJOR.match(spec)
    assert match, (
        f"`engines.{tool}` in {_PACKAGE} is {spec!r}; it must name one major as `N.x`. A range admits "
        "two toolchains, and two toolchains are how a lock one of them wrote fails to install on the other."
    )
    return int(match.group(1))


def _declared_python() -> str:
    return (_ROOT / _PYTHON_VERSION_FILE).read_text(encoding="utf-8").strip()


def _setup_steps(action: str) -> Iterator[tuple[str, str, dict[str, object]]]:
    """`(workflow, job, with)` for every step that uses `action`, in every workflow."""
    for path in _WORKFLOWS:
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_name, job in workflow["jobs"].items():
            for step in job.get("steps", []):
                if str(step.get("uses", "")).startswith(action):
                    yield path.name, job_name, dict(step.get("with") or {})


def _dockerfile() -> str:
    return (_ROOT / "Dockerfile").read_text(encoding="utf-8")


def _dockerfile_images() -> list[str]:
    return re.findall(r"^FROM\s+(\S+)", _dockerfile(), re.MULTILINE)


def _pyproject() -> dict:
    return tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


# ── The declarations ─────────────────────────────────────────────────────────


def test_node_and_npm_are_each_declared_as_one_major() -> None:
    assert _declared_major("node") > 0
    assert _declared_major("npm") > 0


def test_npm_refuses_to_install_on_any_other_toolchain() -> None:
    """Without this, `engines` is advice: npm warns, installs anyway, and may rewrite the lock."""
    settings = [
        line.split("=", 1)[1].strip()
        for line in (_GUI / ".npmrc").read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("engine-strict")
    ]
    assert settings == ["true"]


def test_python_is_declared_once_as_one_minor() -> None:
    assert re.fullmatch(r"\d+\.\d+", _declared_python()), (
        f"{_PYTHON_VERSION_FILE} must name one minor version, e.g. 3.14"
    )


# ── CI reads them ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("action", "version_key", "file_key", "declaration"),
    [
        ("actions/setup-node", "node-version", "node-version-file", _PACKAGE),
        ("actions/setup-python", "python-version", "python-version-file", _PYTHON_VERSION_FILE),
    ],
)
def test_every_workflow_reads_the_declaration_rather_than_restating_it(
    action: str, version_key: str, file_key: str, declaration: str
) -> None:
    steps = list(_setup_steps(action))
    assert steps, f"no {action} step in any workflow — the assertion below would be vacuous"
    stated = [f"{workflow}:{job}" for workflow, job, given in steps if version_key in given]
    assert not stated, (
        f"{action} is given a literal `{version_key}` in {stated}. Read `{declaration}` with "
        f"`{file_key}` instead: a second spelling of the version is the drift this file exists to stop."
    )
    elsewhere = sorted({str(given.get(file_key)) for _, _, given in steps} - {declaration})
    assert not elsewhere, f"{action} reads {elsewhere}, not `{declaration}`"


# ── The image follows them ───────────────────────────────────────────────────


def test_the_image_builds_the_frontend_on_the_declared_node() -> None:
    majors = {int(m) for m in _IMAGE_NODE.findall(_dockerfile())}
    assert majors == {_declared_major("node")}, (
        f"the Dockerfile builds the frontend on Node {sorted(majors)}, while {_PACKAGE} declares "
        f"{_declared_major('node')}. `npm ci` there would refuse the install under engine-strict."
    )


def test_the_image_installs_the_frontend_with_its_npmrc() -> None:
    """The release-age floor and engine-strict live in `.npmrc`; an install without it has neither."""
    copied_before_install = _dockerfile().split("RUN npm ci", 1)[0]
    assert re.search(r"^COPY\s+.*tools/gui/\.npmrc", copied_before_install, re.MULTILINE)


def test_the_image_is_built_and_run_on_the_declared_python() -> None:
    versions = set(_IMAGE_PYTHON.findall(_dockerfile()))
    assert versions == {_declared_python()}, (
        f"the Dockerfile's Python stages use {sorted(versions)}, while {_PYTHON_VERSION_FILE} says "
        f"{_declared_python()}. The image is what ships; it must be what the gates ran on."
    )


def test_the_licence_register_names_the_images_the_dockerfile_uses() -> None:
    """The notices are generated from this register; an image it no longer names is one shipped unrecorded."""
    register = json.dumps(json.loads((_ROOT / "licenses" / "native.json").read_text(encoding="utf-8")))
    missing = [image for image in _dockerfile_images() if image not in register]
    assert not missing, f"licenses/native.json does not name {missing}, which the Dockerfile builds from"


def test_the_documented_gates_run_the_locked_python_tools() -> None:
    """A bare `ruff` in the gate list runs whatever is on PATH — not the version the lock and CI use."""
    documented = (_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    bare = re.findall(r"`((?:ruff|zuban|pytest|pip-audit)\s[^`]*)`", documented)
    assert not bare, f"AGENTS.md documents {bare} without `uv run`, so they run outside the lock"


# ── The support floor is the toolchain ───────────────────────────────────────


def test_the_supported_python_is_the_python_everything_runs_on() -> None:
    project = _pyproject()
    declared = _declared_python()
    nodot = declared.replace(".", "")
    stated = {
        "requires-python": project["project"]["requires-python"],
        "ruff target-version": project["tool"]["ruff"]["target-version"],
        "zuban python_version": project["tool"]["zuban"]["python_version"],
    }
    expected = {
        "requires-python": f">={declared}",
        "ruff target-version": f"py{nodot}",
        "zuban python_version": declared,
    }
    assert stated == expected, (
        f"{_PYTHON_VERSION_FILE} is {declared}, but pyproject.toml states {stated}. A floor below the "
        "toolchain promises a Python nothing tests; move them together."
    )


# ── What describes the runtime matches it ────────────────────────────────────


def test_the_declared_node_types_match_the_declared_node() -> None:
    declared = json.loads((_GUI / "package.json").read_text(encoding="utf-8"))
    types = int(declared["devDependencies"]["@types/node"].lstrip("^~>=< ").split(".")[0])
    assert types == _declared_major("node"), (
        f"`@types/node` is on {types} while the build runs Node {_declared_major('node')}. Types ahead "
        "of the runtime let the typechecker accept APIs the build machine does not have; types behind "
        "it hide ones it does. Move them with `engines.node`."
    )


def test_the_installation_guide_states_the_declared_toolchain() -> None:
    """Under engine-strict the documented minimum is the only version that installs, so it must be it."""
    guide = (_ROOT / "docs" / "02-installation.md").read_text(encoding="utf-8")
    declared = {"Node.js": str(_declared_major("node")), "npm": str(_declared_major("npm")),
                "Python": _declared_python()}
    for label, version in declared.items():
        row = re.search(rf"^\|\s*{re.escape(label)}\s*\|\s*([\d.]+)\s*\|", guide, re.MULTILINE)
        assert row, f"docs/02-installation.md has no `{label}` row in its requirements table"
        assert row.group(1) == version, (
            f"docs/02-installation.md says {label} {row.group(1)}; the declaration says {version}"
        )
