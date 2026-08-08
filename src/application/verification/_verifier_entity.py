"""Verification logic for entity files.

The last rule body to leave the facade, which now dispatches and holds none: entities, connections,
diagrams, matrices, documents and outgoing files each verify in a module of their own.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from src.application.entity_type_predicates import is_internal_entity_type
from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.verification._verifier_rules_grf import check_global_artifact_reference
from src.application.verification._verifier_rules_schema import (
    check_attribute_schema,
    check_frontmatter_schema,
    check_module_source_path,
)
from src.application.verification._verifier_rules_specialization import check_entity_specialization
from src.application.verification.artifact_verifier_parsing import parse_frontmatter, read_file
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.verification.artifact_verifier_rules import (
    check_artifact_id_entity,
    check_artifact_type,
    check_enum,
    check_required_fields,
    check_section,
)
from src.application.verification.artifact_verifier_types import (
    ENTITY_REQUIRED,
    VALID_STATUSES,
    VerificationResult,
)

if TYPE_CHECKING:
    from src.application.verification._verifier_snapshot import RepositorySnapshot


def verify_entity(
    path: Path,
    *,
    registry: ArtifactRegistry | None,
    catalogs: RuntimeCatalogs,
    repo_root: Path | None,
    snapshot: RepositorySnapshot | None = None,
) -> VerificationResult:
    """Verify an entity file.

    ``repo_root`` is the *governing* repository, whose ``.arch-repo/schemata`` the schema rules key
    off — which is not always the file's own location, since proposed content is verified in a temp
    path against the repository that would receive it.
    """
    result = VerificationResult(path=path, file_type="entity")
    loc = str(path)
    content = read_file(path, result, loc, snapshot=snapshot)
    if content is None:
        return result
    fm = parse_frontmatter(content, result, loc)
    if fm is None:
        return result

    check_required_fields(fm, ENTITY_REQUIRED, result, loc)
    check_artifact_id_entity(fm, result, loc)
    check_artifact_type(fm, catalogs.ontology.all_entity_type_names(), "entity type", result, loc)
    check_entity_specialization(fm, catalogs.specializations, result, loc)
    check_enum(fm, "status", VALID_STATUSES, result, loc)
    check_section(content, "§content", required=True, result=result, loc=loc)
    check_section(content, "§display", required=True, result=result, loc=loc)

    if is_internal_entity_type(str(fm.get("artifact-type", "")), catalogs.ontology):
        check_global_artifact_reference(fm, registry, result, loc)

    if repo_root is not None:
        check_frontmatter_schema(fm, repo_root, "entity", result, loc)
        check_attribute_schema(
            content,
            fm,
            repo_root,
            result,
            loc,
            specialization_catalog=catalogs.specializations,
            profile_registry=catalogs.profiles,
        )

    check_module_source_path(content, path, result, loc)
    return result
