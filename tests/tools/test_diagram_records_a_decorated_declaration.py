"""A body may decorate a declaration, and the diagram it writes must still verify.

Reported from another checkout as "a junction cannot be drawn in an ArchiMate view": authoring
`function → junction → function` failed **E315** on the junction's own alias, while
`connection-ids-used` recorded both of the junction's connections by their real ids. The two
reconcilers disagreed about whether the junction existed.

The cause is not junctions and not a type filter. The reader that derives `entity-ids-used` from a
body anchored the alias to the end of the line, and a junction is drawn as a coloured circle
(`circle " " as JNA_x #252327`), so the declaration was invisible to it — while the verifier, which
resolves drawn aliases against the model's display aliases, saw it. A coloured *rectangle* fails
identically, which is what makes the fix the reader rather than a filter.

The report's second symptom, **E317** on junction-sourced edges, is *not* reproduced by this
mechanism and is deliberately not claimed here: measured against a decorated body, the connections
were recorded correctly and only E315 fired. E317 appeared in one probe against the live repository,
for the honest reason that the pair drawn there had no model connection at all. Whatever produced the
reporter's E317 is a separate question, most likely the re-derived list left by the no-`puml` edit
their own report describes.

These run through the real write tool against a real repository, because the defect was in what the
tool *records* rather than in what any component computes in isolation — and the previous shape of
this had no test at all: `infer_entities_from_puml` was referenced only from `src/`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest

_JUNCTION = "JNA@1000000000.JunAaa.the-fork"
_FUNCTION_A = "FNC@1000000002.FncCcc.function-a"
_FUNCTION_B = "FNC@1000000003.FncDdd.function-b"

_TRIGGERING = "archimate-triggering"


@lru_cache(maxsize=1)
def _entity_types() -> dict:
    from src.infrastructure.app_bootstrap import build_module_registry  # noqa: PLC0415

    return {str(name): info for name, info in build_module_registry().all_entity_types().items()}


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _alias(artifact_id: str) -> str:
    return f"{artifact_id.split('@')[0]}_{artifact_id.split('.')[1]}"


def _write_entity(repo: Path, artifact_id: str, artifact_type: str, domain: str, element: str) -> None:
    hierarchy = _entity_types()[artifact_type].hierarchy
    _write(
        repo / "model" / Path(*hierarchy) / f"{artifact_id}.md",
        f"""\
---
artifact-id: {artifact_id}
artifact-type: {artifact_type}
name: "{artifact_id}"
version: 0.1.0
status: draft
last-updated: '2026-08-12'
---

<!-- §content -->

## {artifact_id}

<!-- §display -->

### archimate

```yaml
domain: {domain}
element-type: {element}
label: "{artifact_id}"
alias: {_alias(artifact_id)}
```
""",
    )


def _write_outgoing(repo: Path, source: str, artifact_type: str, legs: list[tuple[str, str]]) -> None:
    hierarchy = _entity_types()[artifact_type].hierarchy
    sections = "\n".join(f"### {conn_type} → {target}\n" for conn_type, target in legs)
    _write(
        repo / "model" / Path(*hierarchy) / f"{source}.outgoing.md",
        f"""\
---
source-entity: {source}
version: 0.1.0
status: draft
last-updated: '2026-08-12'
---

<!-- §connections -->

{sections}
""",
    )


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A → junction → B, the smallest model in which a junction can be drawn."""
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    _write_entity(root, _FUNCTION_A, "function", "Business", "Business Function")
    _write_entity(root, _FUNCTION_B, "function", "Business", "Business Function")
    _write_entity(root, _JUNCTION, "and-junction", "Common", "And Junction")
    _write_outgoing(root, _FUNCTION_A, "function", [(_TRIGGERING, _JUNCTION)])
    _write_outgoing(root, _JUNCTION, "and-junction", [(_TRIGGERING, _FUNCTION_B)])
    return root


