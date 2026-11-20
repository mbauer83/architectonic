"""A skill may only teach tools, arguments and assurance edge types that exist.

A skill is prose an agent follows literally, and nothing executes it: a call it spells wrongly fails
at the agent, far from the file that taught it. The assurance skills had drifted in exactly that way
— a `violates` edge the ontology never declared, `assurance_create_node` without the `analysis_id`
it requires, an ingestion script built on three tools that were never registered — and no gate read
them.

Three checks, each against the product's own declaration rather than a list kept here:

* a tool a skill names is registered on one of the four MCP mounts;
* an argument a skill passes in a call is one the tool declares, and a complete call passes the
  arguments the tool requires;
* an edge type passed to `assurance_add_edge` is one the assurance ontology permits somewhere.

What this cannot see is prose: a sentence that describes a rule wrongly still passes.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

from src.domain.yaml_documents import parse_yaml
from src.infrastructure.mcp.mcp_artifact_server import mcp_read, mcp_write
from src.infrastructure.mcp.mcp_assurance_server import mcp_assurance_read, mcp_assurance_write

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = REPO_ROOT / "skills"
ASSURANCE_CONNECTIONS = REPO_ROOT / "src" / "ontologies" / "assurance" / "connections.yaml"

_TOOL_NAME = r"(?:artifact|assurance|scratchpad)_[a-z0-9_]+"
#: A tool named as code, or called. A bare word in running prose is not a claim that a tool exists.
_NAMED = re.compile(rf"`({_TOOL_NAME})`|\b({_TOOL_NAME})\(")
#: One call with its argument text. Skill examples do not nest parentheses inside a call.
_CALL = re.compile(rf"\b({_TOOL_NAME})\(([^()]*)\)", re.DOTALL)
_KEYWORD = re.compile(r"\b([a-z_]+)\s*=(?!=)")
_EDGE_TYPE = re.compile(r"""conn_type\s*=\s*["']([a-z-]+)["']""")
#: An example that elides arguments does not claim to be a complete call.
_ELISION = ("...", "…")


def _registered_tools() -> dict[str, Mapping[str, object]]:
    return {
        tool.name: tool.parameters or {}
        for server in (mcp_read, mcp_write, mcp_assurance_read, mcp_assurance_write)
        for tool in server._tool_manager.list_tools()  # noqa: SLF001 - the registration is the subject
    }


def _declared(schema: Mapping[str, object], key: str) -> set[str]:
    value = schema.get(key)
    return {str(item) for item in value} if isinstance(value, list | dict) else set()


def _assurance_edge_types() -> set[str]:
    with ASSURANCE_CONNECTIONS.open(encoding="utf-8") as handle:
        ontology = parse_yaml(handle)
    return {edge for _source, _target, edges in ontology["permitted_relationships"] for edge in edges}


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def skill_defects(skills_root: Path) -> Iterator[str]:
    """Every place a skill under `skills_root` names something the product does not declare."""
    tools = _registered_tools()
    parameter_names = {name for schema in tools.values() for name in _declared(schema, "properties")}
    edge_types = _assurance_edge_types()
    for path in sorted(skills_root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        where = path.relative_to(skills_root)
        for match in _NAMED.finditer(text):
            name = match.group(1) or match.group(2)
            # `artifact_id` in backticks is an argument, which a skill may name as freely as a tool.
            if name not in tools and name not in parameter_names:
                yield f"{where}:{_line(text, match.start())}: {name} is not a registered tool"
        for match in _CALL.finditer(text):
            name, arguments = match.group(1), match.group(2)
            if name not in tools:
                continue
            at = f"{where}:{_line(text, match.start())}: {name}"
            passed = set(_KEYWORD.findall(arguments))
            unknown = passed - _declared(tools[name], "properties")
            if unknown:
                yield f"{at} does not declare {sorted(unknown)}"
            missing = _declared(tools[name], "required") - passed
            if passed and missing and not any(mark in arguments for mark in _ELISION):
                yield f"{at} requires {sorted(missing)}"
            if name == "assurance_add_edge":
                for edge in _EDGE_TYPE.findall(arguments):
                    if edge not in edge_types:
                        yield f"{at} passes conn_type {edge!r}, which the assurance ontology does not declare"


def test_every_skill_names_only_what_is_registered() -> None:
    assert list(skill_defects(SKILLS_ROOT)) == []


def test_there_are_skills_to_check() -> None:
    """A gate over an empty directory passes for the wrong reason."""
    assert any(SKILLS_ROOT.rglob("SKILL.md"))


@pytest.mark.parametrize(
    ("body", "reported"),
    [
        ("Call `assurance_import_bom` first.", "assurance_import_bom is not a registered tool"),
        (
            'assurance_add_edge(source_id=a, target_id=b, conn_type="violates")',
            "passes conn_type 'violates'",
        ),
        ('assurance_create_node(node_type="loss", name="Loss of X")', "requires ['analysis_id']"),
        ('assurance_read_node(node_id=a, depth=2)', "does not declare ['depth']"),
    ],
)
def test_each_kind_of_drift_is_reported(tmp_path: Path, body: str, reported: str) -> None:
    """The checker itself, on text it must refuse — a gate that reports nothing proves nothing."""
    (tmp_path / "SKILL.md").write_text(body, encoding="utf-8")

    assert any(reported in defect for defect in skill_defects(tmp_path))


@pytest.mark.parametrize(
    "body",
    [
        "Report `artifact_id` values for every entity created.",
        "assurance_create_node(analysis_id=..., node_type='risk', ...)",
        'assurance_add_edge(source_id=a, target_id=b, conn_type="leads-to")',
        "Run `assurance_verify` and then assurance_stpa_complete().",
    ],
)
def test_what_is_correct_is_not_reported(tmp_path: Path, body: str) -> None:
    (tmp_path / "SKILL.md").write_text(body, encoding="utf-8")

    assert list(skill_defects(tmp_path)) == []
