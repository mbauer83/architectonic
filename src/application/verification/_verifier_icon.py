"""Verify a shared icon file: its shape, its identity, and that its picture is the one it names.

An icon usually arrives through the upload path, which normalises it; one that arrives through git
has passed no such check, so the verifier holds every icon to what the upload path would have
produced. The codes:

- **E360** the file cannot be read as an icon (missing field, block or frontmatter);
- **E361** its id is not an `ICO@…` id, or the file is not named after it;
- **E362** its `render-digest` does not name the picture it carries;
- **E363** the picture is not a PNG within the stored limits, or its size is not the one declared;
- **W360** an `applies-to` name is no type or specialization the product knows, so the icon applies
  to nothing under it.

A picture is decoded through `StoredPictureInspector`, an adapter; a verifier built without one — a
test's, or one that must not decode — skips that check explicitly, as it skips PlantUML syntax.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from src.application.icons.icon_vocabulary import unknown_applicability_names
from src.application.verification.artifact_verifier_parsing import read_file
from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.application.verification.verifier_ports import PictureProblem, StoredPictureInspector
from src.domain.artifact_id import is_entity_id, parse_entity_id
from src.domain.icons.icon_file import IconFile, IconFileProblem, read_icon_file
from src.domain.icons.icon_ref import ICON_ID_PREFIX
from src.domain.icons.render_form import render_digest

if TYPE_CHECKING:
    from src.application.verification._verifier_snapshot import RepositorySnapshot


def verify_icon(
    path: Path,
    *,
    inspector: StoredPictureInspector | None,
    known_names: frozenset[str] | None = None,
    snapshot: RepositorySnapshot | None = None,
) -> VerificationResult:
    result = VerificationResult(path=path, file_type="icon")
    loc = str(path)
    content = read_file(path, result, loc, snapshot=snapshot)
    if content is None:
        return result
    match read_icon_file(content):
        case IconFileProblem(reason=reason):
            result.issues.append(_error("E360", f"not a readable icon file: {reason}", loc))
        case IconFile() as icon:
            result.issues.extend(
                _identity_issues(icon, path, loc) + _picture_issues(icon, inspector, loc)
                + _applicability_issues(icon, known_names, loc)
            )
    return result


def _identity_issues(icon: IconFile, path: Path, loc: str) -> list[Issue]:
    artifact_id = icon.metadata.artifact_id
    if not (is_entity_id(artifact_id) and parse_entity_id(artifact_id).prefix == ICON_ID_PREFIX):
        return [_error("E361", f"'{artifact_id}' is not an {ICON_ID_PREFIX}@… id", loc)]
    if path.stem != artifact_id:
        return [_error("E361", f"the file is named '{path.stem}', not after its id '{artifact_id}'", loc)]
    return []


def _picture_issues(icon: IconFile, inspector: StoredPictureInspector | None, loc: str) -> list[Issue]:
    meta = icon.metadata
    if render_digest(icon.png) != meta.render_digest:
        return [_error("E362", "the render-digest does not name the picture the file carries", loc)]
    if inspector is None:
        return []
    match inspector.inspect(icon.png):
        case PictureProblem(reason=reason):
            return [_error("E363", f"the picture is not one this product embeds: {reason}", loc)]
        case (width, height) if (width, height) != (meta.width, meta.height):
            declared = f"{meta.width}×{meta.height}"
            return [_error("E363", f"the picture is {width}×{height}, not the declared {declared}", loc)]
        case _:
            return []


def _applicability_issues(icon: IconFile, known_names: frozenset[str] | None, loc: str) -> list[Issue]:
    if known_names is None:
        return []
    return [
        Issue(Severity.WARNING, "W360", f"applies-to names '{name}', which is no known type or specialization", loc)
        for name in unknown_applicability_names(icon.metadata.applies_to, known_names)
    ]


def _error(code: str, message: str, loc: str) -> Issue:
    return Issue(Severity.ERROR, code, message, loc)
