# Persona and scenario usability framework

This directory holds the *material* for persona-based usability evaluation of the
platform: who the target users are, what situations they meet the product in, what a
correct answer to each of their questions would have been, and the scripts that compose
briefs and restore the repository afterwards. **This file is the specification for that
material** — what each field means and what makes a good one.

The *method* lives with the skills that use it:

- `skills/usability-scenario-run/` — executing and evaluating a run: `SKILL.md` for the
  setup and the mistakes that invalidate one, `method.md` for the full staged method,
  `harness-setup.md` for the role-to-model matrix and the Claude Code and Codex harnesses.
- `skills/usability-scenario-authoring/` — writing or revising a scenario, a persona or a
  vocabulary, against the specification below.

## The catalog

| File | What it is |
|---|---|
| `vocabularies.yaml` | Every controlled vocabulary, with a definition per term. Personas, scenarios and the guard tests all resolve against it, so extending a vocabulary is a data change. |
| `personas.yaml` | Situation-independent role descriptions. A persona says who someone is, what they can do, how they gather information and decide, what they can spend, and which questions they carry into every situation. |
| `scenarios/*.yaml` | One file per scenario. A scenario is a state of affairs plus, for each participating persona, their position in it and the tasks it puts to them — together with the evaluator's answer key. |

## The scripts

| File | What it does |
|---|---|
| `compose_brief.py` | Composes a persona brief for one participant in one scenario. The only sanctioned composition path. |
| `usability_catalog.py` | Loads the catalog and holds the allowlists the composer projects through. |
| `viewpoint_inventory.py` | Snapshots the viewpoint catalog and writes the restoration checksum a run is verified against. |
| `execution_probe.py` | Full raw viewpoint execution and projection with provenance — oracle input and invariant evidence. |
| `cleanup_usability_viewpoints.py` | Deletes only the viewpoints a run created, then verifies the catalog and pins are byte-identical to the pre-run baseline. |
| `codex-profiles.toml` | Codex CLI profiles for the role-to-model matrix. |

The split is the point. A persona is written once and appears in many scenarios without
being rewritten; a scenario names the situation once and several personas meet it from
their own angle. Neither artifact contains the other's content: personas hold no tasks
and no answer keys, scenarios hold no role descriptions.

## What a persona says

Expertise is graded per axis — `none`, `aware`, `working`, `fluent`, `authority` —
across architecture modelling, the solution domain, software engineering, assurance and
compliance, and this product. That replaces the single expert/non-expert flag of the
first iteration, which asked the wrong question: the interesting personas are exactly
the ones who are an authority in their own field and a beginner at architecture
modelling, and one boolean cannot say that about anybody.

One of those axes is not the persona's to settle. `solution_domain` names the domain of
**whatever a scenario models**, so a persona can only carry a default for it — the value
that holds when the modelled systems are of the kind they usually work on. A scenario
states the real one for its own situation through `expertise_overrides`, and the
vocabulary marks the axis `overridable: true` to say so.

The other four are properties of the person and are marked `overridable: false`. A
scenario that could restate one would make the same persona two different subjects, and
findings scored against it would stop being comparable between runs — which is the whole
value of a fixed catalog. Someone who differs on those axes is a different persona: write
one. `usability_catalog.compose_brief` refuses such an override rather than projecting it,
because a brief is what an isolated persona context actually receives.

`product_familiarity` is familiarity with the product under evaluation — this architecture
repository — and never skill at product work. It was `product_usage`, which read as the
latter; *usage* was the word doing the damage.

Information-gathering and decision-making are separate structured blocks rather than one
prose paragraph, because they fail separately: a persona can find the right surface and
then decline to trust it, or trust the first thing it finds without looking further.

Budgets are **ordinal actions** — one click, one submitted text entry, one selection, one
navigation, one tab or panel switch. Never minutes: a synthetic run has no wall clock,
and a simulated one measures nothing. `session_shape` is narrative colour for the
persona context and carries no measurement weight.

## What a scenario says

