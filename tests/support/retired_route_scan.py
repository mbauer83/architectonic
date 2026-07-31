"""Token-aware scan for retired route literals in the working tree.

A retired path that survives in a Vite proxy rule, an example in the docs, or a positive test
is a live defect that no other check catches: the code compiles, the suite is green, and the
one request that takes that path 404s in front of a user.

The match has to be token-aware. ``/api/entity`` is a prefix of ``/api/entities``, and a naive
substring search would report every canonical route as a violation of the legacy route it
replaced — the failure mode that makes a scan like this get switched off.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

#: Directories that never contain live route references: build output, caches, dependencies.
_SKIP_DIRECTORIES = frozenset({
    ".git", ".venv", "node_modules", "dist", "__pycache__", ".pytest_cache", ".ruff_cache",
    ".mypy_cache", "coverage", "playwright-report", "test-results", ".arch-repo",
    ".arch-assurance", "htmlcov",
})

#: Files where a retired literal is a *record* rather than a reference.
_SKIP_FILES = frozenset({
    "CHANGELOG.md",  # release history: the old→new mapping consumers migrate against
    "_pending.py",  # the migration ledger itself
    "retired_route_scan.py",  # this module
})

#: Directories whose content is a *record* of what was, not a reference to it. An ADR's Context
#: names the defect it decided against; rewriting that to avoid a retired literal would erase the
#: reason the decision exists.
_RECORD_DIRECTORIES = frozenset({"adr"})

#: Generated output, each with its own drift gate. A retired literal here is a stale artifact those
#: gates report, not a live reference — and the escaped regexes in the timeout policy would trip a
#: path scan on the backslash anyway.
_GENERATED_SUFFIX = ".generated.ts"
_GENERATED_NAMES = frozenset({"routeTimeoutPolicy.json"})

_TEXT_SUFFIXES = frozenset({
    ".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".vue", ".md", ".json", ".yaml", ".yml",
    ".html", ".sh", ".toml",
})


def _literal_pattern(literal: str) -> re.Pattern[str]:
    """Match *literal* only as a whole path, never inside a longer one.

    Both boundaries are load-bearing, and each was found by a false positive:

    * the leading one, because ``/admin/api/entity`` *contains* ``/api/entity`` — the admin surface
      would be reported as a reference to the engagement route it has nothing to do with;
    * the trailing one rejecting ``/``, because a retired literal is retired as a *complete* path.
      ``/api/entity-schemata`` is retired while ``/api/entity-schemata/{artifact_type}`` is its
      live replacement, and without this every canonical route would be flagged as a reference to
      the route it replaced.

    ``{param}`` placeholders match any single path segment, so a template matches both its FastAPI
    spelling and a concrete URL a document or test might use.
    """
    parts = [
        r"[^/?#\s\"']+" if part.startswith("{") and part.endswith("}") else re.escape(part)
        for part in literal.split("/")
    ]
    return re.compile(r"(?<![A-Za-z0-9\-_])" + "/".join(parts) + r"(?![A-Za-z0-9\-_/])")


def scan_files(root: Path) -> Iterator[Path]:
    """Every text file under *root* that could reference a route."""
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in _TEXT_SUFFIXES:
            continue
        if (
            path.name in _SKIP_FILES
            or path.name in _GENERATED_NAMES
            or path.name.endswith(_GENERATED_SUFFIX)
        ):
            continue
        parts = set(path.relative_to(root).parts)
        if (_SKIP_DIRECTORIES | _RECORD_DIRECTORIES) & parts:
            continue
        yield path


def find_retired_literals(
    root: Path, literals: frozenset[str], *, exempt: frozenset[Path] = frozenset()
) -> dict[str, list[str]]:
    """Retired literal → ``path:line`` occurrences, excluding *exempt* files.

    *exempt* names the negative tests that must keep asserting a retired route no longer
    resolves; every other occurrence is a defect.
    """
    patterns = {literal: _literal_pattern(literal) for literal in literals}
    findings: dict[str, list[str]] = {}
    exempt_resolved = {path.resolve() for path in exempt}
    for path in scan_files(root):
        if path.resolve() in exempt_resolved:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, start=1):
            for literal, pattern in patterns.items():
                if pattern.search(line):
                    findings.setdefault(literal, []).append(
                        f"{path.relative_to(root)}:{number}"
                    )
    return findings
