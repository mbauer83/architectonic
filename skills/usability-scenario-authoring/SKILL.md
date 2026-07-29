---
name: usability-scenario-authoring
description: >
  Author or revise a persona/scenario usability specification under
  tools/usability_test/ — a new scenario, a new persona, or a change to the shared
  vocabularies. Use this when the user wants to extend usability-test coverage to a work
  type or a channel that is not covered yet. Trigger on phrases like "write a usability
  scenario", "add a persona", "new usability scenario", "cover modelling in the usability
  tests", "add an assurance scenario", "extend the persona catalog", "usability coverage
  for the MCP channel", or any request to describe a target user or a situation for
  usability evaluation.
---

# Authoring a usability scenario

Read `tools/usability_test/README.md` first — it is the specification for these files and
this skill does not repeat it. Read one existing scenario in full before writing a new
one; `impact-analysis-of-a-breaking-change.yaml` is the shortest complete example.

## What goes where

A **persona** is who someone is, independent of any situation. A **scenario** is a
situation and the tasks it puts to the personas in it. If you find yourself writing a
task into a persona or a role description into a scenario, the content is in the wrong
file.

Do not create a new persona for a new scenario by default. Thirteen exist; most new
scenarios are new situations for people who are already described. Add a persona only
when the new role's expertise profile, information strategy or decision strategy differs
structurally from every existing one — not when it differs only in job title.

## Gather before writing

1. **Work type and channel** — one `work_type` from the vocabulary, and the `channels`
   the work is done through. A scenario needing two work types is two scenarios.
2. **The situation** — what happened, when, under what pressure. Written from the world:
   no feature names, no surface names, no product vocabulary. Finding the surface is the
   thing under test, so naming it in the situation destroys the measurement.
3. **The stakes** — what goes wrong if this work is done badly. Be specific about who
   acts on the answer and what they do with it; this is what makes a wrong-but-plausible
   answer scoreable as high severity rather than as a nuisance.
4. **The participants** — which existing personas are in this situation, and for each,
   where they stand in it: what they already know, what they are under pressure from,
   what they have used before. Use `expertise_overrides` for `solution_domain` — the domain
   of the systems this scenario models, which no persona can settle in advance. That axis is
   the only overridable one: the other four describe the person, and restating one would make
   the same persona two different subjects, so findings scored against it would no longer
   compare across runs. A participant who genuinely differs on those axes is a different
   persona — write one, and say in `context` what the situation adds. Composition refuses a
   forbidden override, so an authoring mistake fails loudly rather than reaching a brief.
5. **The tasks** — what each participant needs answered. Reference a standing question
   with `recurring_question:` where the task instantiates one; write a fresh task where
   it does not. Every task states what would count as answered and which concrete
   artifact the answer feeds.
6. **The answer key** — see below.

## Writing the answer key

This is the part that makes a scenario an evaluation rather than a walkthrough, and it is
where scenarios are usually weak.

- **`expected_route.action`** is required on every task. It is both the answer and the
  scoring rule: `execute` is scored on whether the persona picked one of the candidate
  routes, everything else on whether they recognized the *class* of route. Getting this
  wrong inverts the scoring — a task marked `execute` that actually has no shipped answer
  will score every honest persona as a failure.
- **`expected_route.candidates`** are typed references (`gui-route`, `mcp-tool`,
  `viewpoint`, `doc`, `cli`) and are resolved against the real system by the tests. An
  empty list is the correct answer key for a task nothing shipped fits — and is required
  reading for the author, because writing it forces the question "is this really a gap?"
- **`oracle`** is optional but strongly preferred: state the expected answer class, how to
  derive it from *primitive* records, and what must be excluded. An oracle computed by the
  same engine as the subject shares that engine's failure modes; say so explicitly rather
  than claiming independent correctness. Where an exact oracle is infeasible, leave the
  oracle out and let the run derive it, but expect the finding to be exploratory rather
  than confirmed.
- **`preconditions`** must be checkable. "The model has motivation content" is not a
  precondition; "goals and outcomes exist and connect to application elements, verified by
  `artifact_query_list_artifacts` then `find_neighbors` on a sample" is.
- **`invariants`** are the cross-surface consistency properties the scenario can check
  while the personas are working — count agreement, legend coverage, disclosure of
  truncation. Each needs a statement and a verification method.
- **`write_policy`** — `none` unless the tasks genuinely require saving something.
  `run-scoped` needs a namespace, a cleanup helper that exists, and verified restoration;
  for anything other than viewpoints that helper does not exist yet, so a mutating
  scenario over entities or connections is blocked until it is built.

## Style

Keys are snake_case nouns without articles, consistently across every file. Persona list
items are third-person and one concern each. Scenario prose is plain and concrete.
Nothing anywhere references a plan, a phase, a work-unit id or a decision number.

## Before finishing

```bash
uv run pytest tests/common/test_usability_catalog.py \
              tests/common/test_usability_scenarios.py \
              tests/tools/test_usability_helpers.py -q
uv run python tools/usability_test/compose_brief.py --scenario <ID> --persona <ID>
```

Read the composed brief as the persona would. If it reads as though it tells you where to
look, the situation has leaked product vocabulary and needs rewriting. Then confirm no
answer-key text appears in it — the leak test asserts this, but read it once yourself.

Update the coverage table in `tools/usability_test/README.md`, and the roadmap item in
the root `README.md` if a work type or channel has moved from uncovered to covered.
