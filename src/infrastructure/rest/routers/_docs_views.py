"""Section views over the one OpenAPI document, so a reader can open part of a large surface.

The document is 136 paths, 166 operations and 391 schemas — about 874 KB. `/docs` renders all of it,
and a reader who came for the assurance store scrolls past everything else to reach it.

**Views, not documents.** The obvious move is to split the contract, and it is the wrong one here: one
document is load-bearing. `tools/gui/scripts/contracts.mjs` dumps it to a single file, generates
`openapi.generated.ts` from that, and `npm run contracts:check` holds the hand-written Effect schemas
against it. Splitting would fragment that pipeline, multiply the gate, and force a decision about which
document owns each of the 391 schemas — many of them shared (the error envelope, the write receipts, the
pagination shapes). Cross-document `$ref` is legal and unevenly supported; duplicating shared schemas is
how two contracts drift. And the partition would not correspond to anything: it is one service, on one
origin, with one auth surface and one error vocabulary.

So the sections here are *filters* over the served document. Nothing to keep in sync, because there is
only ever one source; a section that named a tag nobody uses would serve an empty document rather than a
stale one, and `tests/architecture/test_openapi_tags.py` holds the tag vocabulary itself.

**Schemas are not pruned.** A filtered document keeps every component, because pruning means computing
the transitive `$ref` closure of the operations kept, and getting that wrong produces a document that
looks complete and cannot be resolved. An unused schema costs a reader nothing — Swagger UI lists
operations, not components — and costs the response some bytes, which is the cheaper mistake.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI

from src.infrastructure.rest.routers._openapi import (
    ALL_TAGS,
    TAG_ASSURANCE_ANALYSES,
    TAG_ASSURANCE_ARGUMENTS,
    TAG_ASSURANCE_FMEA,
    TAG_ASSURANCE_NODES,
    TAG_ASSURANCE_SECURITY,
    TAG_ASSURANCE_STORE,
)

#: The assurance tags, as a set, so `architecture` can be defined as everything else.
ASSURANCE_TAGS: frozenset[str] = frozenset({
    TAG_ASSURANCE_STORE,
    TAG_ASSURANCE_ANALYSES,
    TAG_ASSURANCE_NODES,
    TAG_ASSURANCE_FMEA,
    TAG_ASSURANCE_ARGUMENTS,
    TAG_ASSURANCE_SECURITY,
})

#: Section name → the tags it shows.
#:
#: `architecture` is defined by *subtraction* rather than by listing its tags, so a new architecture
#: section appears in it without anyone remembering to add it here. The failure mode of a positive list
#: is a new section that belongs to neither view and is reachable only from the unfiltered `/docs`.
SECTION_TAGS: dict[str, frozenset[str]] = {
    "architecture": ALL_TAGS - ASSURANCE_TAGS,
    "assurance": ASSURANCE_TAGS,
}


def filtered_document(document: dict[str, Any], tags: frozenset[str]) -> dict[str, Any]:
    """`document` with only the operations carrying one of `tags`.

    Deep-copied: the app caches its schema, and filtering in place would make the first section view
    requested the only complete document the process ever serves again.
    """
    filtered = copy.deepcopy(document)
    paths: dict[str, Any] = {}
    for path, methods in filtered.get("paths", {}).items():
        kept = {
            method: operation
            for method, operation in methods.items()
            if not isinstance(operation, dict)
            or not operation.get("operationId")
            or bool(set(operation.get("tags") or ()) & tags)
        }
        # A path whose every operation was filtered out is dropped, rather than left as an empty
        # object — an empty path item renders as a heading with nothing under it.
        if any(isinstance(op, dict) and op.get("operationId") for op in kept.values()):
            paths[path] = kept
    filtered["paths"] = paths
    filtered["tags"] = [t for t in filtered.get("tags", []) if t.get("name") in tags]
    return filtered


def install_docs_views(app: FastAPI) -> None:
    """Serve `/docs/{section}` and `/openapi/{section}.json` for each section.

    `include_in_schema=False` throughout: these are documentation surfaces, not part of the modelled
    REST contract, so they carry no route-policy row — the same treatment `/health` and the MCP mounts
    get. A row would make them answerable by the fitness functions that compare the served surface
    against the manifest, which is a claim nobody wants to make about a docs page.
    """
    from fastapi.openapi.docs import get_swagger_ui_html
    from fastapi.responses import HTMLResponse, JSONResponse

    def _view(section: str, tags: frozenset[str]) -> None:
        schema_path = f"/openapi/{section}.json"

        def read_schema() -> JSONResponse:
            return JSONResponse(filtered_document(app.openapi(), tags))

        def read_docs() -> HTMLResponse:
            return get_swagger_ui_html(
                openapi_url=schema_path,
                title=f"{app.title} — {section}",
            )

        app.add_api_route(schema_path, read_schema, include_in_schema=False)
        app.add_api_route(f"/docs/{section}", read_docs, include_in_schema=False)

    for section, tags in SECTION_TAGS.items():
        _view(section, tags)
