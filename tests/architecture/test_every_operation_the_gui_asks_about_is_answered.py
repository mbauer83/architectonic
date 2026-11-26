"""Every operation the GUI offers a control by is one the backend answers for.

`useCan` refuses a name the backend's projection (`denied_operations`) does not hold, so a control
named after an operation outside the catalog is never offered, with a reason nobody can act on. The
names are read where the GUI states them: a `useCan('…')` call, a `PermittedButton`'s `operation`,
and the table of an artifact's writes (`domain/artifactWrites.ts`).
"""

from __future__ import annotations

import re
from pathlib import Path

from src.application.operation_catalog import OPERATION_CATALOG
from tests.support.source_paths import TOOLS

_GUI = TOOLS / "gui" / "src"
_QUOTED = re.compile(r"'([a-z][a-z0-9_.-]*)'")
_ASKED = re.compile(r"useCan\(([^)]*\)?)\)")
_BUTTON = re.compile(r'(?<![:\w-])operation="([^"]+)"')
#: An operation named by its REST operation id, as the table of an artifact's writes names them.
_OPERATION_ID = re.compile(r"'([a-z]+_[a-z_]+)'")
_WRITES_TABLE = _GUI / "domain" / "artifactWrites.ts"


def _sources() -> list[Path]:
    return [
        path for path in sorted(_GUI.rglob("*"))
        if path.suffix in {".ts", ".vue"} and "__tests__" not in path.parts and not path.name.endswith(".test.ts")
    ]


def _asked(text: str) -> set[str]:
    named = {name for call in _ASKED.findall(text) for name in _QUOTED.findall(call)}
    return named | set(_BUTTON.findall(text))


def test_the_gui_names_its_writes_where_this_rule_reads_them() -> None:
    assert _WRITES_TABLE.is_file()
    asked = {name for path in _sources() for name in _asked(path.read_text(encoding="utf-8"))}
    assert {"viewpoints_create_viewpoint", "documents_create_document", "changes_apply_candidate"} <= asked


def test_every_operation_the_gui_asks_about_is_in_the_catalog() -> None:
    unanswered = {
        f"{path.relative_to(_GUI)}: {name}"
        for path in _sources()
        for name in _asked(path.read_text(encoding="utf-8"))
        if name not in OPERATION_CATALOG
    }
    tabled = set(_OPERATION_ID.findall(_WRITES_TABLE.read_text(encoding="utf-8"))) - OPERATION_CATALOG.keys()
    assert not unanswered and not tabled, (
        "these name no operation the backend answers for, so their controls are never offered: "
        f"{sorted(unanswered)} {sorted(tabled)}"
    )
