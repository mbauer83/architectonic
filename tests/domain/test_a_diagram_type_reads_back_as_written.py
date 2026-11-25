"""The diagram type a diagram file is written with is the one its frontmatter reads back as.

The writer (`format_diagram_puml`) and the reader (`diagram_type_field`) as a pair, over what the
field permits: any stated type, and none — which an older file may hold and which is read as
ArchiMate for drawing and as missing for the verifier.
"""

from __future__ import annotations

import pytest

from src.application.modeling.diagram_file_format import format_diagram_puml
from src.domain.diagrams.diagram_type_field import (
    DIAGRAM_TYPE_KEY,
    UNSTATED_DIAGRAM_TYPE,
    diagram_type_of,
    stated_diagram_type,
)
from src.domain.repository.frontmatter import parse_frontmatter


def _written(diagram_type: str) -> dict[str, object]:
    text = format_diagram_puml(
        artifact_id="DIA@1.abc.x", diagram_type=diagram_type, name="x", version="0.1.0",
        status="draft", last_updated="2026-01-01", puml_body="@startuml\n@enduml\n",
    )
    return dict(parse_frontmatter(text))


@pytest.mark.parametrize("diagram_type", ["archimate-layered", "c4-container", "matrix", "datatype", "gsn"])
def test_a_stated_type_reads_back_as_written(diagram_type: str) -> None:
    frontmatter = _written(diagram_type)

    assert stated_diagram_type(frontmatter) == diagram_type
    assert diagram_type_of(frontmatter) == diagram_type


@pytest.mark.parametrize(
    "unstated", [{}, {DIAGRAM_TYPE_KEY: None}, {DIAGRAM_TYPE_KEY: ""}, {DIAGRAM_TYPE_KEY: "  "}]
)
def test_a_diagram_stating_no_type_is_drawn_as_archimate_and_reads_as_missing(
    unstated: dict[str, object],
) -> None:
    assert stated_diagram_type(unstated) == ""
    assert diagram_type_of(unstated) == UNSTATED_DIAGRAM_TYPE == "archimate"
