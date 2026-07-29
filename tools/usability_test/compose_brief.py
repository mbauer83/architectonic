"""Compose an isolated persona brief for one participant in one usability scenario.

The ONLY sanctioned way to build a brief. It projects through the allowlists in
usability_catalog.py, so the evaluator's answer-key material can never reach a persona
context by a manual-composition mistake. Never compose a brief by hand.

Usage:
  python tools/usability_test/compose_brief.py --list
  python tools/usability_test/compose_brief.py --scenario SCENARIO_ID --persona PERSONA_ID [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from usability_catalog import (  # type: ignore[import-not-found]
    compose_brief,
    load_personas,
    load_scenarios,
)

_HEADINGS: dict[str, str] = {
    "role": "Who you are",
    "expertise": "What you know, and how well",
    "capabilities": "What you can do unaided",
    "literacies": "What you read fluently",
    "boundaries": "What you will not do",
    "focus": "What you care about",
    "channels": "How you work",
    "information_strategy": "How you find things out",
    "decision_strategy": "How you decide",
    "resources": "What you can spend",
    "recurring_questions": "Questions you always carry",
}


def _render_value(value: object, indent: str = "") -> list[str]:
    """Nested mappings become nested bullets; scalars and lists of scalars stay inline."""
    if isinstance(value, dict):
        lines: list[str] = []
        for key, child in value.items():
            label = str(key).replace("_", " ")
            if isinstance(child, (dict, list)):
                lines.append(f"{indent}- {label}:")
                lines.extend(_render_value(child, indent + "  "))
            else:
                lines.append(f"{indent}- {label}: {_flatten(child)}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                lines.append(f"{indent}-")
                lines.extend(_render_value(item, indent + "  "))
            else:
                lines.append(f"{indent}- {_flatten(item)}")
        return lines
    return [f"{indent}{_flatten(value)}"]


def _flatten(value: object) -> str:
    return " ".join(str(value).split())


def _render_recurring_questions(questions: list[dict[str, Any]]) -> list[str]:
    """These are the persona's standing questions, not the scenario's tasks — rendered as
    prose so they read as character rather than as a second, competing task list."""
    lines: list[str] = []
    for question in questions:
        lines.append(f"- {_flatten(question['text'])}")
        lines.append(
            f"  (answered by: {_flatten(question['information_need'])} "
            f"— feeding a {question['decision_artifact']})"
        )
    return lines


def render_markdown(brief: dict[str, Any]) -> str:
    scenario = brief["scenario"]
    persona = brief["persona"]
    lines = [
        f"# {persona['name']} — {scenario['title']}",
        "",
        "## The situation",
        "",
        _flatten(scenario["situation"]),
        "",
        "## What is at stake",
        "",
        _flatten(scenario["stakes"]),
        "",
        "## Where you are in it",
        "",
        _flatten(brief["context"]),
        "",
        "## You",
        "",
    ]
    for field, heading in _HEADINGS.items():
        if field not in persona:
            continue
        lines.append(f"### {heading}")
        if field == "recurring_questions":
            lines.extend(_render_recurring_questions(persona[field]))
        else:
            lines.extend(_render_value(persona[field]))
        lines.append("")

    lines.extend(["## Your tasks", ""])
    for task in brief["tasks"]:
        lines.append(f"### {task['id']}")
        lines.append("")
        lines.append(_flatten(task["text"]))
        lines.append("")
        lines.append(f"- What counts as answered: {_flatten(task['information_need'])}")
        lines.append(f"- The answer must feed a: {task['decision_artifact']}")
        lines.append(
            f"- Action budget: {task['budget_actions']} actions (one click, one submitted "
            "text entry, one selection, one navigation, or one tab or panel switch). "
            "When the budget is exhausted, abandon the task and say why in one sentence."
        )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _print_listing() -> None:
    personas = load_personas()
    for scenario_id, scenario in sorted(load_scenarios().items()):
        channels = ", ".join(scenario["channels"])
        print(f"{scenario_id}  [{scenario['work_type']} | {channels}]")
        for participant in scenario["participants"]:
            persona_id = str(participant["persona"])
            name = personas[persona_id]["name"]
            print(f"    {persona_id:<32} {name} — {len(participant['tasks'])} task(s)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", help="scenario id (= scenario file stem)")
    parser.add_argument("--persona", help="persona id, as declared in the persona catalog")
    parser.add_argument("--list", action="store_true", help="list scenarios and their participants")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    args = parser.parse_args()

    if args.list:
        _print_listing()
        return
    if not args.scenario or not args.persona:
        parser.error("--scenario and --persona are both required (or use --list)")

    scenarios = load_scenarios()
    scenario = scenarios.get(args.scenario)
    if scenario is None:
        print(f"unknown scenario {args.scenario!r}; known: {', '.join(sorted(scenarios))}",
              file=sys.stderr)
        raise SystemExit(1)
    try:
        brief = compose_brief(load_personas(), scenario, args.persona)
    except KeyError as exc:
        print(str(exc).strip("\"'"), file=sys.stderr)
        raise SystemExit(1) from exc

    print(json.dumps(brief, indent=2) if args.json else render_markdown(brief))


if __name__ == "__main__":
    main()
