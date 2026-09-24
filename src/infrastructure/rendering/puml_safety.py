"""Safety helpers shared by PlantUML renderers and render pipelines."""

from __future__ import annotations

import re
import warnings
from collections.abc import Mapping
from typing import Any

from src.domain.repository.frontmatter import body_after_frontmatter

DEFAULT_PUML_SIZE_WARNING_THRESHOLD = 8_000

_STARTUML_NAME_RE = re.compile(r"@startuml[^\n]*")

# What a body may ask PlantUML to read is one policy with one owner, in the application layer so the
# verifier can apply it too: `src.application.puml_directive_policy`. Re-exported here for the
# renderers and write paths that have always imported it from this module.
from src.application.puml_directive_policy import (  # noqa: E402
    UnsafePumlError,
    assert_user_puml_safe,
    find_unsafe_puml_directives,
    is_managed_include,
)

__all__ = [
    "DEFAULT_PUML_SIZE_WARNING_THRESHOLD",
    "UnsafePumlError",
    "assert_user_puml_safe",
    "configured_puml_size_warning_threshold",
    "find_unsafe_puml_directives",
    "is_managed_include",
    "strip_leading_puml_frontmatter",
    "strip_startuml_name",
    "warn_when_puml_exceeds_threshold",
]


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
