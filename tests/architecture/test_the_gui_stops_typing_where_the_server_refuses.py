"""The GUI's candidate description limit is the server's.

A form stops typing at `DESCRIPTION_LIMIT` (`tools/gui/src/domain/schemas/candidates.ts`) and the server
refuses a longer description (`candidate_architecture.DESCRIPTION_LIMIT`, served as the `maxLength` of the
wire's description). The generated OpenAPI types carry no `maxLength` value and `contracts:check` compares
shapes, not constants, so a change to one side left the form allowing input the server refuses — or stopping
short of what it accepts — with every gate green. The server's constant is the survivor; this holds the
GUI's copy to it.
"""

from __future__ import annotations

import re

from src.application.change_sets.candidate_architecture import DESCRIPTION_LIMIT
from src.infrastructure.candidate_wire import CandidateHeader, CandidatePatch
from tests.support.source_paths import TOOLS

_GUI_SCHEMA = TOOLS / "gui" / "src" / "domain" / "schemas" / "candidates.ts"
_STATED = re.compile(r"^export const DESCRIPTION_LIMIT = (\d+)$", re.MULTILINE)


def test_the_gui_states_the_limit_the_server_holds() -> None:
    (stated,) = _STATED.findall(_GUI_SCHEMA.read_text(encoding="utf-8"))
    assert int(stated) == DESCRIPTION_LIMIT


def test_the_served_contract_publishes_the_same_limit() -> None:
    for model in (CandidateHeader, CandidatePatch):
        description = model.model_json_schema()["properties"]["description"]
        lengths = {option.get("maxLength") for option in description.get("anyOf", [description])} - {None}
        assert lengths == {DESCRIPTION_LIMIT}, model.__name__
