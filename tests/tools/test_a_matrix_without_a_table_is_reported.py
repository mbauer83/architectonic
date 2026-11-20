"""W322 asks whether a matrix body holds a table, and a pipe somewhere in the file is not one.

The rule used to search the whole file for the character. Frontmatter is part of the file, so a block
scalar (`description: |`) or a pipe in a title answered for a body that had no table at all, and so
did a row nobody had given a delimiter row — which no renderer draws as a table either.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.verification.artifact_verifier_rules import check_matrix_markdown_shape
from src.application.verification.artifact_verifier_types import VerificationResult

_FRONTMATTER = {"diagram-type": "matrix"}


def _codes(content: str, tmp_path: Path) -> list[str]:
    result = VerificationResult(path=tmp_path / "m.md", file_type="diagram")
    check_matrix_markdown_shape(_FRONTMATTER, content, result, "m.md")
    return [issue.code for issue in result.issues]


def test_a_body_holding_a_table_is_not_reported(tmp_path: Path) -> None:
    content = "---\ndiagram-type: matrix\n---\n\n| | A |\n|---|---|\n| **B** | ✓ |\n"

    assert _codes(content, tmp_path) == []


@pytest.mark.parametrize(
    "content",
    [
        pytest.param("---\ndiagram-type: matrix\ndescription: |\n  two\n---\n\nNo table.\n", id="block-scalar"),
        pytest.param("---\ndiagram-type: matrix\nname: a | b\n---\n", id="pipe-in-a-title"),
        pytest.param("---\ndiagram-type: matrix\n---\n\n| | A |\n| **B** | ✓ |\n", id="rows-without-a-delimiter"),
    ],
)
def test_a_pipe_that_is_not_a_table_does_not_answer_for_one(content: str, tmp_path: Path) -> None:
    assert _codes(content, tmp_path) == ["W322"]
