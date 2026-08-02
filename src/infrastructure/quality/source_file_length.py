"""Source-file length policy checks for non-test backend (Python) and frontend
(TypeScript/Vue) code.

Neither Ruff nor this project's ESLint config provides a native, baseline-ratcheting
max-file-length rule (ESLint's built-in `max-lines` has no clean per-file grandfather
mechanism short of one config override per oversized file). This module implements the
project's local policy once, for both languages, so it can be enforced in tests and CI
without expanding either lint stack.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SOURCE_FILE_SOFT_LIMIT = 250
SOURCE_FILE_HARD_LIMIT = 350

_FRONTEND_ROOT = "tools/gui/src"
_FRONTEND_EXTENSIONS = (".ts", ".vue")
_FRONTEND_EXCLUDED_SUFFIXES = (".test.ts", ".d.ts")

#: Generated output is not authored source, so no authoring policy applies to it. Keyed on the
#: project's naming convention rather than a list of filenames: the point of the convention is that
#: a reader — and this check — can tell generated from authored without consulting a registry.
_FRONTEND_GENERATED_SUFFIX = ".generated.ts"

# TEMPORARY grandfathered baseline: these pre-existing files exceed the hard limit and
# MUST be refactored into smaller modules; the recorded value is each file's current
# counted size, so none of them may grow further. Do not add new entries — new files
# must satisfy SOURCE_FILE_HARD_LIMIT outright. Remove each entry as its file is
# refactored below the hard limit.
#
# One entry has been raised since it was recorded: `_sqlite_store.py` went 396 → 401 when
# the domain layer was grouped into concern subpackages and one four-name import no longer
# fit on a single line. That is import reflow, not new logic, and the file is still owed a
# refactor — but a mechanical re-wrap should not read as an unexplained ratchet upward.
SOURCE_FILE_BASELINE_LIMITS: dict[str, int] = {
    "src/application/verification/artifact_verifier.py": 403,
    "src/infrastructure/artifact_index/_sqlite_store.py": 401,
    "src/infrastructure/artifact_index/service.py": 543,
    "tools/gui/src/ui/components/ArtifactReferenceInput.vue": 619,
    "tools/gui/src/ui/components/AssuranceAnalysisPicker.vue": 407,
    "tools/gui/src/ui/components/EntityGroupNavTree.vue": 353,
    "tools/gui/src/ui/components/EntityPickerInput.vue": 437,
    "tools/gui/src/ui/components/SaveChangesDialog.vue": 355,
    "tools/gui/src/ui/diagram-types/activity/ActivityStepItem.vue": 412,
    "tools/gui/src/ui/views/AssuranceBrowseView.vue": 596,
    "tools/gui/src/ui/views/AssuranceCastWizardView.vue": 599,
    "tools/gui/src/ui/views/AssuranceNodeForm.vue": 354,
    "tools/gui/src/ui/views/AssuranceStpaWizardView.vue": 447,
    "tools/gui/src/ui/views/AssuranceSupplyChainWizardView.vue": 431,
    "tools/gui/src/ui/views/CreateDiagramView.vue": 494,
    "tools/gui/src/ui/views/DocumentCreateView.vue": 606,
    "tools/gui/src/ui/views/DocumentDetailView.vue": 432,
    "tools/gui/src/ui/views/EntitiesView.vue": 505,
    "tools/gui/src/ui/views/EntityCreateView.vue": 530,
    "tools/gui/src/ui/views/GraphExploreView.vue": 457,
    "tools/gui/src/ui/views/GroupManagementView.vue": 618,
}


@dataclass(frozen=True)
class SourceLengthViolation:
    path: str
    counted_lines: int
    limit: int
    reason: str


def _iter_backend_source_files(repo_root: Path) -> list[Path]:
    return sorted((repo_root / "src").rglob("*.py"))


def _iter_frontend_source_files(repo_root: Path) -> list[Path]:
    frontend_root = repo_root / _FRONTEND_ROOT
    return sorted(
        path
        for extension in _FRONTEND_EXTENSIONS
        for path in frontend_root.rglob(f"*{extension}")
        if "__tests__" not in path.parts
        and not path.name.endswith(_FRONTEND_GENERATED_SUFFIX)
        and not path.name.endswith(_FRONTEND_EXCLUDED_SUFFIXES)
    )


def iter_policy_source_files(repo_root: Path) -> list[Path]:
    return [*_iter_backend_source_files(repo_root), *_iter_frontend_source_files(repo_root)]


def counted_source_lines(path: Path) -> int:
    comment_prefix = "#" if path.suffix == ".py" else "//"
    return sum(
        1
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith(comment_prefix)
    )


def find_source_length_violations(repo_root: Path) -> list[SourceLengthViolation]:
    violations: list[SourceLengthViolation] = []
    for path in iter_policy_source_files(repo_root):
        rel = path.relative_to(repo_root).as_posix()
        counted = counted_source_lines(path)
        if counted <= SOURCE_FILE_HARD_LIMIT:
            continue

        baseline = SOURCE_FILE_BASELINE_LIMITS.get(rel)
        if baseline is None:
            violations.append(
                SourceLengthViolation(
                    path=rel,
                    counted_lines=counted,
                    limit=SOURCE_FILE_HARD_LIMIT,
                    reason="new file exceeds hard limit",
                )
            )
            continue

        if counted > baseline:
            violations.append(
                SourceLengthViolation(
                    path=rel,
                    counted_lines=counted,
                    limit=baseline,
                    reason="existing oversized file grew beyond recorded baseline",
                )
            )
    return violations
