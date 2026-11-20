"""A lifted note's attributes reach the entity, and are checked against the repository's schema.

Driven through the real tools on a repository the test creates, because both halves are about what
reaches disk: the attribute is in the entity's Properties table after a lift, and a value the write
would refuse stops the lift before anything is written — on the read, in the preflight, with the
code the verifier gives.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.infrastructure.mcp.artifact_mcp.scratchpad_tools import (
    scratchpad_create,
    scratchpad_edit,
    scratchpad_lift,
)

_GOAL_SCHEMA = {
    "type": "object",
    "properties": {
        "Horizon": {"type": "string", "enum": ["near", "far"]},
        "Weight": {"type": "integer"},
    },
}


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    schemata = root / ".arch-repo" / "schemata"
    schemata.mkdir(parents=True)
    (schemata / "attributes.goal.schema.json").write_text(json.dumps(_GOAL_SCHEMA), encoding="utf-8")
    return root


def _pad_with(repo: Path, attributes: dict[str, Any]) -> dict[str, Any]:
    created = scratchpad_create(name="Q3 thinking", repo_root=str(repo))
    assert created["ok"], created
    pad = created["scratchpad"]
    stored = scratchpad_edit(
        artifact_id=pad["artifact-id"], version=pad["version"],
        upsert={"notes": [{  # type: ignore[arg-type]
            "id": "n1", "title": "Grow", "destination": "element", "element-type": "goal",
            "attributes": attributes,
        }]},
        repo_root=str(repo),
    )
    assert stored["ok"], stored
    return stored["scratchpad"]


def _lift(repo: Path, pad: dict[str, Any]) -> dict[str, Any]:
    answer = scratchpad_lift(
        artifact_id=pad["artifact-id"], selection=["n1"], version=pad["version"],
        dry_run=False, repo_root=str(repo),
    )
    assert answer["ok"], answer
    return answer["lift"]


def _entities(repo: Path) -> list[Path]:
    return sorted(
        path for path in (repo / "model").rglob("*.md") if not path.name.endswith(".outgoing.md")
    )


def test_the_attributes_of_a_lifted_note_are_the_entity_s_properties(repo: Path) -> None:
    pad = _pad_with(repo, {"Horizon": "far", "Weight": 3})

    lift = _lift(repo, pad)

    assert lift["committed"] and not lift["errors"], lift
    (entity,) = _entities(repo)
    written = entity.read_text(encoding="utf-8")
    assert "| Horizon | far |" in written
    assert "| Weight | 3 |" in written


def test_a_value_the_schema_s_type_cannot_read_is_refused_before_anything_is_written(
    repo: Path,
) -> None:
    pad = _pad_with(repo, {"Weight": "heavy"})

    served = pad["notes"][0]["verdict"]
    lift = _lift(repo, pad)

    assert (served["kind"], served["code"]) == ("refused", "E042")
    assert lift["blocks"] and not lift["committed"]
    (item,) = lift["items"]
    assert (item["outcome"], item["code"], item["reason"]) == ("refuse", "E042", served["message"])
    assert _entities(repo) == []


def test_an_attribute_the_schema_does_not_declare_warns_and_is_carried(repo: Path) -> None:
    pad = _pad_with(repo, {"Sponsor": "CFO"})

    lift = _lift(repo, pad)

    assert pad["notes"][0]["verdict"]["kind"] == "narrowed"
    assert lift["committed"], lift
    assert "Attribute 'Sponsor' is not declared for goal" in lift["items"][0]["warning"]
    (entity,) = _entities(repo)
    assert "| Sponsor | CFO |" in entity.read_text(encoding="utf-8")