def _body(*, junction_colour: str = "", function_colour: str = "") -> str:
    return f"""@startuml zz-decorated
rectangle "A" <<function>> as {_alias(_FUNCTION_A)}{function_colour}
circle " " as {_alias(_JUNCTION)}{junction_colour}
rectangle "B" <<function>> as {_alias(_FUNCTION_B)}

{_alias(_FUNCTION_A)} --> {_alias(_JUNCTION)}
{_alias(_JUNCTION)} --> {_alias(_FUNCTION_B)}
@enduml"""


def _create(repo: Path, body: str, *, entity_ids: list[str] | None = None) -> dict:
    from src.infrastructure.mcp import mcp_artifact_server as write_tools  # noqa: PLC0415

    return write_tools.artifact_create_diagram(
        diagram_type="archimate-business",
        name="zz decorated",
        puml=body,
        entity_ids=entity_ids,
        auto_include_stereotypes=False,
        dry_run=True,
        repo_root=str(repo),
    )


def _listed(result: dict, key: str) -> list[str]:
    """The frontmatter list the write produced, read back out of the emitted content."""
    lines = str(result["content"]).splitlines()
    try:
        start = lines.index(f"{key}:")
    except ValueError:
        return []
    listed: list[str] = []
    for line in lines[start + 1 :]:
        if not line.startswith("- "):
            break
        listed.append(line[2:].strip())
    return listed


class TestADecoratedDeclarationIsRecorded:
    def test_a_coloured_junction_verifies_and_is_listed(self, repo: Path) -> None:
        """The reported failure. Before the fix: E315 on the junction's own alias."""
        result = _create(repo, _body(junction_colour=" #252327"))

        assert result["verification"]["valid"] is True, result["verification"]["issues"]
        assert _JUNCTION in _listed(result, "entity-ids-used")

    def test_a_coloured_rectangle_verifies_and_is_listed(self, repo: Path) -> None:
        """Same defect, no junction involved — which is what makes the fix the reader, not a filter."""
        result = _create(repo, _body(function_colour=" #E6F3FF"))

        assert result["verification"]["valid"] is True, result["verification"]["issues"]
        assert _FUNCTION_A in _listed(result, "entity-ids-used")

    def test_the_connections_of_a_decorated_entity_are_still_recorded(self, repo: Path) -> None:
        """A companion, not a regression: these were recorded before the fix as well.

        Pinned because it is the asymmetry the report described — both of the junction's connections
        recorded by their real ids while the junction itself was missing — so a later change that
        "fixes" the disagreement by dropping the connections instead is caught here.
        """
        result = _create(repo, _body(junction_colour=" #252327", function_colour=" #E6F3FF"))

        recorded = _listed(result, "connection-ids-used")
        assert len(recorded) == 2, recorded
        assert all(_JUNCTION.split(".")[0] in cid for cid in recorded), recorded

    def test_an_undecorated_body_still_verifies(self, repo: Path) -> None:
        """The case that always worked, kept so a fix here cannot trade one shape for another."""
        result = _create(repo, _body())

        assert result["verification"]["valid"] is True, result["verification"]["issues"]


class TestAnExplicitlyPassedIdIsHonoured:
    def test_an_id_passed_alongside_a_body_is_recorded_rather_than_discarded(self, repo: Path) -> None:
        """`entity_ids and not puml` meant a supplied id was silently dropped, in either id form.

        Stated with an id the body does **not** draw, which is the only way to see the difference: an
        id the body draws is recorded by the body inference anyway, so asserting on one of those would
        pass whether the caller's list was honoured or discarded.

        Silently discarding what a caller named is worse than refusing it — nothing told them the
        diagram they had just written could not verify.
        """
        undrawn_body = f"""@startuml zz-undrawn
rectangle "A" <<function>> as {_alias(_FUNCTION_A)}
rectangle "B" <<function>> as {_alias(_FUNCTION_B)}
@enduml"""

        result = _create(repo, undrawn_body, entity_ids=[_JUNCTION.rsplit(".", 1)[0]])

        assert result["verification"]["valid"] is True, result["verification"]["issues"]
        # Recorded in full form, from the short form the caller passed.
        assert _JUNCTION in _listed(result, "entity-ids-used")
