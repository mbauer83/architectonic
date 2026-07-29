"""Conflict handler classes and resolution helpers for the promotion workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from src.infrastructure.write.artifact_write._promote_file_ops import TargetResolver, rewrite_outgoing
from src.infrastructure.write.artifact_write.parse_existing import parse_entity_file
from src.infrastructure.write.artifact_write.promote_to_enterprise import ConflictResolution


class _ConflictHandler(Protocol):
    def handle(
        self,
        conflict: Any,
        eng_root: Path,
        ent_root: Path,
        registry: Any,
        result: Any,
        backups: Any,
        resolve_target: Any,
        conn_ids: Any,
    ) -> None: ...


class _AcceptEnterpriseHandler:
    def handle(
        self,
        conflict: Any,
        eng_root: Path,
        ent_root: Path,
        registry: Any,
        result: Any,
        backups: Any,
        resolve_target: Any,
        conn_ids: Any,
    ) -> None:
        pass


@dataclass
class _AcceptEngagementHandler:
    def handle(
        self,
        conflict: Any,
        eng_root: Path,
        ent_root: Path,
        registry: Any,
        result: Any,
        backups: Any,
        resolve_target: Any,
        conn_ids: Any,
    ) -> None:
        replace_enterprise_content(conflict, eng_root, ent_root, registry, result, backups, resolve_target, conn_ids)


@dataclass
class _MergeHandler:
    merged_fields: dict[str, Any]

    def handle(
        self,
        conflict: Any,
        eng_root: Path,
        ent_root: Path,
        registry: Any,
        result: Any,
        backups: Any,
        resolve_target: Any,
        conn_ids: Any,
    ) -> None:
        apply_merge(conflict, ent_root, registry, self.merged_fields, result, backups)


def build_handler(resolution: ConflictResolution) -> _ConflictHandler | None:
    match resolution.strategy:
        case "accept_enterprise":
            return _AcceptEnterpriseHandler()
        case "accept_engagement":
            return _AcceptEngagementHandler()
        case "merge" if resolution.merged_fields:
            return _MergeHandler(merged_fields=resolution.merged_fields)
        case _:
            return None


def replace_enterprise_content(
    conflict: Any,
    eng_root: Path,
    ent_root: Path,
    registry: Any,
    result: Any,
    backups: list[Any],
    resolve_target: TargetResolver,
    conn_ids: Any,
) -> None:
    ent_path = registry.find_file_by_id(conflict.enterprise_id)
    eng_path = registry.find_file_by_id(conflict.engagement_id)
    if not ent_path or not eng_path:
        result.plan.warnings.append(f"Could not find files for conflict {conflict.engagement_id}")
        return
    content = eng_path.read_text(encoding="utf-8").replace(conflict.engagement_id, conflict.enterprise_id, 1)
    backups.append((ent_path, ent_path.read_bytes()))
    ent_path.write_text(content, encoding="utf-8")
    result.updated_files.append(str(ent_path.relative_to(ent_root)))
    eng_outgoing = eng_path.with_suffix(".outgoing.md")
    if eng_outgoing.exists():
        ent_outgoing = ent_root / eng_outgoing.relative_to(eng_root)
        backups.append((ent_outgoing, ent_outgoing.read_bytes() if ent_outgoing.exists() else None))
        rewritten = rewrite_outgoing(
            eng_outgoing.read_text(encoding="utf-8"),
            resolve_target=resolve_target,
            result=result,
            conn_ids=conn_ids,
        ).replace(conflict.engagement_id, conflict.enterprise_id, 1)
        ent_outgoing.parent.mkdir(parents=True, exist_ok=True)
        ent_outgoing.write_text(rewritten, encoding="utf-8")
        result.updated_files.append(str(ent_outgoing.relative_to(ent_root)))


def apply_merge(
    conflict: Any,
    ent_root: Path,
    registry: Any,
    merged_fields: dict[str, Any],
    result: Any,
    backups: list[Any],
) -> None:
    from src.application.modeling.artifact_write_formatting import format_entity_markdown
    from src.domain.modules.module_types import EntityTypeName
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.boundary import modification_stamp

    ent_path = registry.find_file_by_id(conflict.enterprise_id)
    if not ent_path:
        result.plan.warnings.append(f"Enterprise file not found for merge: {conflict.enterprise_id}")
        return
    parsed = parse_entity_file(ent_path)
    fm = dict(parsed.frontmatter)
    get_module_registry().get_entity_type(EntityTypeName(conflict.artifact_type))
    content = format_entity_markdown(
        artifact_id=conflict.enterprise_id,
        artifact_type=conflict.artifact_type,
        name=merged_fields.get("name", fm.get("name", "")),
        version=merged_fields.get("version", fm.get("version", "0.1.0")),
        status=merged_fields.get("status", fm.get("status", "draft")),
        last_updated=modification_stamp(),
        keywords=merged_fields.get("keywords", fm.get("keywords")),
        summary=merged_fields.get("summary", parsed.summary),
        properties=merged_fields.get("properties", parsed.properties),
        notes=merged_fields.get("notes", parsed.notes),
        display_section_id=parsed.display_section_id,
        display_content=parsed.display_content,
        repo_root=ent_root,
    )
    backups.append((ent_path, ent_path.read_bytes()))
    ent_path.write_text(content, encoding="utf-8")
    result.updated_files.append(str(ent_path.relative_to(ent_root)))
