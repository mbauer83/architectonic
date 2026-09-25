"""Create, edit and delete the shared icons of the repository's library.

An upload is normalised first (`icons.normaliser`), so what is written is always the one stored form;
its `applies-to` names must be types or specializations the product knows; and a picture the library
already holds is not stored twice — the existing icon is named instead, since two icons with one
picture would be two choices that look the same. An edit changes what the icon says about itself and
never its picture (D1). Every file is verified in a temporary location, as every other artifact is,
before it is written.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from src.application.icons.icon_usage import icon_users
from src.application.icons.icon_vocabulary import icon_applicability_names, unknown_applicability_names
from src.application.identifier_allocator import get_default_allocator
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.config.repo_paths import DIAGRAM_CATALOG
from src.domain.icons.applicability import InvalidApplicabilityError, applicability_from
from src.domain.icons.icon_file import IconFile, IconMetadata, IconStatus, format_icon_file, read_icon_file
from src.domain.icons.icon_record import IconRecord
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


def upload_from_base64(
    content_base64: str,
    *,
    source_format: SourceFormat,
    name: str,
    attribution: str,
    applies_to: Sequence[str] = (),
    default_style: IconStyle = "badge",
    tags: Sequence[str] = (),
) -> IconUpload | IconRefused:
    """An upload as the surfaces receive it — the file base64-encoded — or why it cannot be one."""
    try:
        content = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError):
        return IconRefused("content_base64 is not base64")
    return IconUpload(content, source_format, name, attribution, tuple(applies_to), default_style, tuple(tags))


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
            return refused_icon_write(path, artifact_id, reason)
        case NormalisedIcon() as normalised:
            pass
    if (existing := _library_icon_with_digest(repo_root, normalised.digest)) is not None:
        held = f"the library already holds this picture as {existing}; use that icon"
        return refused_icon_write(path, artifact_id, held)
    icon = IconFile(_metadata(artifact_id, upload, normalised), normalised.png, normalised.svg_source)
    return _verified_write(
        path, artifact_id, format_icon_file(icon), list(normalised.notes),
        repo_root=repo_root, verifier=verifier, clear_repo_caches=clear_repo_caches, dry_run=dry_run,
    )


def edit_icon(
    *,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    artifact_id: str,
    name: str | None = None,
    attribution: str | None = None,
    applies_to: Sequence[str] | None = None,
    default_style: IconStyle | None = None,
    tags: Sequence[str] | None = None,
    status: IconStatus | None = None,
    dry_run: bool,
) -> WriteResult:
    """Change what an engagement library icon says about itself; an argument left None keeps its value.

    Retiring (`status="retired"`) stops the icon being offered while every diagram showing it still does.
    """
    assert_engagement_write_root(repo_root)
    record = library_icon_here(repo_root, artifact_id)
    icon = read_icon_file(record.path.read_text(encoding="utf-8"))
    if not isinstance(icon, IconFile):
        return refused_icon_write(record.path, record.artifact_id, f"the icon file cannot be read: {icon.reason}")
    meta = icon.metadata
    eff_name = (name if name is not None else meta.name).strip()
    eff_attribution = (attribution if attribution is not None else meta.attribution).strip()
    eff_applies_to = applies_to if applies_to is not None else meta.applies_to.as_list()
    if (refused := _metadata_refusal(eff_name, eff_attribution, eff_applies_to, verifier)) is not None:
        return refused_icon_write(record.path, record.artifact_id, refused.reason)
    edited = replace(
        meta,
        name=eff_name,
        attribution=eff_attribution,
        applies_to=applicability_from(eff_applies_to),
        default_style=default_style or meta.default_style,
        tags=_tags(tags) if tags is not None else meta.tags,
        status=status or meta.status,
        last_updated=modification_stamp(),
    )
    return _verified_write(
        record.path, record.artifact_id, format_icon_file(replace(icon, metadata=edited)), [],
        repo_root=repo_root, verifier=verifier, clear_repo_caches=clear_repo_caches, dry_run=dry_run,
    )


def library_icon_here(repo_root: Path, artifact_id: str) -> IconRecord:
    """The icon *artifact_id* names in this repository's own library; an enterprise icon is not editable here."""
    icon = get_repository(repo_root).get_icon(artifact_id)
    if icon is None or not icon.path.is_relative_to(repo_root):
        raise FileNotFoundError(f"Icon '{artifact_id}' is not in this repository's library")
    return icon


def _stored_form(upload: IconUpload, repo_root: Path, verifier: ArtifactVerifier) -> NormalisedIcon | IconRefused:
    refused = _metadata_refusal(upload.name.strip(), upload.attribution.strip(), upload.applies_to, verifier)
    return refused or normalise_upload(upload.content, upload.source_format)


def _metadata_refusal(
    name: str, attribution: str, applies_to: Sequence[str], verifier: ArtifactVerifier
) -> IconRefused | None:
    if not name:
        return IconRefused("an icon needs a name")
    if not attribution:
        return IconRefused("an icon needs an attribution: whose mark it is, and on what terms it is used")
    try:
        applicability = applicability_from(applies_to)
    except InvalidApplicabilityError as exc:
        return IconRefused(str(exc))
    unknown = unknown_applicability_names(applicability, icon_applicability_names(verifier.runtime_catalogs))
    if unknown:
        return IconRefused(f"applies-to names no known type or specialization: {', '.join(unknown)}")
    return None


def _verified_write(
    path: Path,
    artifact_id: str,
    content: str,
    notes: list[str],
    *,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    dry_run: bool,
) -> WriteResult:
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
    return WriteResult(written, path, artifact_id, None if written else content, notes, verification)


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
        tags=_tags(upload.tags),
        status="active",
        last_updated=modification_stamp(),
    )


def _tags(tags: Sequence[str]) -> tuple[str, ...]:
    return tuple(tag.strip() for tag in tags if tag.strip())


def refused_icon_write(path: Path, artifact_id: str, reason: str) -> WriteResult:
    """An icon write that did not happen, with the reason as its one error."""
    issue = {"severity": "error", "code": "icon_refused", "message": reason, "location": None}
    return WriteResult(False, path, artifact_id, None, [], {"valid": False, "issues": [issue]})


class IconInUseError(ValueError):
    """A library icon something still shows, named with its users so they can be re-pointed first."""


def delete_icon(
    *,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    artifact_id: str,
    dry_run: bool,
) -> WriteResult:
    """Delete an engagement library icon nothing uses; refuse, naming the users, while anything does.

    Retiring (`status: retired`) is the way to stop offering an icon that is still shown.
    """
    assert_engagement_write_root(repo_root)
    icon = library_icon_here(repo_root, artifact_id)
    users = icon_users(
        icon.artifact_id, get_repository(repo_root).list_diagrams(), verifier.runtime_catalogs.specializations
    )
    if not users.is_empty:
        raise IconInUseError(f"{icon.artifact_id} is still used by {users.described()}; re-point or clear them first")
    if not dry_run:
        icon.path.unlink()
        clear_repo_caches(icon.path)
    return WriteResult(not dry_run, icon.path, icon.artifact_id, None, [], {"valid": True, "issues": []})
