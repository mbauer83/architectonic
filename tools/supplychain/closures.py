#!/usr/bin/env python
"""The two dependency closures, named once so every supply-chain gate asks the same question.

"Which pins ship" and "which pins CI executes" are decisions about the product, not flags on a
command. They were spelled inside the licence gate's Python collector, where a second consumer could
only reach them by copying the flag list — and a copied flag list drifts silently, which in a
supply-chain gate means a confident verdict over the wrong set. So the two answers live here, the
flags are written down once, and every gate calls the function rather than respelling the selection.

- ``shipped_closure()`` — what a user is exposed to: the main dependencies plus the ``gui`` group and
  the ``cloud-archive`` extra. ``fastapi`` and the ``/api/events`` websocket stack are declared in the
  ``gui`` *group* rather than in ``[project].dependencies`` or an extra, so a closure taken from the
  extras alone omits the only network-facing code in the product.
- ``development_closure()`` — what CI executes, which is an attack surface of its own: a compromised
  test plugin runs with repository write access.

The two are nested — every shipped pin is a development pin — but they answer different obligations,
so they stay two functions rather than one parameterised by a flag.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Which of the two questions a closure answers. Adding a third is a decision about the product's
#: obligations, not a convenience, which is why this is a closed set and not a free string.
ClosureName = Literal["shipped", "development"]

#: The selection per closure, and the only place these flags appear.
_SELECTION: Mapping[ClosureName, tuple[str, ...]] = {
    "shipped": ("--no-dev", "--group", "gui", "--extra", "cloud-archive"),
    "development": ("--all-groups", "--all-extras"),
}

#: Shape of the export, shared by both closures and required by their consumers:
#: ``--no-emit-project`` drops the editable project itself, which is neither a licensed third party
#: nor a registry artifact anything can audit; ``--no-hashes`` because ``pip-audit --no-deps`` refuses
#: a hashed requirement file; ``--no-annotate`` so every non-comment line is a pin. Environment
#: markers are deliberately kept — stripping them makes an installer try ``pywin32`` on Linux.
_SHAPE = ("--no-hashes", "--no-emit-project", "--no-annotate")

#: ANSI escape sequences, stripped before the export is parsed as data. With colour on, an escape
#: sequence reaches stdout and parses as a package named "\x1b" with an unknown licence — failing a
#: gate for a reason that has nothing to do with the gate, and only where output is a terminal.
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

#: Colour off, deterministically, for the same reason.
_QUIET_ENV = {"NO_COLOR": "1", "TERM": "dumb"}


@dataclass(frozen=True, slots=True)
class Closure:
    """One resolved dependency set: the requirement lines as exported, and the pins parsed from them.

    ``requirements`` keeps its environment markers, so it can be handed to a scanner as a requirement
    file. ``pins`` maps package name to version for the consumers that inventory rather than install.
    """

    name: ClosureName
    requirements: str
    pins: Mapping[str, str]


def shipped_closure() -> Closure:
    """The closure a user is exposed to — the set the licence inventory and the notices describe."""
    return _export("shipped")


def development_closure() -> Closure:
    """The closure CI executes — the shipped set plus everything the repository builds and tests with."""
    return _export("development")


def _export(name: ClosureName) -> Closure:
    exported = subprocess.run(
        ["uv", "export", *_SELECTION[name], *_SHAPE],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        env={**os.environ, **_QUIET_ENV},
    ).stdout
    return Closure(name=name, requirements=exported, pins=_pins(exported))


def _pins(exported: str) -> Mapping[str, str]:
    """`name -> version` for every requirement line, first occurrence winning.

    A requirement line always names a package; anything else is noise from the tool that produced it,
    and inventing an entry from noise is worse than skipping it.
    """
    found: dict[str, str] = {}
    for raw in exported.splitlines():
        line = _ANSI.sub("", raw).strip()
        if not line or line.startswith(("#", "-")):
            continue
        spec = line.partition(";")[0].strip()
        package, _, version = spec.partition("==")
        package = package.split("[")[0].strip()
        if not package or not package[0].isalnum():
            continue
        found.setdefault(package, version.strip())
    return found
