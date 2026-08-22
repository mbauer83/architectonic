"""W045 — a declared step the stored body does not draw, and the port addition that makes it visible.

The severe half of the defect this diagnostic exists for was that it was silent: a diagram missing
a quarter of its steps verified clean, because every rule read the model and none read the picture.
So the assertions here are about a **stored** body that disagrees with its own frontmatter. A
contribution that re-rendered from `diagram-entities` and compared would be putting the renderer
against itself, and would pass on every input.

`BaseDiagramVerificationContext` did not carry the body, and the first two tests are the delegation
CLAUDE.md asks for after completing a contract: that the field exists and that the runner fills it
from the file's own content rather than the contribution re-reading the file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.application.verification._verifier_contribution_runner import run_diagram_contributions
from src.application.verification.artifact_verifier_types import VerificationResult
from src.diagram_types.activity._contributions import STEP_COVERAGE_CONTRIBUTION
from src.domain.diagrams.diagram_verification import BaseDiagramVerificationContext
from tests.diagram_types._activity_shapes import CROSS_LEVEL_CONVERGENCE, bundled_shapes

_STEPS: dict[str, Any] = {
    "action": [{"id": "draft", "label": "draft it"}, {"id": "review", "label": "review it"}],
    "decision": [{"id": "ready", "condition": "is it ready", "then_label": "y", "else_label": "n"}],
}


def _run(fm: dict[str, Any], body: str) -> VerificationResult:
    result = VerificationResult(path=Path("d.puml"), file_type="diagram")
    ctx = BaseDiagramVerificationContext(
        fm=fm, loc="d.puml", scope="engagement", diagram_id="ACT@1.a.d",
        allowed_connections=frozenset(), allowed_entities=frozenset(), catalogs=None, body=body,
    )
    STEP_COVERAGE_CONTRIBUTION.run(None, ctx, result)
    return result


class TestTheContextCarriesTheStoredBody:
    def test_the_field_exists_and_defaults_to_empty(self) -> None:
        ctx = BaseDiagramVerificationContext(
            fm={}, loc="d.puml", scope="engagement", diagram_id="",
            allowed_connections=frozenset(), allowed_entities=frozenset(), catalogs=None,
        )

        assert ctx.body == ""

    def test_the_runner_fills_it_from_the_file_content(self) -> None:
        """The delegation: the body comes from the content the verifier already read."""
        seen: list[str] = []

        class _Spy:
            diagnostic_codes = ("W045",)

            def run(self, candidate: Any, ctx: BaseDiagramVerificationContext, result: Any) -> None:
                seen.append(ctx.body)

        class _Module:
            def diagram_verification_contributions(self) -> tuple:
                return (_Spy(),)

        class _Registry:
            def connection_ids(self) -> list[str]:
                return []

            def entity_ids(self) -> list[str]:
                return []

        content = "---\nartifact-id: ACT@1.a.d\n---\n@startuml d\n:[[arch://draft draft it]];\n@enduml\n"
        run_diagram_contributions(
            module=_Module(), candidate=object(), fm={"artifact-id": "ACT@1.a.d"}, content=content,
            registry=_Registry(), scope="engagement", runtime_catalogs=None,
            result=VerificationResult(path=Path("d.puml"), file_type="diagram"), loc="d.puml",
        )

        assert seen == ["@startuml d\n:[[arch://draft draft it]];\n@enduml\n"]


class TestAStoredBodyThatDrawsEveryStep:
    def test_it_reports_nothing(self) -> None:
        body = (
            "@startuml d\n:[[arch://draft draft it]];\n"
            "if ([[arch://ready is it ready??]]) then (y)\nelse (n)\nendif\n"
            ":[[arch://review review it]];\n@enduml\n"
        )

        assert _run({"diagram-entities": _STEPS}, body).issues == []

    def test_a_step_reached_by_a_connector_counts_once(self) -> None:
        """The connector line carries no sentinel; the line that draws the step does."""
        shape = CROSS_LEVEL_CONVERGENCE
        body = shape.render()

        assert _run({"diagram-entities": shape.entities}, body).issues == []

    def test_every_bundled_activity_diagram_is_clean_against_its_own_render(self) -> None:
        """Not a count over live content: the invariant is that a fresh render draws what it declares."""
        for shape in bundled_shapes():
            result = _run({"diagram-entities": shape.entities}, shape.render())

            assert result.issues == [], f"{shape.name}: {[i.message for i in result.issues]}"


class TestAStoredBodyMissingADeclaredStep:
    def test_it_is_a_warning_naming_the_step_and_the_remedy(self) -> None:
        body = "@startuml d\n:[[arch://draft draft it]];\n@enduml\n"

        issues = _run({"diagram-entities": _STEPS}, body).issues

        assert [i.code for i in issues] == ["W045", "W045"]
        assert {str(i.severity) for i in issues} == {"warning"}
        messages = " ".join(i.message for i in issues)
        assert "'review'" in messages and "'ready'" in messages
        assert 'puml="auto-sync"' in messages

    def test_a_fork_is_never_reported(self) -> None:
        """PlantUML's `fork` takes no label or link argument, so a fork carries nothing to read."""
        fm = {"diagram-entities": {"fork": [{"id": "split"}, {"id": "rejoin"}]}}

        assert _run(fm, "@startuml d\nfork\nend fork\n@enduml\n").issues == []

    def test_a_bound_step_is_matched_by_the_entity_it_represents(self) -> None:
        """A step bound to an entity carries that entity's id as its sentinel, not its local id."""
        fm = {"diagram-entities": {"action": [
            {"id": "draft", "label": "draft it", "entity_id": "FNC@1.a.draft-it"},
        ]}}

        assert _run(fm, "@startuml d\n:[[arch://FNC@1.a.draft-it draft it]];\n@enduml\n").issues == []
        assert [i.code for i in _run(fm, "@startuml d\n:[[arch://draft draft it]];\n@enduml\n").issues] == ["W045"]

    def test_no_stored_body_reports_nothing(self) -> None:
        """A diagram whose body has not been read is not a diagram missing its steps."""
        assert _run({"diagram-entities": _STEPS}, "").issues == []
