"""Guards for the persona catalog (tools/usability_test/personas.yaml): structural integrity,
and that every controlled value resolves against tools/usability_test/vocabularies.yaml rather
than against a vocabulary hard-coded here. Extending a vocabulary must be a data change;
a value that no vocabulary declares must fail."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_USABILITY_DIR = _REPO_ROOT / "tools" / "usability_test"

_KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_SNAKE = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")

_REQUIRED_PERSONA_FIELDS = frozenset({
    "id", "name", "role", "expertise", "capabilities", "literacies", "boundaries",
    "focus", "channels", "information_strategy", "decision_strategy", "resources",
    "recurring_questions",
})
_REQUIRED_ROLE_FIELDS = frozenset({"summary", "setting", "accountabilities"})
_REQUIRED_INFORMATION_STRATEGY_FIELDS = frozenset({
    "entry_point", "breadth", "depth", "verification", "dead_end_response",
})
_REQUIRED_DECISION_STRATEGY_FIELDS = frozenset({
    "evidence_basis", "risk_posture", "abandonment", "delegation",
})
_REQUIRED_RESOURCE_FIELDS = frozenset({"task_actions", "authoring_actions", "session_shape"})
_REQUIRED_QUESTION_FIELDS = frozenset({"id", "text", "information_need", "decision_artifact"})


def _load(name: str) -> dict[str, Any]:
    loaded: Any = yaml.safe_load((_USABILITY_DIR / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture(scope="module")
def vocabularies() -> dict[str, Any]:
    return _load("vocabularies.yaml")


@pytest.fixture(scope="module")
def personas() -> list[dict[str, Any]]:
    catalog = _load("personas.yaml")
    assert catalog["schema"] == 4
    assert catalog["kind"] == "persona-catalog"
    return list(catalog["personas"])


def _ids(vocabularies: dict[str, Any], name: str) -> frozenset[str]:
    return frozenset(str(entry["id"]) for entry in vocabularies[name])


def test_every_vocabulary_entry_is_defined(vocabularies: dict[str, Any]) -> None:
    """A term without a definition is a term two readers will use differently."""
    for name, entries in vocabularies.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            assert entry.get("meaning"), f"{name}/{entry.get('id')}: no meaning declared"
        declared = [str(entry["id"]) for entry in entries]
        assert len(declared) == len(set(declared)), f"{name}: duplicate ids"


def test_persona_ids_are_unique_self_describing_slugs(personas: list[dict[str, Any]]) -> None:
    ids = [persona["id"] for persona in personas]
    assert len(ids) == len(set(ids))
    for persona_id in ids:
        assert _KEBAB.match(persona_id), f"{persona_id}: persona ids are kebab-case slugs"


def test_personas_declare_every_required_field(personas: list[dict[str, Any]]) -> None:
    for persona in personas:
        missing = _REQUIRED_PERSONA_FIELDS - persona.keys()
        assert not missing, f"{persona.get('id')}: missing {sorted(missing)}"
        assert _REQUIRED_ROLE_FIELDS <= persona["role"].keys(), persona["id"]
        assert _REQUIRED_INFORMATION_STRATEGY_FIELDS <= persona["information_strategy"].keys(), persona["id"]
        assert _REQUIRED_DECISION_STRATEGY_FIELDS <= persona["decision_strategy"].keys(), persona["id"]
        assert _REQUIRED_RESOURCE_FIELDS <= persona["resources"].keys(), persona["id"]
        for field in ("capabilities", "literacies", "boundaries", "focus", "channels"):
            assert persona[field], f"{persona['id']}: {field} is empty"


def test_persona_field_keys_are_snake_case(personas: list[dict[str, Any]]) -> None:
    """Key style is uniform across the specification files: snake_case nouns, no articles."""
    for persona in personas:
        for block in ("role", "expertise", "information_strategy", "decision_strategy", "resources"):
            for key in persona[block]:
                assert _SNAKE.match(str(key)), f"{persona['id']}/{block}: {key!r} is not snake_case"


def test_expertise_is_graded_on_every_declared_axis(
    personas: list[dict[str, Any]], vocabularies: dict[str, Any]
) -> None:
    """The point of grading per axis rather than flagging expert/non-expert is that a
    persona can be an authority in one field and a beginner in another — which only holds
    if every persona is graded on every axis."""
    axes = _ids(vocabularies, "expertise_axes")
    levels = _ids(vocabularies, "expertise_levels")
    for persona in personas:
        assert persona["expertise"].keys() == axes, persona["id"]
        for axis, level in persona["expertise"].items():
            assert level in levels, f"{persona['id']}/{axis}: unknown level {level!r}"


def test_controlled_values_resolve_against_the_vocabularies(
    personas: list[dict[str, Any]], vocabularies: dict[str, Any]
) -> None:
    channels = _ids(vocabularies, "channels")
    postures = _ids(vocabularies, "risk_postures")
    artifacts = _ids(vocabularies, "decision_artifacts")
    for persona in personas:
        for channel in persona["channels"]:
            assert channel in channels, f"{persona['id']}: unknown channel {channel!r}"
        posture = persona["decision_strategy"]["risk_posture"]
        assert posture in postures, f"{persona['id']}: unknown risk posture {posture!r}"
        for question in persona["recurring_questions"]:
            artifact = question["decision_artifact"]
            assert artifact in artifacts, f"{question['id']}: unknown decision artifact {artifact!r}"


def test_budgets_are_positive_ordinal_action_counts(personas: list[dict[str, Any]]) -> None:
    """Budgets are counted in actions, never in minutes: a synthetic run has no wall clock,
    so a time budget would measure nothing and could not be enforced."""
    for persona in personas:
        for field in ("task_actions", "authoring_actions"):
            budget = persona["resources"][field]
            assert isinstance(budget, int) and budget > 0, f"{persona['id']}/{field}: {budget!r}"
        assert isinstance(persona["resources"]["session_shape"], str)


def test_recurring_questions_are_complete_and_globally_unique(personas: list[dict[str, Any]]) -> None:
    seen: dict[str, str] = {}
    for persona in personas:
        assert persona["recurring_questions"], f"{persona['id']}: no recurring questions"
        for question in persona["recurring_questions"]:
            missing = _REQUIRED_QUESTION_FIELDS - question.keys()
            assert not missing, f"{question.get('id')}: missing {sorted(missing)}"
            question_id = str(question["id"])
            assert _KEBAB.match(question_id), f"{question_id}: question ids are kebab-case slugs"
            assert question_id not in seen, (
                f"{question_id} is declared by both {seen[question_id]} and {persona['id']}; "
                "scenario tasks reference these ids, so they must be unambiguous"
            )
            seen[question_id] = str(persona["id"])


def test_the_agent_channel_has_a_persona(personas: list[dict[str, Any]]) -> None:
    """A product whose audience is humans and agents alike cannot be evaluated on the
    agent channel without at least one persona that works it."""
    assert any("mcp" in persona["channels"] for persona in personas)
