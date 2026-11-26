"""A table cell that holds an id is compared through the id form's owner, never with a bare `===` or `==`.

Beside the register's row for "which spelling of an artifact id is its identity"
(`test_each_syntax_has_one_reader`): that probe finds a reader by the slug separator and the call that cuts at
it, and a plain string comparison has neither — so it could not see the defect this gate exists for. The
Adaptations tab matched adaptation rows to a candidate with `cell(row, 'candidate_architecture') === id`; a
row naming the candidate by its short id never matched, and the adaptation showed no end state and no
stressor, while `answerLinks` beside it joined the same rows through `stableEntityId`.

Which columns hold an id is read from the shipped stress-analysis type — every `id` and `reference` column —
plus the two plain columns that name an element of the naive architecture by id (an element the naive
creates has no file, so neither can be a reference). A cell of one of them, read in the candidate or stress
code, is compared through `stableEntityId` (GUI) or `canonical_entity_key` (backend), never as a string.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.application.artifacts.document_schema import normalize_document_schema
from src.domain.repository.repo_default_stress_analysis import STRESS_ANALYSIS, STRESS_ANALYSIS_SCHEMA

_ROOT = Path(__file__).resolve().parents[2]

#: Plain columns that name an element of the naive architecture by its id.
_ELEMENT_ID_COLUMNS = frozenset({"component", "subject"})

#: Where id cells of an analysis are read: the candidate and stress-analysis code, both sides.
_GUI_FILES = (
    "tools/gui/src/domain/candidates", "tools/gui/src/domain/stressAnalysis",
    "tools/gui/src/ui/components/candidates", "tools/gui/src/ui/components/stressWorkspace",
    "tools/gui/src/ui/views/StressWorkspaceView.vue", "tools/gui/src/ui/composables",
)
_BACKEND_FILES = ("src/application/stress_analysis", "src/application/change_sets", "src/infrastructure/candidates")


def _id_columns() -> frozenset[str]:
    schema = normalize_document_schema(STRESS_ANALYSIS, STRESS_ANALYSIS_SCHEMA)
    typed = {
        column.name for section in schema.sections for table in section.tables for column in table.columns
        if column.kind in ("id", "reference")
    }
    return frozenset(typed | _ELEMENT_ID_COLUMNS)


def _alternation(columns: frozenset[str]) -> str:
    return "|".join(sorted((re.escape(name) for name in columns), key=len, reverse=True))


def _gui_comparison(columns: frozenset[str]) -> re.Pattern[str]:
    read = rf"cell\(\s*[^,()]+,\s*'(?:{_alternation(columns)})'\s*\)"
    return re.compile(rf"{read}\s*[!=]==|[!=]==\s*{read}")


def _backend_comparison(columns: frozenset[str]) -> re.Pattern[str]:
    named = _alternation(columns)
    read = rf"(?:\[\s*\"(?:{named})\"\s*\]|\.get\(\s*\"(?:{named})\"\s*\))(?:\.value)?"
    return re.compile(rf"{read}\s*(?:[!=]=|\bnot in\b|\bin\b)|(?:[!=]=)\s*[\w.]+{read}")


def _files(roots: tuple[str, ...], suffixes: tuple[str, ...]) -> list[Path]:
    found = []
    for root in roots:
        path = _ROOT / root
        found.extend([path] if path.is_file() else sorted(p for p in path.rglob("*") if p.suffix in suffixes))
    return [p for p in found if ".test." not in p.name and "__tests__" not in p.parts]


def _offences(pattern: re.Pattern[str], files: list[Path]) -> list[str]:
    return [
        f"{path.relative_to(_ROOT)}:{number}: {line.strip()}"
        for path in files for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if pattern.search(line)
    ]


def test_the_id_columns_are_read_from_the_shipped_type() -> None:
    assert {"candidate_architecture", "architecture", "component", "subject"} <= _id_columns()


def test_no_gui_candidate_or_stress_code_compares_an_id_cell_as_a_string() -> None:
    offences = _offences(_gui_comparison(_id_columns()), _files(_GUI_FILES, (".ts", ".vue")))
    assert offences == [], (
        "Compare an id cell through `stableEntityId` (`tools/gui/src/domain/artifactId.ts`), or join through "
        "an existing helper such as `answerLinks`; a short id never equals its slugged form:\n" + "\n".join(offences)
    )


def test_no_backend_candidate_or_stress_code_compares_an_id_cell_as_a_string() -> None:
    offences = _offences(_backend_comparison(_id_columns()), _files(_BACKEND_FILES, (".py",)))
    assert offences == [], (
        "Compare an id cell through `canonical_entity_key` (`src/domain/artifact_id.py`); a short id never "
        "equals its slugged form:\n" + "\n".join(offences)
    )


def test_the_probe_finds_the_comparison_that_reached_a_user() -> None:
    """The gate is only as good as its pattern: the line that shipped, and its backend twin, are found."""
    columns = _id_columns()
    assert _gui_comparison(columns).search("  .filter((row) => cell(row, 'candidate_architecture') === id)")
    assert _gui_comparison(columns).search("if (id !== cell(one, 'architecture')) return")
    assert not _gui_comparison(columns).search("cell(row, 'stressor') === stressor")
    assert _backend_comparison(columns).search('if row["candidate_architecture"] == candidate.id:')
    assert _backend_comparison(columns).search('hits = [t for t in ticks if t.get("component") in naive]')
    assert not _backend_comparison(columns).search('if tick.get("stressor") not in held:')
