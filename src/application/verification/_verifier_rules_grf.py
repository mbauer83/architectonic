"""Global-artifact-reference verifier rules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.domain.artifact_id import stable_id

if TYPE_CHECKING:
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry

_GAR_TYPE = "global-artifact-reference"
_GAR_ID_KEY = "global-artifact-id"
_GAR_TYPE_KEY = "global-artifact-type"


def check_global_artifact_reference(
    fm: dict,
    registry: "ArtifactRegistry | None",
    result: VerificationResult,
    loc: str,
) -> None:
    """Validate a global-artifact-reference entity.

    E140: global-artifact-id missing or empty.
    E142: global-artifact-type missing or empty.
    E141: referenced enterprise entity does not exist (artifact_type=entity).
    E143: referenced enterprise document does not exist (artifact_type=document).
    E144: referenced enterprise diagram does not exist (artifact_type=diagram).
    W141/W143/W144: cannot verify because enterprise repo is not loaded.
    """
    global_id = fm.get(_GAR_ID_KEY)
    if not global_id:
        result.issues.append(
            Issue(
                Severity.ERROR,
                "E140",
                f"global-artifact-reference is missing required '{_GAR_ID_KEY}' field",
                loc,
            )
        )
        return

    artifact_type = fm.get(_GAR_TYPE_KEY)
    if not artifact_type:
        result.issues.append(
            Issue(
                Severity.ERROR,
                "E142",
                f"global-artifact-reference is missing required '{_GAR_TYPE_KEY}' field",
                loc,
            )
        )
        return

    if registry is None:
        result.issues.append(
            Issue(
                Severity.WARNING,
                "W141",
                f"Cannot verify global-artifact-id '{global_id}': enterprise repo not loaded",
                loc,
            )
        )
        return

    global_short = stable_id(global_id)
    if artifact_type == "entity":
        enterprise_ids = registry.enterprise_entity_ids()
        if not enterprise_ids:
            result.issues.append(
                Issue(
                    Severity.WARNING,
                    "W141",
                    (f"Cannot verify global-artifact-id '{global_id}': no enterprise entities in registry"),
                    loc,
                )
            )
            return
        if global_short not in {stable_id(e) for e in enterprise_ids}:
            result.issues.append(
                Issue(
                    Severity.ERROR,
                    "E141",
                    f"global-artifact-id '{global_id}' does not exist in the enterprise repository",
                    loc,
                )
            )
    elif artifact_type == "document":
        enterprise_ids = registry.enterprise_document_ids()
        if not enterprise_ids:
            result.issues.append(
                Issue(
                    Severity.WARNING,
                    "W143",
                    (f"Cannot verify global-artifact-id '{global_id}': no enterprise documents in registry"),
                    loc,
                )
            )
            return
        if global_short not in {stable_id(e) for e in enterprise_ids}:
            result.issues.append(
                Issue(
                    Severity.ERROR,
                    "E143",
                    (f"global-artifact-id '{global_id}' does not exist in the enterprise repository (document)"),
                    loc,
                )
            )
    elif artifact_type == "diagram":
        enterprise_ids = registry.enterprise_diagram_ids()
        if not enterprise_ids:
            result.issues.append(
                Issue(
                    Severity.WARNING,
                    "W144",
                    (f"Cannot verify global-artifact-id '{global_id}': no enterprise diagrams in registry"),
                    loc,
                )
            )
            return
        if global_short not in {stable_id(e) for e in enterprise_ids}:
            result.issues.append(
                Issue(
                    Severity.ERROR,
                    "E144",
                    (f"global-artifact-id '{global_id}' does not exist in the enterprise repository (diagram)"),
                    loc,
                )
            )
