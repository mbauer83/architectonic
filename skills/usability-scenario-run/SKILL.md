---
name: usability-scenario-run
description: >
  Execute and evaluate a persona/scenario usability run against the platform, or resume
  and report on one already in progress. Use this when the user wants to test the product
  with personas, run a usability evaluation of the GUI or the MCP surface, score how well
  a surface answers a target user's question, or produce a findings report with FMEA
  ratings. Trigger on phrases like "run the usability test", "run a usability scenario",
  "test this with personas", "usability evaluation", "persona stress test", "score the
  scenario", "usability findings report", "resume the usability run", or a request naming
  a scenario id from tools/usability_test/scenarios/.
---

# Running a usability scenario

The full staged method is `method.md` beside this file, and the harness setup — the
role-to-model matrix, and how to spawn isolated contexts on Claude Code or Codex — is
`harness-setup.md`. **Read both in full before starting.** This file exists to get the run
set up correctly and to stop the three mistakes that invalidate one.

## Before anything else

```bash
uv run python tools/usability_test/compose_brief.py --list
uv run pytest tests/common/test_usability_catalog.py \
              tests/common/test_usability_scenarios.py \
              tests/tools/test_usability_helpers.py -q
```

If the guard tests fail, the answer key is stale — fix that before running, not after.
Then confirm the backend is up on `:8000` on current code, and, for a GUI scenario, the
frontend on `:5173`. **Never start, stop or restart either.** If one is down, stop and ask
the user.

Read the scenario file in full. It tells you the channel (which persona runner to spawn),
the write policy (whether cleanup is needed at all), the preconditions to preflight, the
surfaces to inspect, and the invariants to check.

## The three mistakes that invalidate a run

1. **Contaminating a persona.** A persona context sees its composed brief and nothing
   else — never the scenario file, never the prompt, never the oracles, never another
   persona's results, never your own findings. Spawn a fresh agent per persona per stage;
   never a fork, never a continuation. Compose every brief with `compose_brief.py`; never
   by hand. If you cannot spawn isolated contexts, every persona-behaviour claim in the
   report must be downgraded to "contaminated — hypothesis only".
2. **Confusing an oracle with a second opinion.** Derive expected answers from primitive
   artifact and connection records with a traversal you specify yourself. Running a second
   view through the same engine is corroboration, not independence: record the shared
   dependency and do not claim independent correctness.
3. **Presenting synthetic behaviour as measurement.** Route-hit rates, lostness,
   abandonment, confidence and vocabulary findings are synthetic-persona hypotheses and
   must be labelled as needing human confirmation. Only API, DOM, tool-payload and model
   evidence may be reported as confirmed. No satisfaction or adoption claims, ever.

## Spawning personas

Use `subagent_type: "usability-persona-gui"` or `"usability-persona-mcp"` by channel.
Their tool allowlists — not their prompts — enforce no-writes and no-source-reading. Never
override model or effort at spawn time: uniformity across personas is what makes them
comparable, and a mid-run change invalidates every cross-persona statement.

Pass each persona: its composed brief, the surface it works through, the failure decision
table (§6 of `method.md`), the recording contract (§7), the run-prefix rule if it may save
anything, and — from the second stage onwards — that persona's *own* prior selections and
nothing else from any other persona.

Between GUI personas, navigate to the frontend origin, clear that origin's storage, and
navigate away. Record in the report that browser isolation was approximated.

## Scoring

Score a task by its `expected_route.action`, not by whether the persona found something.
For `execute`, score the route hit. For every other action, score whether the persona
recognized the route class: "nothing here fits, I would build it" on an `author` task is a
hit, and a confident near-fit pick on a `recognize-product-gap` task is a false scent.

Judge adequacy against the oracle, never against how convincing the persona's own account
was. A persona that produced a plausible answer from a wrong result is the most severe
finding class the framework has.

Preflight every precondition first. A task whose preconditions fail is **fixture-invalid**:
run it only to observe whether the product communicates that the data is not there, and
never score it as an interface failure.

## Finishing

Assemble the report only from the artifacts under `test-results/usability/<RUN_ID>/`,
never from memory — stages are resumable precisely because of this. If the write policy
was `run-scoped`, run the cleanup helper with both `--manifest` and `--baseline`, then the
whole-worktree restoration check. Any verification failure at either level: stop and ask
the user; never improvise a repair.

State honestly whether the run was complete or partial, and name in the deviations log
everything that was cut. A partial report is useful; a partial report presented as
complete is not.
