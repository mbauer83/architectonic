"""The request body of a row edit, as REST frames it.

The rows themselves, the section and text bodies and their reading are
`src.infrastructure.document_part_wire`'s, which the MCP tools take as arguments too; this adds only
what is REST's own: the envelope with `dry_run` beside the rows.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.infrastructure.document_part_wire import RowEditBody


class EditDocumentTableRequest(BaseModel):
    rows: list[RowEditBody] = Field(min_length=1)
    dry_run: bool = True
