"""The infrastructure adapter for the application-owned `PumlSyntaxPort`.

The scheduler, file-inventory and incremental-state adapters depend only on stdlib and
application code, so they live in the application layer
(`src/application/verification/_verifier_stdlib_adapters.py`) and the verifier resolves
them itself. This one cannot: it draws with PlantUML, which runs in a Java process that infrastructure owns.

Wired to the verifier by `verifier_factory.build_artifact_verifier`; nothing should
construct it directly.
"""

from __future__ import annotations

import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from src.application.verification._verifier_rules_rendered_picture import RenderedPictureChecks
from src.application.verification.artifact_verifier_syntax import (
    check_puml_syntax,
    check_puml_syntax_batch,
)
from src.application.verification.artifact_verifier_types import Issue
from src.infrastructure.rendering import plantuml_runner
from src.infrastructure.rendering.puml_safety import is_managed_include

#: A managed-fragment marker as a stored body may keep it (`!include ../_archimate-stereotypes.puml`).
_MANAGED_MARKER_RE = re.compile(r"^\s*!include\s+((?:\.\./)*(_[\w.-]+\.puml))\s*$", re.MULTILINE)

__all__ = ["DefaultPumlSyntaxAdapter"]


class DefaultPumlSyntaxAdapter:
    """Delegates to the syntax check, drawing with this process's PlantUML (`plantuml_runner`).

    Managed include fragments are skipped. `_archimate-glyphs.puml` and its siblings are
    generated sprite/stereotype/relation definitions with no `@startuml` of their own —
    they are meant to be included, and PlantUML run against one standalone exits non-zero,
    which would surface as an E350 error on a file that is entirely correct. The whole-repo
    pass never reaches them (the inventory scans `diagram-catalog/diagrams/`, they live one
    level above), but `artifact_verify_file` takes a caller-supplied path, so an agent can
    point it at one.

    With *picture_checks*, the picture each check renders is read before it is discarded, and what
    its geometry decides is reported with the syntax findings — one render answers both.
    """

    def __init__(self, picture_checks: RenderedPictureChecks | None = None) -> None:
        self._picture_checks = picture_checks

    def check_one(self, path: Path, loc: str) -> list[Issue]:
        if is_managed_include(path.name):
            return []
        with _staged_for_plantuml([path]) as staged:
            checked = staged.get(path, path)
            issues = check_puml_syntax(
                checked, loc, drawing=plantuml_runner.PLANTUML, picture_checks=self._picture_checks,
            )
            return _reported_against(issues, staged=checked, source=path, loc=loc)

    def check_batch(self, paths: list[Path]) -> dict[Path, list[Issue]]:
        checkable = [p for p in paths if not is_managed_include(p.name)]
        if not checkable:
            return {p: [] for p in paths}
        with _staged_for_plantuml(checkable) as staged:
            results = check_puml_syntax_batch(
                list(staged.values()), drawing=plantuml_runner.PLANTUML, picture_checks=self._picture_checks,
            )
            found = {
                source: _reported_against(results.get(copy, []), staged=copy, source=source, loc=str(source))
                for source, copy in staged.items()
            }
            # A file that could not be read could not be staged; PlantUML is asked about it where it is.
            found.update({
                p: check_puml_syntax(p, str(p), drawing=plantuml_runner.PLANTUML) for p in checkable if p not in staged
            })
            return {p: found.get(p, []) for p in paths}


def _reported_against(issues: list[Issue], *, staged: Path, source: Path, loc: str) -> list[Issue]:
    """*issues* speaking of the file the caller named, not of the copy PlantUML was shown."""
    if staged == source:
        return issues
    return [
        replace(
            issue,
            location=loc if issue.location == str(staged) else issue.location,
            message=issue.message.replace(str(staged), str(source)),
        )
        for issue in issues
    ]


@contextmanager
def _staged_for_plantuml(paths: list[Path]) -> Iterator[dict[Path, Path]]:
    """Each readable path → a copy, its managed-fragment markers inlined, in a directory of its own.

    **Inlined**, because PlantUML runs sandboxed and the sandbox refuses every file include —
    including a stored body's marker for a fragment the product generated itself. Every render
    already inlines those fragments before PlantUML sees the body; the syntax check has to hand over
    the same bytes, or it reports a refusal as a syntax error. A marker naming anything but a managed
    fragment is left in place, where the body policy refuses it.

    **A directory of its own**, so two sources of one name in a batch keep two copies.
    """
    with tempfile.TemporaryDirectory(prefix="arch-syntax-") as scratch:
        staged: dict[Path, Path] = {}
        for index, path in enumerate(paths):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            inlined = _MANAGED_MARKER_RE.sub(lambda m, base=path.parent: _fragment_or_marker(m, base), text)
            copy = Path(scratch) / str(index) / path.name
            copy.parent.mkdir()
            copy.write_text(inlined, encoding="utf-8")
            staged[path] = copy
        yield staged


def _fragment_or_marker(match: re.Match[str], base: Path) -> str:
    target = (base / match.group(1)).resolve()
    if not is_managed_include(target.name) or not target.is_file():
        return match.group(0)
    return target.read_text(encoding="utf-8")
