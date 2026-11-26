"""A typed table's `id` cells are checked against what is stored, listing each kind's files once.

Verifying a stress analysis, or writing its rows, asked "is this candidate stored?" once per id cell, and
each ask listed every candidate file again: O(cells × candidates) directory scans. One reader is bound per
verification or edit (`stored_id_reader`). Which kinds an `id` column may name is the kind table's to say
(`named_by_id_in_documents`), not a literal in the generic document-table module.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts import stored_ids
from src.application.artifacts.document_tables import ID_COLUMN_KINDS
from src.domain.repository.artifact_location import ARTIFACT_KINDS

_STORED = "CAND@1795685981.VJ9xSMc"


def test_each_kind_is_listed_once_however_many_cells_ask(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = tmp_path / "candidate-architectures"
    store.mkdir()
    (store / f"{_STORED}.cached-index-store.candidate.yaml").write_text("id: x\n", encoding="utf-8")
    listings: list[str] = []
    real = stored_ids.stored_ids

    def counted(root: Path, kind: str) -> dict[str, str]:
        listings.append(kind)
        return real(root, kind)  # type: ignore[arg-type]

    monkeypatch.setattr(stored_ids, "stored_ids", counted)
    stored_id_of = stored_ids.stored_id_reader(tmp_path)

    answers = [stored_id_of("candidate-architecture", spelled) for spelled in (_STORED, f"{_STORED}.x", "CAND@1.n")]

    assert answers == [f"{_STORED}.cached-index-store", f"{_STORED}.cached-index-store", None]
    assert listings == ["candidate-architecture"]


def test_the_kinds_an_id_column_may_name_are_the_kind_tables() -> None:
    assert ID_COLUMN_KINDS == tuple(kind.name for kind in ARTIFACT_KINDS if kind.named_by_id_in_documents)
    assert ID_COLUMN_KINDS == ("candidate-architecture",)
