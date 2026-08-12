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
#:
#: This list is an approximation of `.gitignore` maintained by hand, and the cost of it drifting is
#: paid here rather than reported: every entry missing from it is read in full, once per file, and
#: matched against every retired literal. `.nyc_output` arrived with the e2e coverage flag and was
#: measured at **841 MB over 221 files**, which took this scan from 2 seconds to over 10 minutes —
#: a gate that slow is a gate a developer starts skipping. Asking git what the repository contains
#: would end the drift, and does not work here: `enterprise-repository` is its own checkout, so
#: `git ls-files` at this root omits content that is genuinely part of the tree being scanned.
_SKIP_DIRECTORIES = frozenset({
    ".git", ".venv", "node_modules", "dist", "__pycache__", ".pytest_cache", ".ruff_cache",
    ".mypy_cache", "coverage", "playwright-report", "test-results", ".arch-repo",
    ".arch-assurance", "htmlcov", ".nyc_output",
})

#: Files where a retired literal is a *record* rather than a reference.
_SKIP_FILES = frozenset({
    "CHANGELOG.md",  # release history: the old→new mapping consumers migrate against
    "_retired.py",  # the record of the retired addresses itself
    "retired_route_scan.py",  # this module
})

#: Directories whose content is a *record* of what was, not a reference to it. An ADR's Context
#: names the defect it decided against; rewriting that to avoid a retired literal would erase the
#: reason the decision exists. ``changelog-assets`` holds the published old→new route map, whose left
#: column is retired addresses by definition — it is what consumers migrate against.
_RECORD_DIRECTORIES = frozenset({"adr", "changelog-assets"})

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


#: How far below a URL literal a request's method may be declared before the two are unrelated.
#: A `fetch(url, { method: 'POST', headers: …, body: … })` spans a handful of lines; beyond that the
#: next `method:` in the file belongs to a different call.
_METHOD_WINDOW = 6

#: One retired *method* on a path that is still live for other methods. `POST /api/assurance/nodes`
#: is gone while `GET /api/assurance/nodes` remains, so the path-level scan above deliberately
#: permits the literal — and a client still POSTing to it gets a 405 that nothing else catches until
#: a browser test hits it.
_CLIENT_CALL_FORMS = (
    # `fetch('/api/x', { method: 'POST' })` and `fetch(`/api/x`, { … })`
    r"fetch\(\s*[`'\"]{path}[`'\"]",
    # `client.post("/api/x"` / `request.post('/api/x'` — the Python and Playwright request APIs
    r"\.{lower}\(\s*[`'\"]{path}[`'\"]",
)


def find_retired_method_calls(
    root: Path,
    retired: dict[tuple[str, str], str],
    *,
    live_paths: frozenset[str],
    exempt: frozenset[Path] = frozenset(),
) -> dict[str, list[str]]:
    """``METHOD path`` → occurrences of a client still using a retired method on a live path.

    The path-level scan cannot see these: it permits any literal whose path still answers to some
    method, which is correct — the path is not retired, one verb on it is. This finds the verb.

    Only the retired pairs whose path is still live are considered; everything else is already
    covered, and reporting it twice would make one defect look like two.
    """
    findings: dict[str, list[str]] = {}
    exempt_resolved = {path.resolve() for path in exempt}
    candidates = [
        (method, template) for (method, template) in retired
        if template in live_paths and "{" not in template
    ]
    if not candidates:
        return findings
    for path in scan_files(root):
        if path.resolve() in exempt_resolved:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for method, template in candidates:
            quoted = re.escape(template)
            for form in _CLIENT_CALL_FORMS:
                pattern = re.compile(form.format(path=quoted, lower=method.lower()))
                for number, line in enumerate(lines, start=1):
                    if not pattern.search(line):
                        continue
                    window = "\n".join(lines[number - 1 : number - 1 + _METHOD_WINDOW])
                    names_method = re.search(
                        rf"method:\s*['\"]{method}['\"]", window, re.IGNORECASE
                    )
                    # `.post(` names its own method; `fetch(` declares it in the options object.
                    if names_method or f".{method.lower()}(" in line:
                        findings.setdefault(f"{method} {template}", []).append(
                            f"{path.relative_to(root)}:{number}"
                        )
    return findings
