"""The infrastructure adapter for the application-owned `PumlSyntaxPort`.

The scheduler, file-inventory and incremental-state adapters depend only on stdlib and
application code, so they live in the application layer
(`src/application/verification/_verifier_stdlib_adapters.py`) and the verifier resolves
them itself. This one cannot: it runs PlantUML in a Java subprocess, which is infrastructure.

Wired to the verifier by `verifier_factory.build_artifact_verifier`; nothing should
construct it directly.
"""

from __future__ import annotations

from pathlib import Path

from src.application.verification.artifact_verifier_syntax import (
    check_puml_syntax,
    check_puml_syntax_batch,
)
from src.application.verification.artifact_verifier_types import Issue
from src.infrastructure.rendering.puml_safety import is_managed_include

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
        return check_puml_syntax(path, loc)

    def check_batch(self, paths: list[Path]) -> dict[Path, list[Issue]]:
        checkable = [p for p in paths if not is_managed_include(p.name)]
        results = check_puml_syntax_batch(checkable) if checkable else {}
        return {p: results.get(p, []) for p in paths}
