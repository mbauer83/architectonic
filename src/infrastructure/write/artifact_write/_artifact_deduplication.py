"""Cross-repo artifact deduplication checks."""

from pathlib import Path

from src.application.artifacts.repository import ArtifactRepository
from src.application.identifier_allocator import get_default_allocator
from src.domain.artifact_id import stable_id
from src.domain.ontology_representation.artifact_types import DiagramRecord, DocumentRecord, EntityRecord


def _is_self(artifact_id: str, exclude_artifact_id: str | None) -> bool:
    """True when ``artifact_id`` denotes the same artifact as ``exclude_artifact_id``.

    Compared on the stable short id so a slug difference (e.g. an in-flight rename
    or a short-form exclude id) never defeats self-exclusion (WS6 canonical identity).
    """
    return exclude_artifact_id is not None and stable_id(artifact_id) == stable_id(exclude_artifact_id)


def extract_friendly_slug(artifact_id: str) -> str:
    """Extract friendly slug from artifact ID (format: TYPE@epoch.random.slug)."""
    parts = artifact_id.split(".")
    return parts[-1] if len(parts) > 0 else artifact_id


def extract_random_part(artifact_id: str) -> str:
    """Extract random part from artifact ID (format: TYPE@epoch.random.slug)."""
    parts = artifact_id.split(".")
    return parts[1] if len(parts) > 1 else ""


def get_repository(repo_root: Path) -> ArtifactRepository:
    """Get or create an ArtifactRepository for the given repo root."""
    from src.infrastructure.artifact_index import shared_artifact_index

    return ArtifactRepository(shared_artifact_index([repo_root]))


def check_entity_duplicate(
    repo: ArtifactRepository,
    artifact_type: str,
    friendly_slug: str,
    exclude_artifact_id: str | None = None,
) -> EntityRecord | None:
    """Check if entity with same type + slug exists. Returns the duplicate or None."""
    entities = repo.list_entities(artifact_type=artifact_type)
    for entity in entities:
        if _is_self(entity.artifact_id, exclude_artifact_id):
            continue
        if extract_friendly_slug(entity.artifact_id) == friendly_slug:
            return entity
    return None


def check_diagram_duplicate(
    repo: ArtifactRepository,
    diagram_type: str,
    friendly_slug: str,
    exclude_artifact_id: str | None = None,
) -> DiagramRecord | None:
    """Check if diagram with same type + slug exists. Returns the duplicate or None."""
    diagrams = repo.list_diagrams(diagram_type=diagram_type)
    for diagram in diagrams:
        if _is_self(diagram.artifact_id, exclude_artifact_id):
            continue
        if extract_friendly_slug(diagram.artifact_id) == friendly_slug:
            return diagram
    return None


def check_document_duplicate(
    repo: ArtifactRepository,
    doc_type: str,
    friendly_slug: str,
    exclude_artifact_id: str | None = None,
) -> DocumentRecord | None:
    """Check if document with same type + slug exists. Returns the duplicate or None."""
    documents = repo.list_documents(doc_type=doc_type)
    for document in documents:
        if _is_self(document.artifact_id, exclude_artifact_id):
            continue
        if extract_friendly_slug(document.artifact_id) == friendly_slug:
            return document
    return None


def validate_entity_unique(
    repo: ArtifactRepository,
    artifact_type: str,
    friendly_slug: str,
    exclude_artifact_id: str | None = None,
) -> None:
    """Raise ValueError if entity with same type + slug exists elsewhere."""
    dup = check_entity_duplicate(repo, artifact_type, friendly_slug, exclude_artifact_id)
    if dup:
        raise ValueError(
            f"Entity with type '{artifact_type}' and name '{friendly_slug}' already exists: {dup.artifact_id}. "
            f"Artifact type + name must be unique across all repositories."
        )


def validate_diagram_unique(
    repo: ArtifactRepository,
    diagram_type: str,
    friendly_slug: str,
    exclude_artifact_id: str | None = None,
) -> None:
    """Raise ValueError if diagram with same type + slug exists elsewhere."""
    dup = check_diagram_duplicate(repo, diagram_type, friendly_slug, exclude_artifact_id)
    if dup:
        raise ValueError(
            f"Diagram with type '{diagram_type}' and name '{friendly_slug}' already exists: {dup.artifact_id}. "
            f"Diagram type + name must be unique across all repositories."
        )


def validate_document_unique(
    repo: ArtifactRepository,
    doc_type: str,
    friendly_slug: str,
    exclude_artifact_id: str | None = None,
) -> None:
    """Raise ValueError if document with same type + slug exists elsewhere."""
    dup = check_document_duplicate(repo, doc_type, friendly_slug, exclude_artifact_id)
    if dup:
        raise ValueError(
            f"Document with type '{doc_type}' and name '{friendly_slug}' already exists: {dup.artifact_id}. "
            f"Document type + name must be unique across all repositories."
        )


def ensure_unique_entity_random_part(
    artifact_id: str,
    artifact_type: str,
    repo: ArtifactRepository,
    prefix: str,
    friendly_name: str,
    max_retries: int = 10,
) -> str:
    """Ensure (type + random-part) is unique. Regenerates ID if random part collides.

    Different entities of the same type must not share the same random part.
    """
    random_part = extract_random_part(artifact_id)

    # Check if this random part is already used with this type
    for entity in repo.list_entities(artifact_type=artifact_type):
        if extract_random_part(entity.artifact_id) == random_part:
            # Random part collision - regenerate
            for _ in range(max_retries):
                new_id = get_default_allocator().allocate(prefix=prefix, name_hint=friendly_name)
                new_random = extract_random_part(new_id)
                # Verify new random part is unique
                collision = False
                for e in repo.list_entities(artifact_type=artifact_type):
                    if extract_random_part(e.artifact_id) == new_random:
                        collision = True
                        break
                if not collision:
                    return new_id
            # If we exhaust retries, raise error
            raise ValueError(
                f"Unable to generate unique ID for {artifact_type} '{friendly_name}' "
                f"after {max_retries} attempts. Random part collisions are extremely unlikely; "
                f"please try again."
            )
    return artifact_id
