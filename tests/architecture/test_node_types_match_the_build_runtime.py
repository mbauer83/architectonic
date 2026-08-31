"""`@types/node` describes the Node the product is actually built on — not a newer one.

Types ahead of the runtime are a silent correctness loss: `tsc` accepts an API the build machine does
not have, and nothing says so until the build fails somewhere else, on a machine the author is not
looking at. The types are not a currency question, so "a newer major is available" is not an argument
for taking it; what decides them is which Node runs the build.

**Two authorities say which Node that is, and they must not drift from a third.** The shipped image
builds the frontend on the `node:` base named in `Dockerfile`; CI sets up the same major at every
`actions/setup-node` site. This holds the declared types to that major, so a Node upgrade that moves
one and not the others fails here rather than at a build.

**Measured 2026-09-01.** The declared types were `^22.15.17` against a Node 20 build — already a major
ahead, with `@types/node` 26 available. Aligning downward to `^20` is what the rule asks for, and it
costs nothing: the typecheck across all three tsconfigs, the build, the contract check and the unit
suite all pass unchanged.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

_ROOT = Path(__file__).resolve().parents[2]
_GUI = _ROOT / "tools" / "gui"

#: `FROM node:<major>...` in the image that builds the frontend.
_IMAGE_NODE = re.compile(r"^FROM\s+node:(\d+)", re.MULTILINE)


def _declared_types_major() -> int:
    declared = json.loads((_GUI / "package.json").read_text(encoding="utf-8"))
    types = declared["devDependencies"]["@types/node"]
    return int(types.lstrip("^~>=< ").split(".")[0])


def _dockerfile_majors() -> set[int]:
    return {int(m) for m in _IMAGE_NODE.findall((_ROOT / "Dockerfile").read_text(encoding="utf-8"))}


def _ci_majors() -> set[int]:
    workflow = yaml.safe_load((_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    found = set()
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if str(step.get("uses", "")).startswith("actions/setup-node"):
                found.add(int(str(step["with"]["node-version"]).split(".")[0]))
    return found


@pytest.fixture(scope="module")
def build_runtime() -> int:
    majors = _dockerfile_majors() | _ci_majors()
    assert majors, "no Node major found in Dockerfile or ci.yml — the assertions would be vacuous"
    assert len(majors) == 1, (
        f"the build runs on more than one Node major: {sorted(majors)}. Types can only match one, so "
        "settle which is the baseline before this test can say anything."
    )
    return majors.pop()


def test_the_declared_node_types_match_the_node_the_build_uses(build_runtime: int) -> None:
    assert _declared_types_major() == build_runtime, (
        f"`@types/node` is on {_declared_types_major()} while the build runs Node {build_runtime}. "
        "Types ahead of the runtime let the typechecker accept APIs the build machine does not have; "
        "types behind it hide ones it does. Move whichever is wrong — and if the runtime moved, move "
        "`Dockerfile`, every `setup-node` step and the types together."
    )
