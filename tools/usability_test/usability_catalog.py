"""Loading and allowlist projection for the persona/scenario usability framework.

Two things live here so they cannot drift apart: how the catalog is read, and which
fields of it a persona is allowed to see. Every brief that reaches an isolated persona
context is built by projecting through the allowlists below, so the evaluator's answer
key — preconditions, surfaces, invariants, expected routes and oracles — cannot leak
into a persona context through a composition mistake. Guarded by
tests/tools/test_usability_helpers.py and tests/common/test_usability_scenarios.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.domain.yaml_documents import parse_yaml

USABILITY_DIR = Path(__file__).resolve().parent
REPO_ROOT = USABILITY_DIR.parents[1]
VOCABULARIES_PATH = USABILITY_DIR / "vocabularies.yaml"
PERSONAS_PATH = USABILITY_DIR / "personas.yaml"
SCENARIOS_DIR = USABILITY_DIR / "scenarios"

# Persona-visible projections. Adding a field to a source file does NOT make it visible:
# it has to be named here, which is the point.
PERSONA_BRIEF_FIELDS: tuple[str, ...] = (
    "name", "role", "expertise", "capabilities", "literacies", "boundaries", "focus",
    "channels", "information_strategy", "decision_strategy", "resources",
    "recurring_questions",
)
SCENARIO_BRIEF_FIELDS: tuple[str, ...] = ("id", "title", "situation", "stakes", "channels")
TASK_BRIEF_FIELDS: tuple[str, ...] = (
    "id", "text", "information_need", "decision_artifact", "budget_actions",
)

# Field names that must never appear as a key anywhere in a composed brief.
EVALUATOR_ONLY_FIELDS: frozenset[str] = frozenset({
    "write_policy", "preconditions", "surfaces", "invariants", "participants",
    "expected_route", "oracle", "candidates", "action", "derivation_method", "exclusions",
    "expected_answer_class", "verification_method", "cleanup", "slug_prefix", "recurring_question",
    "work_type", "statement", "mutations", "rationale", "expertise_overrides",
})


def _load_yaml(path: Path) -> dict[str, Any]:
    loaded: Any = parse_yaml(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} does not contain a YAML mapping")
    return loaded


def load_vocabularies() -> dict[str, Any]:
    return _load_yaml(VOCABULARIES_PATH)


def vocabulary_ids(vocabularies: dict[str, Any], name: str) -> frozenset[str]:
    """The declared ids of one controlled vocabulary; raises if the vocabulary is unknown,
    so a typo in a test or a scenario cannot silently validate against an empty set."""
    entries = vocabularies.get(name)
    if not isinstance(entries, list) or not entries:
        raise KeyError(f"no such vocabulary (or empty): {name!r}")
    return frozenset(str(entry["id"]) for entry in entries)


def overridable_axes(vocabularies: dict[str, Any] | None = None) -> frozenset[str]:
    """The expertise axes a scenario may restate for one participant.

    An axis qualifies only when its MEANING depends on the situation — `solution_domain`
    names the domain of whatever is modelled, so no persona can settle it in advance. The
    others describe the person; letting a scenario restate one would make the same persona
    two different subjects, and findings scored against it would no longer be comparable
    between runs. Declared in the vocabulary rather than listed here, so the rule has one home.
    """
    vocab = vocabularies if vocabularies is not None else load_vocabularies()
    entries = vocab.get("expertise_axes")
    if not isinstance(entries, list) or not entries:
        raise KeyError("no such vocabulary (or empty): 'expertise_axes'")
    return frozenset(str(e["id"]) for e in entries if e.get("overridable") is True)


def load_personas() -> dict[str, dict[str, Any]]:
    """Personas keyed by id, in catalog order."""
    catalog = _load_yaml(PERSONAS_PATH)
    return {str(persona["id"]): persona for persona in catalog["personas"]}


def load_scenarios() -> dict[str, dict[str, Any]]:
    """Scenarios keyed by id. The file stem must equal the declared id — the two are
    used interchangeably on the command line, so a mismatch would be a trap."""
    scenarios: dict[str, dict[str, Any]] = {}
    for path in sorted(SCENARIOS_DIR.glob("*.yaml")):
        scenario = _load_yaml(path)
        declared = str(scenario["id"])
        if declared != path.stem:
            raise ValueError(f"{path.name}: declares id {declared!r}, expected {path.stem!r}")
        scenarios[declared] = scenario
    return scenarios


def iter_tasks(scenario: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Every (participant, task) pair in a scenario, for evaluator-side traversal."""
    return [
        (participant, task)
        for participant in scenario["participants"]
        for task in participant["tasks"]
    ]


def find_participant(scenario: dict[str, Any], persona_id: str) -> dict[str, Any]:
    participant = next(
        (p for p in scenario["participants"] if p["persona"] == persona_id), None
    )
    if participant is None:
        taking_part = ", ".join(str(p["persona"]) for p in scenario["participants"])
        raise KeyError(
            f"persona {persona_id!r} does not take part in {scenario['id']!r} "
            f"(participants: {taking_part})"
        )
    return participant


def resolved_budget(persona: dict[str, Any], task: dict[str, Any]) -> int:
    """A task's action budget: its own if it declares one, else the persona's default."""
    declared = task.get("budget_actions")
    return int(declared) if declared is not None else int(persona["resources"]["task_actions"])


def compose_brief(
    personas: dict[str, dict[str, Any]], scenario: dict[str, Any], persona_id: str
) -> dict[str, Any]:
    """The persona-visible projection of one participant's part in one scenario."""
    persona = personas.get(persona_id)
    if persona is None:
        raise KeyError(f"unknown persona id {persona_id!r}")
    participant = find_participant(scenario, persona_id)

    projected = {field: persona[field] for field in PERSONA_BRIEF_FIELDS if field in persona}
    overrides = participant.get("expertise_overrides") or {}
    if overrides:
        # Refused at composition, not only in the guard tests: a brief is what an isolated
        # persona context actually receives, so an illegitimate override must never reach one
        # even if it arrives from an unguarded path.
        forbidden = sorted(set(overrides) - overridable_axes())
        if forbidden:
            raise ValueError(
                f"{scenario['id']}/{persona_id}: expertise_overrides may not restate "
                f"{', '.join(forbidden)} — only situational axes are overridable; a persona "
                "differing on the others is a different persona"
            )
        projected["expertise"] = {**projected["expertise"], **overrides}

    return {
        "scenario": {field: scenario[field] for field in SCENARIO_BRIEF_FIELDS if field in scenario},
        "persona_id": persona_id,
        "persona": projected,
        "context": participant["context"],
        "tasks": [
            {
                **{field: task[field] for field in TASK_BRIEF_FIELDS if field in task},
                "budget_actions": resolved_budget(persona, task),
            }
            for task in participant["tasks"]
        ],
    }


def collect_keys(value: object) -> set[str]:
    """Every mapping key appearing anywhere in a nested structure. The leak guard walks
    a composed brief with this rather than matching field names against rendered prose,
    which would false-positive on ordinary English."""
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key))
            keys |= collect_keys(child)
    elif isinstance(value, list):
        for child in value:
            keys |= collect_keys(child)
    return keys
