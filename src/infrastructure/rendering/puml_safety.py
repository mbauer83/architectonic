"""Safety helpers shared by PlantUML renderers and render pipelines."""

from __future__ import annotations

import re
import warnings
from collections.abc import Mapping
from typing import Any

from src.domain.repository.frontmatter import body_after_frontmatter

DEFAULT_PUML_SIZE_WARNING_THRESHOLD = 8_000

_STARTUML_NAME_RE = re.compile(r"@startuml[^\n]*")

# ── User-submitted PUML safety (untrusted-input hardening) ──────────────────────
#
# PlantUML's preprocessor can read local files and fetch URLs (`!include`,
# `!includeurl`, `!import`, `!theme … from …`, `%load_json`, `%getenv`). With the
# default security profile these succeed and their result is embedded in the
# rendered output, so a submitted body such as `!include /etc/passwd` exfiltrates
# a server file into the returned SVG. PlantUML's own profiles are all-or-nothing
# for our include model (SANDBOX blocks even our trusted macros; ALLOWLIST could
# not be configured to allow relative macro includes while blocking absolutes),
# so the enforceable control is at OUR trust boundary: reject any I/O-capable
# directive a user-submitted body contains, except the exact managed includes our
# own renderers emit (relative `../_*.puml` macros + bundled `<…>` stdlib). Our
# renderers inject the trusted includes themselves — a user body never needs an
# arbitrary one.

_MANAGED_INCLUDE_BASENAMES = frozenset({
    "_archimate-stereotypes.puml",
    "_archimate-glyphs.puml",
    "_archimate-relations.puml",
    "_macros.puml",
})
def is_managed_include(basename: str) -> bool:
    """Whether a file is one of the generated include fragments the renderers emit.

    These have no `@startuml` of their own: they define sprites, stereotypes and relation
    styling for other diagrams to include. Standalone they are neither renderable nor
    syntax-checkable, and treating them as diagrams reports errors against correct files.
    """
    return basename in _MANAGED_INCLUDE_BASENAMES


# Preprocessor directives that read a file or fetch a URL. `!include` is special-cased
# (it has a safe managed form); the rest have no legitimate use in a user body.
_INCLUDE_DIRECTIVE_RE = re.compile(r"^\s*!(include|includeurl|includesub|import|importurl)\b\s*(.*)$", re.IGNORECASE)
_THEME_FROM_RE = re.compile(r"^\s*!theme\b.*\bfrom\b", re.IGNORECASE)
_IO_BUILTIN_RE = re.compile(r"%(?:load_json|loadjson|get_?env|getenv)\b", re.IGNORECASE)
_MANAGED_INCLUDE_RE = re.compile(
    r"^(?:\.\./)*(" + "|".join(re.escape(b) for b in _MANAGED_INCLUDE_BASENAMES) + r")$"
)


class UnsafePumlError(ValueError):
    """A user-submitted PUML body contains a forbidden file/network directive."""


def find_unsafe_puml_directives(puml_body: str) -> list[str]:
    """Return the offending lines of a user-submitted PUML body (empty when safe).

    Safe: any content plus `!include <…>` (bundled stdlib) and `!include ../_*.puml`
    for our managed macros. Unsafe: `!include` of an absolute path / arbitrary
    relative path / URL, and any `!includeurl`/`!includesub`/`!import`/`%load_json`/
    `%getenv`/`!theme … from …`.
    """
    offenders: list[str] = []
    for raw in puml_body.splitlines():
        line = raw.strip()
        if _THEME_FROM_RE.match(line) or _IO_BUILTIN_RE.search(line):
            offenders.append(line)
            continue
        match = _INCLUDE_DIRECTIVE_RE.match(line)
        if match is None:
            continue
        directive = match.group(1).lower()
        target = match.group(2).strip().strip('"').strip("'").strip()
        if directive != "include":
            offenders.append(line)  # includeurl/includesub/import/importurl: never legitimate
            continue
        if target.startswith("<") and target.endswith(">"):
            continue  # bundled stdlib include — no filesystem/network access
        low = target.lower()
        is_absolute = target.startswith(("/", "\\")) or bool(re.match(r"^[a-z]:[\\/]", low))
        if "://" in low or is_absolute or not _MANAGED_INCLUDE_RE.match(target):
            offenders.append(line)
    return offenders


def assert_user_puml_safe(puml_body: str) -> None:
    """Raise UnsafePumlError if a user-submitted PUML body reads files or fetches URLs."""
    offenders = find_unsafe_puml_directives(puml_body)
    if offenders:
        joined = "; ".join(offenders[:5])
        raise UnsafePumlError(
            "PUML body contains forbidden file/network preprocessor directives "
            f"({len(offenders)}): {joined}. Only diagram content and the renderer's own "
            "managed includes are permitted; includes/imports of arbitrary files or URLs are not."
        )


def strip_leading_puml_frontmatter(puml_body: str) -> str:
    """Remove an optional YAML frontmatter block from the start of a PUML body.

    The delimitation this module used to define — CRLF-tolerant, trailing whitespace on both fences,
    closing fence may end the file — is now `domain.repository.frontmatter`'s, for every reader in the
    codebase rather than for PUML alone. It was the most careful of the fourteen and became the only one.
    """
    return body_after_frontmatter(puml_body)


def strip_startuml_name(puml_body: str) -> str:
    """Drop the title after the first ``@startuml`` so PlantUML names output by the input
    file stem.

    The whole remainder of the line is removed — a previous ``@startuml\\s+\\S+`` form stripped
    only the first word, so a multi-word diagram name (e.g. "Artifact Persistence Model") left
    "@startuml Persistence Model" behind. PlantUML then named the output by that leftover and
    the temp→final rename missed it, yielding a misnamed file and a silently failed render.
    """
    return _STARTUML_NAME_RE.sub("@startuml", puml_body, count=1)


def warn_when_puml_exceeds_threshold(
    puml_body: str,
    *,
    threshold: int = DEFAULT_PUML_SIZE_WARNING_THRESHOLD,
) -> None:
    if threshold <= 0 or len(puml_body) <= threshold:
        return
    warnings.warn(
        f"Generated PlantUML body is {len(puml_body)} characters; threshold is {threshold}",
        UserWarning,
        stacklevel=2,
    )


def configured_puml_size_warning_threshold(config: Mapping[str, Any]) -> int:
    rendering = config.get("rendering", {})
    if isinstance(rendering, Mapping) and "output_size_warning_threshold" in rendering:
        return int(rendering["output_size_warning_threshold"])
    if "output_size_warning_threshold" in config:
        return int(config["output_size_warning_threshold"])
    return DEFAULT_PUML_SIZE_WARNING_THRESHOLD
