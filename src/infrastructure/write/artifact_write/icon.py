"""Create a shared icon in the repository's library from an upload.

The upload is normalised first (`icons.normaliser`), so what is written is always the one stored form;
its `applies-to` names must be types or specializations the product knows; and a picture the library
already holds is not stored twice — the existing icon is named instead, since two icons with one
picture would be two choices that look the same. The file is verified in a temporary location, as
every other artifact is, before it is written.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.application.icons.icon_vocabulary import icon_applicability_names, unknown_applicability_names
from src.application.identifier_allocator import get_default_allocator
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.config.repo_paths import DIAGRAM_CATALOG
from src.domain.icons.applicability import InvalidApplicabilityError, applicability_from
from src.domain.icons.icon_file import IconFile, IconMetadata, format_icon_file
from src.domain.icons.icon_ref import ICON_ID_PREFIX, IconStyle
from src.domain.icons.normalised_icon import IconRefused, NormalisedIcon
from src.domain.icons.render_form import SourceFormat
from src.domain.repository.repo_layout import ICONS
from src.infrastructure.atomic_file import write_atomic
from src.infrastructure.icons.normaliser import normalise_upload

from ._artifact_deduplication import get_repository
from .boundary import assert_engagement_write_root, modification_stamp
from .types import WriteResult
from .verify import verify_content_in_temp_path


@dataclass(frozen=True, slots=True)
class IconUpload:
    content: bytes
    source_format: SourceFormat
    name: str
    #: Whose mark it is and on what terms it is used; required, as vendor logos are trademarks.
    attribution: str
    applies_to: Sequence[str] = ()
    default_style: IconStyle = "badge"
    tags: Sequence[str] = ()


def create_icon(
    *,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    upload: IconUpload,
    dry_run: bool,
) -> WriteResult:
    assert_engagement_write_root(repo_root)
    artifact_id = get_default_allocator().allocate(prefix=ICON_ID_PREFIX, name_hint=upload.name)
    path = repo_root / DIAGRAM_CATALOG / ICONS / f"{artifact_id}.md"
    match _stored_form(upload, repo_root, verifier):
        case IconRefused(reason=reason):
            return _refused(path, artifact_id, reason)
        case NormalisedIcon() as normalised:
            pass
    if (existing := _library_icon_with_digest(repo_root, normalised.digest)) is not None:
        return _refused(path, artifact_id, f"the library already holds this picture as {existing}; use that icon")
    icon = IconFile(_metadata(artifact_id, upload, normalised), normalised.png, normalised.svg_source)
    content = format_icon_file(icon)
    preview = verify_content_in_temp_path(
        verifier=verifier, file_type="icon", desired_name=path.name, content=content, support_repo_root=repo_root
    )
    verification = {"path": str(path), "file_type": "icon", "valid": preview.valid, "issues": [
        {"severity": i.severity, "code": i.code, "message": i.message, "location": str(path)} for i in preview.issues
    ]}
    written = not dry_run and preview.valid
    if written:
        write_atomic(path, content)
        clear_repo_caches(path)
    return WriteResult(written, path, artifact_id, None if written else content, list(normalised.notes), verification)


def _stored_form(upload: IconUpload, repo_root: Path, verifier: ArtifactVerifier) -> NormalisedIcon | IconRefused:
    if not upload.name.strip():
        return IconRefused("an icon needs a name")
    if not upload.attribution.strip():
        return IconRefused("an icon needs an attribution: whose mark it is, and on what terms it is used")
    try:
        applies_to = applicability_from(upload.applies_to)
    except InvalidApplicabilityError as exc:
        return IconRefused(str(exc))
    unknown = unknown_applicability_names(applies_to, icon_applicability_names(verifier.runtime_catalogs))
    if unknown:
        return IconRefused(f"applies-to names no known type or specialization: {', '.join(unknown)}")
    return normalise_upload(upload.content, upload.source_format)


def _library_icon_with_digest(repo_root: Path, digest: str) -> str | None:
    library = get_repository(repo_root).list_icons()
    return next((icon.artifact_id for icon in library if icon.metadata.render_digest == digest), None)


def _metadata(artifact_id: str, upload: IconUpload, normalised: NormalisedIcon) -> IconMetadata:
    return IconMetadata(
        artifact_id=artifact_id,
        name=upload.name.strip(),
        source_format=normalised.source_format,
        width=normalised.width,
        height=normalised.height,
        render_digest=normalised.digest,
        attribution=upload.attribution.strip(),
        applies_to=applicability_from(upload.applies_to),
        default_style=upload.default_style,
        tags=tuple(tag.strip() for tag in upload.tags if tag.strip()),
        status="active",
        last_updated=modification_stamp(),
    )


def _refused(path: Path, artifact_id: str, reason: str) -> WriteResult:
    issue = {"severity": "error", "code": "icon_refused", "message": reason, "location": None}
    return WriteResult(False, path, artifact_id, None, [], {"valid": False, "issues": [issue]})
