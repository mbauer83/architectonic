"""The infrastructure adapter for the application-owned `PumlSyntaxPort`.

The scheduler, file-inventory and incremental-state adapters depend only on stdlib and
application code, so they live in the application layer
(`src/application/verification/_verifier_stdlib_adapters.py`) and the verifier resolves
them itself. This one cannot: it runs PlantUML in a Java subprocess, which is infrastructure.

Wired to the verifier by `verifier_factory.build_artifact_verifier`; nothing should
construct it directly.
"""

from __future__ import annotations

import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from src.application.verification.artifact_verifier_syntax import (
    check_puml_syntax,
    check_puml_syntax_batch,
)
from src.application.verification.artifact_verifier_types import Issue
from src.infrastructure.rendering.puml_safety import is_managed_include

#: A managed-fragment marker as a stored body may keep it (`!include ../_archimate-stereotypes.puml`).
_MANAGED_MARKER_RE = re.compile(r"^\s*!include\s+((?:\.\./)*(_[\w.-]+\.puml))\s*$", re.MULTILINE)

__all__ = ["DefaultPumlSyntaxAdapter"]


class DefaultPumlSyntaxAdapter:
    """Delegates to the subprocess-based PlantUML runner.

    Managed include fragments are skipped. `_archimate-glyphs.puml` and its siblings are
    generated sprite/stereotype/relation definitions with no `@startuml` of their own —
    they are meant to be included, and PlantUML run against one standalone exits non-zero,
    which would surface as an E350 error on a file that is entirely correct. The whole-repo
    pass never reaches them (the inventory scans `diagram-catalog/diagrams/`, they live one
    level above), but `artifact_verify_file` takes a caller-supplied path, so an agent can
    point it at one.
    """

    def check_one(self, path: Path, loc: str) -> list[Issue]:
        if is_managed_include(path.name):
            return []
        with _with_managed_includes_inlined([path]) as checked:
            return check_puml_syntax(checked[path], loc)

    def check_batch(self, paths: list[Path]) -> dict[Path, list[Issue]]:
        checkable = [p for p in paths if not is_managed_include(p.name)]
        if not checkable:
            return {p: [] for p in paths}
        with _with_managed_includes_inlined(checkable) as checked:
            results = check_puml_syntax_batch([checked[p] for p in checkable])
            return {p: results.get(checked.get(p, p), []) for p in paths}


@contextmanager
def _with_managed_includes_inlined(paths: list[Path]) -> Iterator[dict[Path, Path]]:
    """Each path, or a temporary copy of it with its managed-fragment markers replaced by the fragment.

    PlantUML runs sandboxed, and the sandbox refuses every file include — including a stored body's
    marker for a fragment the product generated itself. Every render already inlines those fragments
    before PlantUML sees the body; the syntax check has to hand over the same bytes, or it reports a
    refusal as a syntax error. A marker naming anything but a managed fragment is left in place, where
    the body policy refuses it.
    """
    with tempfile.TemporaryDirectory(prefix="arch-syntax-") as scratch:
        mapping: dict[Path, Path] = {}
        for index, path in enumerate(paths):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                mapping[path] = path
                continue
            inlined = _MANAGED_MARKER_RE.sub(lambda m, base=path.parent: _fragment_or_marker(m, base), text)
            if inlined == text:
                mapping[path] = path
                continue
            copy = Path(scratch) / f"{index}-{path.name}"
            copy.write_text(inlined, encoding="utf-8")
            mapping[path] = copy
        yield mapping


def _fragment_or_marker(match: re.Match[str], base: Path) -> str:
    target = (base / match.group(1)).resolve()
    if not is_managed_include(target.name) or not target.is_file():
        return match.group(0)
    return target.read_text(encoding="utf-8")
