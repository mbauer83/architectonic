"""W387 — a stored body whose generated header is not what its renderer states today.

A stored body keeps a copy of what the renderer states rather than what its author drew: the palette,
the glyphs, a relationship's line style, the label width bound. The write path restates that copy on
every edit, so a diagram nobody edits keeps the one it was written with — an upgrade that changes the
palette leaves every untouched diagram drawing the old one. `generate_static_includes --check` named
those bodies, and it is a development gate nobody authoring content runs; `artifact_verify`, which is,
passed them in silence.

A warning: nothing the diagram says about the model is wrong, and an edit repairs it. Asked of the
diagram type's renderer through its optional capability, so a notation whose header states nothing
generated is silent rather than exempted.
"""

from __future__ import annotations

from pathlib import Path

from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.domain.ontology_representation.ontology_protocol import DiagramTypeModule, generated_header_is_current
from src.domain.repository.frontmatter import body_after_frontmatter


def check_generated_header(
    module: DiagramTypeModule | None,
    content: str,
    repo_root: Path,
    result: VerificationResult,
    loc: str,
) -> None:
    if module is None or generated_header_is_current(module.renderer, body_after_frontmatter(content), repo_root):
        return
    result.issues.append(Issue(
        Severity.WARNING,
        "W387",
        "The body's generated header — palette, glyphs, relationship styles, label width — is not what "
        "the renderer states today, so the diagram draws with superseded styling. Any edit of the "
        "diagram through artifact_edit_diagram restates it, without touching what was drawn.",
        loc,
    ))
