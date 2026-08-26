from dataclasses import asdict

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.application.artifacts._search import ALL_SEARCHABLE_KINDS
from src.domain.ontology_representation.artifact_types import (
    RecordType,
    ScratchpadNoteRecord,
    ScratchpadRecord,
    SearchableKind,
)
from src.infrastructure.mcp.artifact_mcp.context import RepoScope, repo_cached, resolve_repo_roots, roots_key
from src.infrastructure.mcp.tool_annotations import READ_ONLY

_FIELD_ALIASES = {"id": "artifact_id"}


def _project(record: dict[str, object], fields: list[str] | None) -> dict[str, object]:
    if not fields:
        return record
    resolved = [_FIELD_ALIASES.get(f, f) for f in fields]
    return {field: record[field] for field in resolved if field in record}


def _included_kinds(
    include_record_types: list[SearchableKind] | None,
    *,
    default: tuple[str, ...],
) -> frozenset[str]:
    """Return the canonical included-kinds set from the caller's include list.

    Entities are a normal member of the set — no implicit always-on behaviour.
    """
    return frozenset(include_record_types or default) & ALL_SEARCHABLE_KINDS


def register_query_search_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        name="artifact_query_search_artifacts",
        title="Artifact Query: Search Artifacts",
        description=(
            "Search artifacts by text query (keyword-scored; may include semantic supplement if configured). "
            "Returns ranked hits as (score + summary record). "
            "\n\nFilters: limit, domain, artifact_type, include_record_types, prefer_record_type, strict_record_type. "
            "Scratchpads and their notes are both searched by default. A pad is where thinking "
            "happened and a note is one thought, so they answer different questions: a pad's own "
            "name and description are matched, never its notes' text, and a note's own title and "
            "body are matched, never its pad's name. A note's id is "
            "`{scratchpad_id}#note/{note_id}` — read the scratchpad with scratchpad_read to see it "
            "in context. Both rank below model content, documents and diagrams on similarity, "
            "because preliminary thinking does not outrank a commitment — but a title the caller "
            "typed exactly, or one carrying every search term, ranks first whatever kind it is. "
            "Domain filter is case-insensitive; canonical lowercase values: "
            '"common", "motivation", "strategy", "business", "application", "technology", "implementation".'
            "\n\nRepo selection: repo_scope defaults to both (engagement + enterprise)."
        ),
        annotations=READ_ONLY,
        structured_output=True,
    )
    def artifact_query_search_artifacts(
        query: str,
        *,
        limit: int = 10,
        domain: str | list[str] | None = None,
        artifact_type: str | list[str] | None = None,
        include_record_types: (
            list[SearchableKind] | None
        ) = None,
        prefer_record_type: RecordType | None = None,
        strict_record_type: bool = False,
        fields: list[str] | None = None,
        repo_root: str | None = None,
        repo_scope: RepoScope = "both",
    ) -> dict[str, object]:
        roots = resolve_repo_roots(
            repo_scope=repo_scope,
            repo_root=repo_root,
            repo_preset=None,
            enterprise_root=None,
        )
        key = roots_key(roots)
        repo = repo_cached(key)
        kinds = _included_kinds(
            include_record_types,
            default=("entities", "diagrams", "documents", "scratchpads", "scratchpad-notes"),
        )

        result = repo.search_artifacts(
            query,
            limit=limit,
            domain=domain,
            artifact_type=artifact_type,
            include_entities="entities" in kinds,
            include_connections="connections" in kinds,
            include_diagrams="diagrams" in kinds,
            include_documents="documents" in kinds,
            include_scratchpads="scratchpads" in kinds,
            include_scratchpad_notes="scratchpad-notes" in kinds,
            prefer_record_type=prefer_record_type,
            strict_record_type=strict_record_type,
        )

        hits: list[dict[str, object]] = []
        for h in result.hits:
            aid = getattr(h.record, "artifact_id", "")
            record = {
                "score": h.score,
                "record_type": h.record_type,
                "artifact_id": aid,
            }
            if isinstance(h.record, ScratchpadRecord):
                # A pad is addressable and readable on its own, so the answer is the address plus
                # what a caller needs to decide whether to open it.
                record.update({
                    "name": h.record.name,
                    "description": h.record.description,
                    "status": h.record.status,
                    "group": h.record.group,
                })
            elif isinstance(h.record, ScratchpadNoteRecord):
                # A note has no artifact summary to fetch: it is not an artifact, it is part of one.
                # The fields here are the same questions a summary answers — what is it called, what
                # kind is it, where does it live — asked of a note, plus the scratchpad to read next.
                record.update({
                    "name": h.record.title,
                    "artifact_type": h.record.element_type,
                    "status": h.record.status,
                    "path": str(h.record.path),
                    "group": h.record.group,
                    "scratchpad_id": h.record.scratchpad_id,
                    "scratchpad_name": h.record.scratchpad_name,
                    "area": h.record.area,
                })
            elif (summary := repo.summarize_artifact(aid) if aid else None) is not None:
                summary_dict = asdict(summary)
                summary_dict["path"] = str(summary.path)
                record.update(summary_dict)
            hits.append(_project(record, fields))

        return {
            "repo_roots": [str(p) for p in roots],
            "repo_scope": repo_scope,
            "query": result.query,
            "hits": hits,
        }
