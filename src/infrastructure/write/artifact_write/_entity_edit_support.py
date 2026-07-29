"""Pure helpers for :func:`entity_edit.edit_entity`.

Holds the partial-update sentinel, the merged-field value object, and the
rename-impact counter — all free of write side effects so they stay easy to test
and reason about.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.application.repo_path_helpers import all_model_roots

from .boundary import normalize_specializations
from .coerce import as_optional_str, as_optional_str_dict, as_optional_str_list, as_optional_typed_dict
from .parse_existing import ParsedEntity

# Sentinel to distinguish "not provided" from explicit None. Re-exported by
# entity_edit so existing callers keep importing it from there.
_UNSET = object()


def _fm_specializations(value: object) -> tuple[str, ...]:
    """The current applied set from a frontmatter ``specialization`` value (scalar, list, or
    absent) — the read mirror of what the writer serialises."""
    if isinstance(value, list):
        return normalize_specializations(None, [str(v) for v in value])
    return normalize_specializations(str(value) if isinstance(value, str) else None, None)


def _merge_specializations(current: object, specialization: object, specializations: object) -> tuple[str, ...]:
    """The post-edit applied set. An explicit update (either the scalar ``specialization`` or
    the list ``specializations``) REPLACES the current set; ``_UNSET`` on both keeps it.
    Passing ``""``/``[]`` clears it, exactly as the single-value edit already cleared one."""
    if specializations is not _UNSET:
        raw = specializations if isinstance(specializations, list) else []
        return normalize_specializations(None, [str(v) for v in raw])
    if specialization is not _UNSET:
        scalar = str(specialization) if isinstance(specialization, str) else None
        return normalize_specializations(scalar, None)
    return _fm_specializations(current)


@dataclass(frozen=True)
class MergedFields:
    """An entity's editable fields after merging partial updates with current values."""

    name: str
    version: str
    status: str
    keywords: list[str] | None
    specializations: tuple[str, ...]
    summary: str | None
    properties: dict[str, Any] | None
    attribute_types: dict[str, str] | None
    notes: str | None


def patch_map(
    existing: Mapping[str, object] | None,
    incoming: object,
) -> dict[str, object] | None:
    """Apply an incoming attribute map over what the entity already declares.

    A patch, not a replacement. The tool contract is "pass only what changes", and honouring that at
    the top level while replacing wholesale one level down is the trap it reads as being protected
    from: setting one attribute silently dropped every other, and a caller had to read the entity
    first and resend values it had no intention of touching.

    A key mapped to `None` removes that attribute, which is the only way a patch can express deletion
    — and is why removal has to be asked for explicitly rather than implied by absence.
    """
    if incoming is None or not isinstance(incoming, dict):
        return dict(existing) if existing else None
    merged = {str(key): value for key, value in (existing or {}).items()}
    for key, value in incoming.items():
        if value is None:
            merged.pop(str(key), None)
        else:
            merged[str(key)] = value
    return merged or None


def merge_fields(
    parsed: ParsedEntity,
    *,
    name: str | None,
    version: str | None,
    status: str | None,
    keywords: object,
    specialization: object = _UNSET,
    specializations: object = _UNSET,
    summary: object,
    properties: object,
    attribute_types: object,
    notes: object,
) -> MergedFields:
    """Merge provided fields over the parsed entity; ``_UNSET``/``None`` keep current values.

    `properties` and `attribute_types` are patched key by key rather than replaced, so a caller
    setting one attribute does not have to resend the others to keep them. Mapping a key to
    `None` removes it.
    """
    fm = parsed.frontmatter
    return MergedFields(
        name=name if name is not None else str(fm.get("name", "")),
        version=version if version is not None else str(fm.get("version", "0.1.0")),
        status=status if status is not None else str(fm.get("status", "draft")),
        keywords=as_optional_str_list(keywords if keywords is not _UNSET else fm.get("keywords")),
        specializations=_merge_specializations(fm.get("specialization"), specialization, specializations),
        summary=as_optional_str(summary) if summary is not _UNSET else parsed.summary,
        properties=(
            patch_map(parsed.properties, as_optional_typed_dict(properties))
            if properties is not _UNSET
            else (parsed.properties or None)
        ),
        attribute_types=(
            as_optional_str_dict(patch_map(
                as_optional_str_dict(fm.get("attribute-types")), attribute_types,
            ))
            if attribute_types is not _UNSET
            else as_optional_str_dict(fm.get("attribute-types"))
        ),
        notes=as_optional_str(notes) if notes is not _UNSET else parsed.notes,
    )


def count_rename_referrers(repo_root: Path, artifact_id: str, own_outgoing: Path) -> int:
    """Count outgoing files a rename would rewrite: the entity's own file plus any referrers."""
    impacted = 1 if own_outgoing.exists() else 0
    for model_root in all_model_roots(repo_root):
        for outgoing_path in model_root.rglob("*.outgoing.md"):
            if outgoing_path == own_outgoing:
                continue
            try:
                if artifact_id in outgoing_path.read_text(encoding="utf-8"):
                    impacted += 1
            except OSError:
                continue
    return impacted
