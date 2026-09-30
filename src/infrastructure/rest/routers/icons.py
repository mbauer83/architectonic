"""The icon library: list what a picker offers, add, edit, replace and delete an icon, serve its picture."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from src.application.icons.icon_rows import icon_fields, usage_fields
from src.application.icons.icon_usage import LibraryUsage, library_usage
from src.application.icons.library_query import offered_icons
from src.application.icons.shown_icons import EditedInstance, shown_icons
from src.application.modeling.proposal_standing import standing_subject
from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.artifact_id import stable_id
from src.domain.baseline_standing import BASELINE_STANDING, BaselineStanding
from src.domain.embedded_image import embedded_png_url
from src.domain.icons.icon_file import IconFile, read_icon_file
from src.domain.icons.icon_record import IconRecord
from src.domain.icons.normalised_icon import IconRefused
from src.infrastructure.rest.contracts.icons import IconListResponse, IconSummary, ShownIconsResponse
from src.infrastructure.rest.dependencies import runtime_catalogs_dependency
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._failures import rejected_input
from src.infrastructure.rest.routers._openapi import (
    READ_RESPONSES,
    TAG_ICONS,
    WRITE_RESPONSES,
    WriteResultResponse,
    media_response,
)

router = APIRouter()

#: A 1 MB upload, base64-encoded, with room for padding: the normaliser refuses anything larger anyway.
_MAX_ENCODED_CHARS = 1_400_000


class CreateIconRequest(BaseModel):
    name: str
    attribution: str
    content_base64: str = Field(max_length=_MAX_ENCODED_CHARS)
    source_format: Literal["svg", "png", "jpeg", "webp"]
    applies_to: list[str] = Field(default_factory=list)
    default_style: Literal["badge", "figure"] = "badge"
    tags: list[str] = Field(default_factory=list)
    dry_run: bool = True


@router.get("/api/icons", tags=[TAG_ICONS], summary="List the icons a picker offers", response_model=IconListResponse)
def list_icons(
    applicable_to: str | None = Query(default=None, description="An entity id, or a type or specialization name"),
    tag: str | None = None,
    q: str | None = Query(default=None, description="Matched against name and attribution"),
    include_retired: bool = False,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    repo = s.get_repo()
    offered = offered_icons(
        repo.list_icons(), applicable_to=applicable_to, tag=tag, text=q,
        include_retired=include_retired, entity_of=repo.get_entity,
    )
    standing_of = s.baseline_standing_reader()
    usage = _usage(catalogs)
    shown_for = usage.shown_for(applicable_to) if applicable_to else frozenset()
    items = [
        {**_summary(icon, standing_of, usage), "shown_for_element": stable_id(icon.artifact_id) in shown_for}
        for icon in offered
    ]
    return {"total": len(items), "items": items}


class EditedInstanceBody(BaseModel):
    instance_id: str
    #: The entity it draws, where that is not the instance id itself (an occurrence).
    entity_id: str | None = None
    #: The type the diagram draws it as, where the notation has types of its own (a C4 container).
    drawn_as: str | None = None


class PreviewShownIconsRequest(BaseModel):
    #: The diagram's `diagram-entities` as the editor holds it, uploads not yet saved included.
    diagram_entities: dict[str, Any] = Field(default_factory=dict)
    instances: list[EditedInstanceBody]


@router.post("/api/icons/preview", tags=[TAG_ICONS], summary="Which icon each instance of a diagram shows",
    response_model=ShownIconsResponse, responses=READ_RESPONSES)
def preview_shown_icons(
    req: PreviewShownIconsRequest, catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency)
) -> dict[str, Any]:
    from src.infrastructure.icons.diagram_icons import DiagramIconSource, prepared_local_icons  # noqa: PLC0415
    from src.infrastructure.icons.library_source import LibraryIconSource  # noqa: PLC0415

    match prepared_local_icons(req.diagram_entities):
        case IconRefused(reason=reason):
            raise rejected_input(reason, field="diagram_entities")
        case dict() as entities:
            pass
    repo = s.get_repo()
    instances = [EditedInstance(i.instance_id, i.entity_id, i.drawn_as) for i in req.instances]
    source = DiagramIconSource(entities, LibraryIconSource(repo))
    shown = shown_icons(entities, instances, repo.get_entity, source, catalogs.specializations)
    return {
        "icons": {
            instance_id: {
                "icon": icon.target.spelled(), "style": icon.style, "level": icon.level,
                "picture": icon.icon.render_digest,
            }
            for instance_id, icon in shown.items()
        },
        "pictures": {icon.icon.render_digest: embedded_png_url(icon.icon.png) for icon in shown.values()},
    }


@router.get("/api/icons/{artifact_id}", tags=[TAG_ICONS], summary="Read an icon by id",
    response_model=IconSummary, responses=READ_RESPONSES)
def read_icon(
    artifact_id: str, catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency)
) -> dict[str, Any]:
    return _summary(_icon(artifact_id), s.baseline_standing_reader(), _usage(catalogs))


@router.get("/api/icons/{artifact_id}/image", tags=[TAG_ICONS], summary="Serve an icon's picture",
    response_class=Response, responses={**READ_RESPONSES, **media_response("image/png", "The icon's stored picture")})
def read_icon_image(artifact_id: str) -> Response:
    record = _icon(artifact_id)
    match read_icon_file(record.path.read_text(encoding="utf-8")):
        case IconFile(png=png):
            return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=31536000"})
        case _:
            raise HTTPException(422, f"{artifact_id} is not a readable icon file; the verifier says why")


_CREATE_RESPONSES: dict[int | str, Any] = {
    **WRITE_RESPONSES,
    200: {"model": WriteResultResponse, "description": "Dry run or refusal; nothing was created"},
}


@router.post("/api/icons", tags=[TAG_ICONS], summary="Add an icon to the library",
    response_model=WriteResultResponse, responses=_CREATE_RESPONSES, status_code=status.HTTP_201_CREATED)
def create_icon(
    req: CreateIconRequest, response: Response, catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency)
) -> dict[str, Any]:
    from src.infrastructure.write.artifact_write.icon import create_icon as _create  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.icon import upload_from_base64  # noqa: PLC0415

    upload = upload_from_base64(
        req.content_base64, source_format=req.source_format, name=req.name, attribution=req.attribution,
        applies_to=req.applies_to, default_style=req.default_style, tags=req.tags,
    )
    if isinstance(upload, IconRefused):
        raise rejected_input(upload.reason, field="content_base64")
    repo_root, _registry, verifier = s.get_write_deps(catalogs)
    result = s.authorized_write(
        "icons_create_icon", _create, repo_root=repo_root, verifier=verifier,
        clear_repo_caches=s.clear_caches, upload=upload, dry_run=req.dry_run,
    )
    if result.wrote:
        response.headers["Location"] = f"/api/icons/{result.artifact_id}"
    else:
        response.status_code = status.HTTP_200_OK
    return s.write_result_to_dict(result)


class UpdateIconRequest(BaseModel):
    """What an icon says about itself; a field left out keeps its value. The picture is not editable."""

    name: str | None = None
    attribution: str | None = None
    applies_to: list[str] | None = None
    default_style: Literal["badge", "figure"] | None = None
    tags: list[str] | None = None
    status: Literal["active", "retired"] | None = None
    dry_run: bool = True


@router.patch("/api/icons/{artifact_id}", tags=[TAG_ICONS], summary="Edit an icon's name, attribution and use",
    response_model=WriteResultResponse, responses=WRITE_RESPONSES)
def update_icon(
    artifact_id: str, req: UpdateIconRequest, catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency)
) -> dict[str, Any]:
    from src.infrastructure.write.artifact_write.icon import edit_icon  # noqa: PLC0415

    repo_root, _registry, verifier = s.get_write_deps(catalogs)
    try:
        result = s.authorized_write(
            "icons_update_icon", edit_icon, repo_root=repo_root, verifier=verifier,
            clear_repo_caches=s.clear_caches, artifact_id=artifact_id, name=req.name,
            attribution=req.attribution, applies_to=req.applies_to, default_style=req.default_style,
            tags=req.tags, status=req.status, dry_run=req.dry_run,
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return s.write_result_to_dict(result)


class ReplaceIconRequest(BaseModel):
    #: An icon already in this library or the enterprise's; upload a new version first.
    replacement_id: str
    dry_run: bool = True


@router.post("/api/icons/{artifact_id}/replace", tags=[TAG_ICONS],
    summary="Re-point every diagram showing an icon at another, then delete it",
    response_model=WriteResultResponse, responses=WRITE_RESPONSES)
def replace_icon(
    artifact_id: str, req: ReplaceIconRequest, catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency)
) -> dict[str, Any]:
    from src.infrastructure.write.artifact_write.icon import IconInUseError  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.icon_replace import replace_icon as _replace  # noqa: PLC0415

    repo_root, _registry, verifier = s.get_write_deps(catalogs)
    try:
        result = s.authorized_write(
            "icons_replace_icon", _replace, repo_root=repo_root, verifier=verifier,
            clear_repo_caches=s.clear_caches, artifact_id=artifact_id, replacement_id=req.replacement_id,
            dry_run=req.dry_run,
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except IconInUseError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return s.write_result_to_dict(result)


class ShareIconRequest(BaseModel):
    #: Whose mark it is, and on what terms it is used; the library requires it.
    attribution: str
    tags: list[str] = Field(default_factory=list)
    dry_run: bool = True


@router.post("/api/diagrams/{artifact_id}/icons/{icon_key}/share", tags=[TAG_ICONS],
    summary="Move an icon a diagram holds for itself into the library",
    response_model=WriteResultResponse, responses=WRITE_RESPONSES)
def share_diagram_icon(
    artifact_id: str, icon_key: str, req: ShareIconRequest,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    from src.infrastructure.write.artifact_write.icon_share import share_icon  # noqa: PLC0415

    repo_root, _registry, verifier = s.get_write_deps(catalogs)
    try:
        result = s.authorized_write(
            "icons_share_diagram_icon", share_icon, repo_root=repo_root, verifier=verifier,
            clear_repo_caches=s.clear_caches, diagram_id=artifact_id, icon_key=icon_key,
            attribution=req.attribution, tags=req.tags, dry_run=req.dry_run,
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return s.write_result_to_dict(result)


_DELETE_RESPONSES: dict[int | str, Any] = {
    **WRITE_RESPONSES,
    200: {"model": WriteResultResponse, "description": "Dry-run plan; nothing was deleted"},
}


@router.delete("/api/icons/{artifact_id}", tags=[TAG_ICONS], summary="Delete an icon nothing uses",
    response_model=None, responses=_DELETE_RESPONSES, status_code=status.HTTP_204_NO_CONTENT)
def delete_icon(
    artifact_id: str, response: Response, dry_run: bool = True,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any] | None:
    from src.infrastructure.write.artifact_write.icon import IconInUseError  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.icon import delete_icon as _delete  # noqa: PLC0415

    repo_root, _registry, verifier = s.get_write_deps(catalogs)
    try:
        result = s.authorized_write(
            "icons_delete_icon", _delete, repo_root=repo_root, verifier=verifier,
            clear_repo_caches=s.clear_caches, artifact_id=artifact_id, dry_run=dry_run,
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except IconInUseError as exc:
        raise HTTPException(409, str(exc)) from exc
    if dry_run:
        response.status_code = status.HTTP_200_OK
        return s.write_result_to_dict(result)
    return None


def _icon(artifact_id: str) -> IconRecord:
    icon = s.get_repo().get_icon(artifact_id)
    if icon is None:
        raise HTTPException(404, f"Not found: {artifact_id!r}")
    return icon


def _usage(catalogs: RuntimeCatalogs) -> LibraryUsage:
    return library_usage(s.get_repo().list_diagrams(), catalogs.specializations)


def _summary(icon: IconRecord, standing_of: Callable[[str], BaselineStanding], usage: LibraryUsage) -> dict[str, Any]:
    return {
        **icon_fields(icon),
        **usage_fields(usage.users_of(icon.artifact_id)),
        "is_global": s.is_global(icon.path),
        BASELINE_STANDING: standing_of(standing_subject(icon)).to_mapping(),
    }
