"""The scratchpad service and its served shape, composed once for both surfaces.

REST and MCP each built the service and each called `to_response`, with the same three arguments
spelled twice. A fourth — where a note's attribute schema comes from — would have been a third
thing for one of them to forget, and a surface that forgot it would serve notes with nothing to
say about their attributes while the other refused a lift over them. So both ask here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.application.scratchpad.note_attributes import AttributeSchemaSource
from src.application.scratchpad.response import to_response
from src.application.scratchpad.service import ScratchpadService
from src.domain.scratchpad import Scratchpad
from src.infrastructure.scratchpad.bulk_write_lift import BulkWriteLiftWriter
from src.infrastructure.scratchpad.yaml_repository import YamlScratchpadRepository


def repository_attribute_schema(repo_root: Path) -> AttributeSchemaSource:
    """The effective attribute schema an entity of this repository is verified against.

    The same resolution the entity schema endpoint and the verifier use — base type, bound
    profiles, the specialization's own — so a note is told about its attributes what the entity it
    becomes will be told.
    """
    def schema_of(element_type: str, specializations: Sequence[str]) -> Mapping[str, Any] | None:
        from src.application.artifacts.schema import (  # noqa: PLC0415
            compute_effective_attribute_schema,
        )
        from src.infrastructure.app_bootstrap import process_runtime_catalogs  # noqa: PLC0415

        catalogs = process_runtime_catalogs()
        schema, _conflicts = compute_effective_attribute_schema(
            repo_root,
            element_type,
            list(specializations) or [""],
            specialization_catalog=catalogs.specializations,
            profile_registry=catalogs.profiles,
        )
        return schema

    return schema_of


def scratchpad_service(repo_root: Path) -> ScratchpadService:
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

    return ScratchpadService(
        YamlScratchpadRepository(repo_root),
        get_module_registry(),
        BulkWriteLiftWriter(repo_root),
        attribute_schema=repository_attribute_schema(repo_root),
    )


def served(scratchpad: Scratchpad, *, group: str, repo_root: Path) -> dict[str, Any]:
    """The scratchpad as a read serves it, judged against this repository's vocabulary."""
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

    return to_response(
        scratchpad,
        group=group,
        registry=get_module_registry(),
        attribute_schema=repository_attribute_schema(repo_root),
    )
