"""Tests for the safety-critical usability-test helpers: manifest validation and
baseline verification in the cleanup script (must never be able to delete a
pre-existing definition), and the brief composer (the evaluator's answer key must never
leak into a persona brief).

The leak guard is the reason the composer exists. A persona that has seen the expected
route, the oracle or a task's preconditions is no longer measuring anything: it is
reciting. So the guard runs over every (scenario, participant) pair the catalog actually
contains, structurally — on the keys of the composed brief — and then again on the
rendered markdown, matching the answer-key *text* rather than field names, which would
false-positive on ordinary English."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HELPERS_DIR = _REPO_ROOT / "tools" / "usability_test"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, _HELPERS_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


cleanup = _load("cleanup_usability_viewpoints")
inventory = _load("viewpoint_inventory")
catalog = _load("usability_catalog")  # must precede compose_brief, which imports it
composer = _load("compose_brief")

_BASELINE = {
    "definitions": {
        "capability-map": {"tier": "module", "version": 1, "hash": "h1"},
        "my-team-view": {"tier": "engagement", "version": 2, "hash": "h2"},
    },
    "pins": ["capability-map"],
}


class TestValidateTargets:
    def test_accepts_only_run_prefixed_new_slugs(self) -> None:
        manifest = {"run_id": "r1", "created_slugs": ["usability-r1-a", "usability-r1-b"]}
        assert cleanup.validate_targets(manifest, _BASELINE) == ["usability-r1-a", "usability-r1-b"]

    def test_rejects_missing_run_id(self) -> None:
        with pytest.raises(ValueError, match="no run_id"):
            cleanup.validate_targets({"created_slugs": ["usability-r1-a"]}, _BASELINE)

    def test_rejects_slug_outside_run_namespace(self) -> None:
        manifest = {"run_id": "r1", "created_slugs": ["usability-r2-a"]}
        with pytest.raises(ValueError, match="outside this run's namespace"):
            cleanup.validate_targets(manifest, _BASELINE)

    def test_rejects_pre_existing_baseline_slug_even_with_matching_prefix(self) -> None:
        baseline = {
            "definitions": {**_BASELINE["definitions"], "usability-r1-leftover": {"hash": "h3"}},
            "pins": [],
        }
        manifest = {"run_id": "r1", "created_slugs": ["usability-r1-leftover"]}
        with pytest.raises(ValueError, match="existed before the run"):
            cleanup.validate_targets(manifest, baseline)

    def test_rejects_pre_existing_engagement_definition_named_by_malformed_manifest(self) -> None:
        manifest = {"run_id": "r1", "created_slugs": ["my-team-view"]}
        with pytest.raises(ValueError, match="outside this run's namespace"):
            cleanup.validate_targets(manifest, _BASELINE)

    def test_rejects_duplicates_and_non_strings(self) -> None:
        manifest = {"run_id": "r1", "created_slugs": ["usability-r1-a", "usability-r1-a", 7]}
        with pytest.raises(ValueError, match="duplicate"):
            cleanup.validate_targets(manifest, _BASELINE)


class TestVerifyAgainstBaseline:
    def _catalog(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        return {"viewpoints": entries}

    def _entry(self, slug: str) -> dict[str, Any]:
        return {"slug": slug, "name": slug}

    def _baseline_for(self, entries: list[dict[str, Any]], pins: list[str]) -> dict[str, Any]:
        return {
            "definitions": {
                str(e["slug"]): {"hash": cleanup.canonical_hash(e)} for e in entries
            },
            "pins": pins,
        }

    def test_clean_restoration_passes(self) -> None:
        entries = [self._entry("capability-map")]
        baseline = self._baseline_for(entries, ["capability-map"])
        assert cleanup.verify_against_baseline(
            self._catalog(entries), ["capability-map"], baseline, set()
        ) == []

    def test_detects_changed_definition_missing_slug_residual_and_pin_change(self) -> None:
        original = [self._entry("capability-map"), self._entry("my-team-view")]
        baseline = self._baseline_for(original, [])
        mutated = [
            {**self._entry("capability-map"), "name": "renamed"},
            self._entry("usability-r1-leftover"),
        ]
        problems = cleanup.verify_against_baseline(
            self._catalog(mutated), ["new-pin"], baseline, {"usability-r1-leftover"}
        )
        assert any("changed during run" in p for p in problems)
        assert any("missing after cleanup: my-team-view" in p for p in problems)
        assert any("residual test slug: usability-r1-leftover" in p for p in problems)
        assert any("pin list changed" in p for p in problems)

    def test_hashes_agree_between_inventory_and_cleanup(self) -> None:
        entry = self._entry("capability-map")
        assert cleanup.canonical_hash(entry) == inventory.canonical_hash(entry)


def _every_brief() -> list[tuple[str, str, dict[str, Any], str]]:
    """(scenario id, persona id, composed brief, rendered markdown) for every participant
    in every scenario — the guard has to hold over the catalog as it actually is, not
    over a sample."""
    personas = catalog.load_personas()
    composed: list[tuple[str, str, dict[str, Any], str]] = []
    for scenario_id, scenario in sorted(catalog.load_scenarios().items()):
        for participant in scenario["participants"]:
            persona_id = str(participant["persona"])
            brief = composer.compose_brief(personas, scenario, persona_id)
            composed.append((scenario_id, persona_id, brief, composer.render_markdown(brief)))
    return composed


class TestComposeBrief:
    def test_no_answer_key_field_is_ever_a_key_in_a_brief(self) -> None:
        for scenario_id, persona_id, brief, _ in _every_brief():
            leaked = catalog.collect_keys(brief) & catalog.EVALUATOR_ONLY_FIELDS
            assert not leaked, (scenario_id, persona_id, sorted(leaked))

    def test_no_answer_key_text_ever_reaches_the_rendered_brief(self) -> None:
        """Field names are not the risk; the prose behind them is. A persona told what the
        oracle expects has been handed the answer in words."""
        scenarios = catalog.load_scenarios()
        for scenario_id, persona_id, _, rendered in _every_brief():
            scenario = scenarios[scenario_id]
            participant = catalog.find_participant(scenario, persona_id)
            secrets: list[str] = [
                str(entry["statement"])
                for block in ("preconditions", "invariants")
                for entry in (scenario.get(block) or [])
            ]
            for task in participant["tasks"]:
                if "preconditions" in task:
                    secrets.append(str(task["preconditions"]))
                secrets.extend(str(value) for value in (task.get("oracle") or {}).values())
            assert secrets, (scenario_id, persona_id, "nothing to guard — the probe is vacuous")
            for secret in secrets:
                probe = " ".join(secret.split())[:60]
                assert probe not in rendered, (scenario_id, persona_id, probe)

    def test_brief_carries_the_situation_the_context_and_budgeted_tasks(self) -> None:
        personas = catalog.load_personas()
        scenario = catalog.load_scenarios()["impact-analysis-of-a-breaking-change"]
        brief = composer.compose_brief(personas, scenario, "development-lead")
        assert brief["scenario"]["situation"] and brief["context"]
        assert brief["persona"]["expertise"] and brief["persona"]["resources"]["task_actions"] > 0
        assert all(task["budget_actions"] > 0 for task in brief["tasks"])
        assert all(
            {"id", "text", "information_need", "decision_artifact"} <= task.keys()
            for task in brief["tasks"]
        )

    def test_participant_expertise_overrides_reach_the_brief(self) -> None:
        """An override exists because one axis cannot be settled by a persona: `solution_domain`
        names the domain of whatever is modelled. A brief that dropped it would tell the
        participant they are at home in a domain this situation never put them in."""
        personas = catalog.load_personas()
        scenario = catalog.load_scenarios()["impact-analysis-of-a-breaking-change"]
        brief = composer.compose_brief(personas, scenario, "product-owner")
        assert brief["persona"]["expertise"]["solution_domain"] == "aware"
        assert personas["product-owner"]["expertise"]["solution_domain"] == "fluent"

    def test_an_override_of_a_person_axis_is_refused_at_composition(self) -> None:
        """Refused where the brief is built, not only in the catalog guards: this is the last
        point before an isolated persona context receives it."""
        personas = catalog.load_personas()
        scenario = catalog.load_scenarios()["impact-analysis-of-a-breaking-change"]
        tampered = json.loads(json.dumps(scenario))
        participant = next(p for p in tampered["participants"] if p["persona"] == "product-owner")
        participant["expertise_overrides"] = {"software_engineering": "authority"}
        with pytest.raises(ValueError, match="may not restate software_engineering"):
            composer.compose_brief(personas, tampered, "product-owner")

    def test_unknown_persona_and_non_participant_fail_loudly(self) -> None:
        personas = catalog.load_personas()
        scenario = catalog.load_scenarios()["impact-analysis-of-a-breaking-change"]
        with pytest.raises(KeyError, match="unknown persona"):
            composer.compose_brief(personas, scenario, "no-such-persona")
        with pytest.raises(KeyError, match="does not take part"):
            composer.compose_brief(personas, scenario, "enterprise-architect")
