"""Which files, URLs and environment values a PlantUML diagram body may reference: the one policy.

PlantUML's preprocessor and its creole markup can read local files and fetch URLs. The first version
of this check listed the directives it forbade, and a list of what is forbidden is only as good as
its author's memory: `!include_once` and `!include_many` matched no entry, `<img:…>` and
`$sprite="img:…"` were not in it at all, and each read a server file into the rendered output. So
the policy names what a body *may* reference, and every other file, URL or environment reference is
refused:

- `!include <…>` — the bundled standard library (C4 and the like), which PlantUML reads from its own
  jar, not from the filesystem;
- `!include ../_*.puml` for the managed fragments the renderers generate, which the product expands
  into the body before PlantUML runs;
- an image embedded as `data:image/…;base64,…`, and nothing else after `img:`.

Refused: every other `!include*` and `!import*`, `!theme … from`, the builtins that read the
environment or the filesystem, and any `img:` or `<img src` that names a file or a URL.

This is the first of two barriers. The renderer also runs under PlantUML's sandbox security profile
(`artifact_verifier_syntax.plantuml_command`), so a spelling this policy has not anticipated still
cannot reach the filesystem. The policy exists to refuse early, with a reason, on every write and
render path: create, edit, preview, the on-disk render after a write, and the verifier's syntax check,
which is the path a body takes when it arrives through git.
"""

from __future__ import annotations

import re

_MANAGED_INCLUDE_BASENAMES = frozenset({
    "_archimate-stereotypes.puml",
    "_archimate-glyphs.puml",
    "_archimate-relations.puml",
    "_macros.puml",
})

#: Any preprocessor directive that brings in another source, however it is spelled:
#: `!include`, `!include_once`, `!include_many`, `!includeurl`, `!includesub`, `!import`, …
_SOURCE_DIRECTIVE_RE = re.compile(r"^\s*!(include\w*|import\w*)\b\s*(.*)$", re.IGNORECASE)
_THEME_FROM_RE = re.compile(r"^\s*!theme\b.*\bfrom\b", re.IGNORECASE)
#: Builtins that read the environment or the filesystem, or say what exists on it.
_IO_BUILTIN_RE = re.compile(
    r"%(?:load_?json|get_?env|file_?exists|dir_?path|file_?name|get_all_theme|load_?theme)\b", re.IGNORECASE
)
#: Every place creole or a stdlib macro takes an image: `<img:X>`, `<img src=X>`, `$sprite="img:X"`.
_IMAGE_TARGET_RE = re.compile(r"(?:\bimg:|<img\s+src\s*=\s*[\"']?)([^\"'>\s{}]*)", re.IGNORECASE)
_EMBEDDED_IMAGE_RE = re.compile(r"^data:image/[a-z0-9.+-]+;base64,", re.IGNORECASE)
_MANAGED_INCLUDE_RE = re.compile(
    r"^(?:\.\./)*(" + "|".join(re.escape(b) for b in _MANAGED_INCLUDE_BASENAMES) + r")$"
)


class UnsafePumlError(ValueError):
    """A PlantUML diagram body references a file, a URL or an environment value."""


def is_managed_include(basename: str) -> bool:
    """Whether a file is one of the generated include fragments the renderers emit.

    These have no `@startuml` of their own: they define sprites, stereotypes and relation
    styling for other diagrams to include. Standalone they are neither renderable nor
    syntax-checkable, and treating them as diagrams reports errors against correct files.
    """
    return basename in _MANAGED_INCLUDE_BASENAMES


def find_unsafe_puml_directives(puml_body: str) -> list[str]:
    """The lines of a body that reference a file, a URL or an environment value (empty when none do)."""
    offenders: list[str] = []
    for raw in puml_body.splitlines():
        line = raw.strip()
        if _line_reaches_outside(line):
            offenders.append(line)
    return offenders


def assert_user_puml_safe(puml_body: str) -> None:
    """Raise `UnsafePumlError` naming the lines of a body that reference a file, URL or environment value."""
    offenders = find_unsafe_puml_directives(puml_body)
    if offenders:
        joined = "; ".join(offenders[:5])
        raise UnsafePumlError(
            "PUML body contains forbidden file/network preprocessor directives "
            f"({len(offenders)}): {joined}. A body may include only the bundled standard library "
            "(`!include <…>`) and the renderer's own managed fragments, and may embed images only as "
            "`data:image/…;base64,…`; it may not read files, fetch URLs or read the environment."
        )


def _line_reaches_outside(line: str) -> bool:
    if _THEME_FROM_RE.match(line) or _IO_BUILTIN_RE.search(line):
        return True
    if any(not _EMBEDDED_IMAGE_RE.match(target) for target in _IMAGE_TARGET_RE.findall(line)):
        return True
    match = _SOURCE_DIRECTIVE_RE.match(line)
    if match is None:
        return False
    if match.group(1).lower() != "include":
        return True  # include_once, include_many, includeurl, includesub, import…: never in a body
    target = match.group(2).strip().strip('"').strip("'").strip()
    if target.startswith("<") and target.endswith(">") and "://" not in target:
        return False  # bundled standard library: read from the jar, not the filesystem
    return _MANAGED_INCLUDE_RE.match(target) is None
