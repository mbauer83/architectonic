"""W044 — orphan specialization-attachment schema file.

Registered into `_GENERIC_REPOSITORY_CONTRIBUTIONS` on import (same mechanism as the E335
workspace-id-uniqueness check in `_workspace_identity_rules.py`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class OrphanAttachmentSchemaContribution:
    """W044: `attributes.{artifact_type}.{slug}.schema.json` whose `slug` is not declared as
    a specialization of `artifact_type` in the repo's catalog."""

    diagnostic_codes: tuple[str, ...] = ("W044",)

    def run(self, ctx: Any, result: Any) -> None:
        if ctx.catalogs is None:
            return
        from src.application.artifact_schema import find_orphan_attachment_schemata  # noqa: PLC0415
        from src.application.verification.artifact_verifier_types import Issue, Severity  # noqa: PLC0415

        specialization_catalog = getattr(ctx.catalogs, "specializations", None)
        if specialization_catalog is None:
            return
        for filename in find_orphan_attachment_schemata(Path(ctx.location), specialization_catalog):
            result.issues.append(
                Issue(
                    Severity.WARNING,
                    "W044",
                    f"Attachment schema '{filename}' has no matching declared specialization",
                    ctx.location,
                )
            )


_W044_SINGLETON = OrphanAttachmentSchemaContribution()

from src.domain.diagrams.diagram_verification import _GENERIC_REPOSITORY_CONTRIBUTIONS  # noqa: E402

if not any(isinstance(c, OrphanAttachmentSchemaContribution) for c in _GENERIC_REPOSITORY_CONTRIBUTIONS):
    _GENERIC_REPOSITORY_CONTRIBUTIONS.append(_W044_SINGLETON)