Persona-visible: `id`, `title`, `situation`, `stakes`, `channels`, each participant's
`context`, and each task's `id`, `text`, `information_need`, `decision_artifact` and
`budget_actions`.

Evaluator-only, and never composed into a brief: `work_type`, `write_policy`,
`preconditions`, `surfaces`, `invariants`, and each task's `preconditions`,
`expected_route` and `oracle`. Of these, a task's `preconditions` and `oracle` are
optional — a scenario may instead leave the oracle to be derived at run time, as the
migrated viewpoint scenario does — but `expected_route` is not: a task with no answer key
cannot be scored.

`expected_route.action` is the answer key and also decides how the route is scored.
Route-hit scoring applies only to `execute`, because only there does a specific existing
surface constitute the correct answer. For every other action — `author`, `fork`,
`consult-docs`, `recognize-fixture-gap`, `recognize-product-gap` — the question is
whether the persona recognized the class of route at all. A confident near-fit pick on a
`recognize-product-gap` task is a false scent; "nothing here fits, I would build it" on
an `author` task is a hit.

`expected_route.candidates` are typed references, and every one of them is resolved
against the running system by `tests/common/test_usability_scenarios.py`:

| kind | resolved against |
|---|---|
| `gui-route` | the paths in `tools/gui/src/ui/router/index.ts` |
| `mcp-tool` | the tools registered on the four MCP servers |
| `viewpoint` | the slugs in the shipped viewpoint library |
| `doc` | files under `docs/` |
| `cli` | the console scripts in `pyproject.toml` |

A renamed route, a retired tool or a moved documentation page therefore fails the test
suite rather than quietly rotting the answer key.

## Composing a brief

```bash
uv run python tools/usability_test/compose_brief.py --list
uv run python tools/usability_test/compose_brief.py \
    --scenario impact-analysis-of-a-breaking-change --persona development-lead
```

This is the only sanctioned way to build a brief. It projects through the allowlists in
`tools/usability_test/usability_catalog.py`, so answer-key material cannot reach a
persona context through a composition mistake. Never compose one by hand, and never hand
a persona context a scenario file.

## Adding a scenario

1. Pick one `work_type` and the `channels` it is worked through. A scenario that needs
   two work types is two scenarios.
2. Write the `situation` and `stakes` from the world, not from the product — no feature
   names, no surface names. The scenario says what happened and what is at risk; finding
   the surface is the thing under test.
3. For each participating persona, write their `context` — where they stand in this
   situation, what they already know, what pressure they are under — and their tasks.
   Reference a persona's standing question with `recurring_question:` where the task is
   an instance of one; write a scenario-specific task where it is not.
4. Write the answer key: `preconditions` that preflight can verify, the `surfaces` the
   scenario exercises, `invariants` worth checking, and per task an `expected_route` and,
   where you can state one in advance, an `oracle`. Derive the oracle from primitive
   records — an oracle computed by the same engine as the subject shares its failure
   modes, and that dependency has to be recorded rather than glossed.
5. Set `write_policy`. `none` needs no cleanup. `run-scoped` requires a namespace, a run
   manifest recorded as writes happen, and verified restoration against a pre-run
   baseline — and, for anything other than viewpoints, a cleanup helper that does not yet
   exist.
6. Run the gates. `tests/common/test_usability_catalog.py` and
   `tests/common/test_usability_scenarios.py` check structure, vocabulary and every route
   reference; `tests/tools/test_usability_helpers.py` checks that no answer key can reach
   a brief.

## Scenario coverage

| Scenario | Work type | Channel |
|---|---|---|
| `impact-analysis-of-a-breaking-change` | impact analysis | GUI |
| `design-question-answered-from-the-model` | information provision | MCP |
| `viewpoint-catalog-fit-and-authoring` | information provision | GUI |

Modelling, implementation guidance, decision support and the assurance methods are not
yet covered, and neither is any mixed-channel scenario in which a human and a delegated
agent work the same situation from different surfaces. Extending the coverage is a
tracked roadmap item; the framework is the part that had to exist first.
