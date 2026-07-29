# The method — one persona/scenario usability run, end to end

The full staged method behind the `usability-scenario-run` skill. Read `SKILL.md` beside
this file first; it is the short form and names the mistakes that invalidate a run. Read
`harness-setup.md` for the role-to-model matrix and how to spawn isolated contexts.

What a run produces: a staged expert inspection of the surfaces one scenario exercises,
and an actionable, evidence-classified findings report. Persona behaviour is generated in
**isolated contexts** and reported as *synthetic-persona hypotheses*; system correctness
claims are grounded in **independent task oracles** and in DOM, API or tool-payload
evidence.

The method is parameterized by a scenario. `uv run python
tools/usability_test/compose_brief.py --list` names the scenarios and their participants;
`tools/usability_test/README.md` is the specification for the catalog. Read that and the
scenario file in full before starting.

**You are the ORCHESTRATOR/EVALUATOR.** You see this whole file and the whole scenario
file. Persona work happens in fresh subagent contexts that receive ONLY their composed
brief — never this file, never the scenario file, never oracles or expected routes,
never another persona's results. If you cannot spawn isolated contexts, you MUST
downgrade every persona-behaviour output (route selection, lostness, abandonment, steps,
time to first useful result) to "contaminated — hypothesis only" and say so in the
report.

---

## 1. Environment, safety, and the run manifest

- Backend `http://127.0.0.1:8000`; frontend `http://localhost:5173` for GUI scenarios.
  **Never restart, stop, or spawn backend or frontend instances.** If either is down,
  stop and ask the user. Freeze source and model changes for the whole run: if
  `git status` or the scenario's subject matter changes unexpectedly mid-run, abort and
  ask.
- **RUN_ID**: generate once. Create the run directory up front:
  `mkdir -p test-results/usability/<RUN_ID>/logs`.
- **Write policy comes from the scenario**, from its `write_policy` block.
  - `mutations: none` — no repository state may change at all. Verify this at the end
    the same way a mutating run verifies restoration.
  - `mutations: run-scoped` — every created artifact's slug MUST begin with the
    scenario's `slug_prefix` with `<RUN_ID>` substituted. Before every save, re-read the
    identifier field and verify the prefix; a Save-As suggestion like `<slug>-copy` is
    not prefixed and must be corrected before saving. Record every successful create in
    `test-results/usability/<RUN_ID>/run-manifest.json` as
    `{"run_id": "<RUN_ID>", "created_slugs": [...]}` **immediately after each save**, not
    at the end.
  - Under either policy: never edit or delete anything that existed before the run —
    including leftovers from earlier runs, which are reported and left alone. Never write
    entities, connections, diagrams, documents, groups, or module and enterprise files
    unless the scenario's write policy explicitly permits it. Pin and curation state is
    never mutated.
- **Run manifest** — write to `test-results/usability/<RUN_ID>/environment.json` in S0:
  commit SHA, `git status --porcelain`, `git diff HEAD --binary | sha256sum`, sha256 of
  every pre-existing untracked file under `engagements/` and `spec/`, the model's
  `index_generation`, browser viewport (GUI scenarios), the model identity and effort of
  every role, persona execution order, timestamps, and the S0 preflight results.
- **Worktree restoration check (S6)**: after cleanup, re-run the same captures. The ONLY
  permitted differences are `test-results/usability/<RUN_ID>/**` and the run's report.
  Any other changed path, tracked or untracked, is a failed restoration — stop and ask.
- Helper scripts (`uv run python …`):
  - `tools/usability_test/compose_brief.py --scenario <ID> --persona <ID>` — the only
    sanctioned brief composition path.
  - `tools/usability_test/viewpoint_inventory.py --baseline <FILE>` — catalog rows plus a
    restoration checksum. Run FIRST in S0 for any scenario whose write policy creates
    viewpoints.
  - `tools/usability_test/execution_probe.py SLUG [--param k=v] [--limit N] [--out FILE]`
    — full raw execution and projection with provenance. Oracle input and invariant
    evidence for viewpoint executions.
  - `tools/usability_test/cleanup_usability_viewpoints.py --manifest <FILE> --baseline
    <FILE> [--apply]` — deletes ONLY manifest-listed, run-prefixed slugs absent from the
    baseline, then verifies the catalog and pins are byte-identical to baseline. Any
    verification failure: stop and ask; never improvise repairs.

## 2. Evidence classes (mandatory on every finding, metric and claim)

- **Observed system fact** — API, DOM, tool-payload or model evidence attached. May be
  reported as confirmed.
- **Expert inspection finding** — evaluator judgement citing a named principle. May be
  reported as an inspection finding.
- **Synthetic-persona hypothesis** — role-specific behaviour produced by an LLM persona.
  MUST be labelled as requiring human confirmation and never presented as measured
  usability. This covers every route-selection rate, lostness figure, abandonment,
  confidence and vocabulary finding.
- **Human-confirmed finding** — none will exist in a synthetic session; the class exists
  so the report's schema survives a later human round.

Terminology discipline: metrics are "ISO-9241-11-informed synthetic task descriptors",
not usability measurements. No satisfaction or adoption claims. Persona "quotes" are
illustrative simulated utterances and are not evidence.

## 3. Independent task oracles (S0A — the truth layer)

Before any persona runs, expand each task's `oracle` block into an evaluator-only row:

`task id | preconditions (verified how) | expected answer class | exact expected
identifiers or a defined set query | required relationship or path properties | known
exclusions | acceptable alternative routes | expected_route.action | derivation method |
index_generation at derivation`

Derivation independence is a property of the *evaluation implementation*, not of the
wording. Derive expected sets from **primitive artifact and connection records** —
`artifact_query_search_artifacts`, `artifact_query_find_neighbors`,
`artifact_query_find_connections_for`, `artifact_query_list_artifacts` — with a traversal
you specify yourself. Probing a different view through the same evaluator is
corroborating evidence only: two results sharing a derivation engine share its failure
modes, so record the dependency and do not claim independent correctness. For
path-completeness questions preserve the **witness paths and relationship semantics**,
not just endpoint sets. For coverage questions enumerate the exact expected set. Where an
exact oracle is infeasible, mark the task **exploratory**: its adequacy may be discussed,
but silent-incompleteness claims may not be stated as confirmed. Store the rows in
`test-results/usability/<RUN_ID>/oracles.json`; no persona context ever receives them.

**Fixture preflight** (part of S0A): verify every scenario-level and task-level
precondition. A failed precondition marks the task **fixture-invalid** — run it only as a
catalog-honesty observation ("does the product communicate that the data is not there?"),
never as a usability failure of the interface.

## 4. Personas and the isolation protocol

Compose every brief with `tools/usability_test/compose_brief.py`. Never compose one by
hand, and never pass a scenario file to a persona.

- Each persona runs in a **fresh, zero-history subagent context** — a new spawn whose
  prompt you author, never a fork or continuation that inherits this conversation. It
  receives only: the composed brief, the surface it works through, permission to read
  `README.md` and `docs/`, the failure decision table (§6), the recording contract (§7),
  and the run-prefix rule for anything it saves.
- Choose the runner by the scenario's channel: `usability-persona-gui` for `gui`,
  `usability-persona-mcp` for `mcp`. Each agent's tool allowlist — not its prompt text —
  is what enforces the channel and the no-mutation rule. Model and effort come from the
  agent definitions and must NOT be overridden at spawn time; uniformity across personas
  is a validity requirement, because a mid-run model change breaks every cross-persona
  comparison.
- Browser state between GUI personas: navigate to the frontend origin FIRST, clear that
  origin's `localStorage` and `sessionStorage`, then navigate away. Clearing from
  `about:blank` cannot touch the app origin. Note in the report that full profile
  isolation is approximated, not guaranteed. MCP personas in separate subagent contexts
  carry no state between runs.
- **S1 contexts receive the navigation surface only** — the catalog or tool list, and the
  documentation index — and must return a ranked pick list per task, including the
  explicit option "nothing here fits; I would <build my own / fork the closest / look in
  the documentation / conclude the data or the feature does not exist>". No execution.
- Where a scenario's answer key permits a **blinded aggregate** of other personas' S1
  picks (chosen routes and confidence, no identities, no correctness), that is the only
  cross-persona material any brief may carry.
- Where a scenario grants a persona a post-task verification phase, it happens as a
  separate follow-up message to the same agent AFTER its navigation tasks are complete —
  never before, and never during navigation measurement.
- Every persona returns a structured task log (§7) as its final output; persist it under
  `test-results/usability/<RUN_ID>/logs/`.

## 5. Stages

Each stage writes its artifact; each can run in a fresh context; the report is assembled
only from artifacts, never from memory.

- **S0 — Baseline and manifest**: baselines for whatever the write policy can touch,
  `environment.json`, a check that the entry surface loads without errors, and a
  report-only note of any leftovers from earlier runs.
- **S0A — Oracles and preflight** (§3): `oracles.json` plus the fixture-validity table.
- **S1 — Blind route selection**: one isolated context per participant, ranked picks or
  "no fit, and here is what I would do instead" per task. Score afterwards, action-aware:
  route hits only for `execute` tasks, route-class recognition for every other action.
  All labels are synthetic hypotheses. After S1, finalize the shortest-path baseline
  **per persona-chosen route** before any S2 context starts.
- **S2 — Task execution**: a fresh context per participant. Each S2 brief includes that
  persona's OWN S1 ranked list and confidence, labelled "your prior selections" — nothing
  else from S1, no scores, no routes, no other personas. The persona executes its
  selections, interprets the result in character, and produces the task's
  `decision_artifact` as real content: an actual slide bullet list, ticket text, evidence
  table or proposed delta. Afterwards you re-run the same executions yourself, judge
  adequacy **against the oracle** rather than against impressions, and record every
  interface-versus-engine consistency pair.
- **S3 — Authoring**: any task whose `expected_route.action` is `author` or `fork`, under
  the same isolation. Manifest every save as it happens; verify each saved artifact
  independently; for forks, verify the source's canonical hash is unchanged.
- **S4 — Invariants and matched comparisons**:
  - **Invariant matrix**: for each invariant in the scenario, execute the stated check
    with a fixed input and index generation, and record `invariant | input | generation |
    surfaces | expected pair | evidence | pass/fail`.
  - **Matched comparison suite** (this is what controls confounding): the same query
    rendered through each representation the scenario touches; the same question asked
    anchored and as an equivalent filter; fixed limits producing a small result, a large
    result and a truncated one; one existing definition forked unchanged and compared;
    one artifact built by forking and the same one built from blank. Only these matched
    cells support variance claims; everything else is a cross-case observation.
  - **Heuristic passes**: TWO fresh evaluator contexts, blind to your findings so far and
    deliberately of different model classes (`usability-heuristic-reviewer-a` and
    `-b`), each sweeping the scenario's surfaces against Nielsen's ten with anchored
    severities (0 none, 1 cosmetic, 2 minor, 3 major or blocks a subtask, 4 blocks the
    task or corrupts understanding) and a justification per violation. Consolidate and
    de-duplicate. Label the exercise "independent expert passes (n=2, two model classes)".
- **S5 — Findings, FMEA and recommendations** (§8).
- **S6 — Synthesis and cleanup**: assemble the report from artifacts; run cleanup if the
  write policy was `run-scoped`; then the whole-worktree restoration check from §1.
  Verification failure at either level: stop and ask. The report states both results.

## 6. Failure decision table (include verbatim in every persona brief)

- API or interface failure — crash, 4xx/5xx, partial render, console exception, tool
  error: capture the evidence, retry ONCE with identical inputs, then mark the task
  **blocked** and move on. Never reload-loop; never restart anything.
- Empty but successful result: record it with its evidence BEFORE any next action; then
  you may try your next-ranked candidate if your budget allows.
- Validation error or blocked save while authoring: record the message verbatim, make ONE
  correction attempt, then stop the task as a **validation dead end**. Never bypass via
  an API or the filesystem.
- Execute at most your top two ranked routes per task, within the task's action budget.
  When the budget is exhausted, abandon and say why in one sentence. Abandoning is a
  legitimate outcome and is recorded as one.
- Anything that looks like data changing underneath you: stop and report immediately.

## 7. Recording contract (persona output)

One JSON or YAML object per task:

`run_id, scenario, persona, task_id, started/finished (ordinal steps, not wall clock),
actions[] (ordinal, kind ∈ {click, type+submitted-text, select, navigate, tab-switch,
tool-call}, target, resulting page/panel/payload), surfaces_visited[] (unique and
revisits), dead_ends[] (what was tried and why rejected), errors[] (and whether recovery
was self-served), outcome ∈ {success, partial, fail, abandoned, blocked,
validation-dead-end, fixture-invalid}, result_ref, adequacy_claim (fully/partially/no,
and what is missing), confidence (act-on-it / verify-first / no),
decision_artifact_content (the actual artifact), simulated_utterance (illustrative only),
deviation_notes`.

Fixed definitions: an **action** is one click, one submitted text entry, one selection,
one navigation, one tab or panel switch, or one tool call. **N** = unique surfaces
visited, **S** = shortest path for the persona's CHOSEN route (finalized by you after S1,
before that persona's S2 context starts), **R** = total visits including revisits;
lostness L = sqrt((N/S−1)² + (R/N−1)²), reported only as a synthetic descriptor. Budgets
are counted in these ordinal actions, never in wall-clock minutes.

Evidence protocol: everything under `test-results/usability/<RUN_ID>/`; screenshots named
`<persona>-<task>-<step>-<surface>.png`; an `evidence.csv` mapping task, action ordinal,
URL or tool call, artifact path and the claim it supports. Capture task start, every
failure and decision point, the final result, and any recovery — not every click.

## 8. Findings register, FMEA and recommendations

Register row: `ID | Surface | Title | Evidence class | Evidence refs | Reproduced?
(yes/once/predicted) | Personas plausibly affected (hypothesis) | Heuristic | Failure mode
| Effect | Cause | Current control or detection cue | S | O | D | Confidence | Action
Priority | Recommendation`.

Anchored FMEA, scoring observed and predicted modes separately:

- **S** severity: 1 cosmetic; 3 slows a task; 5 the task fails but the user knows; 7 a
  wrong or incomplete answer the user may notice; 9–10 the user confidently acts on a
  wrong answer, or repository state is corrupted.
- **O** occurrence: rate task **exposure** — how often the triggering situation arises (1
  exotic, 5 a common task variant, 9 nearly every session) — and mark the frequency
  `observed n/N | estimated | unknown`. Never infer a frequency from one synthetic run.
- **D** non-detectability: the likelihood the user and the existing cues FAIL to notice
  before acting. 1 obvious error state; 5 noticeable only with attention; 9–10 silently
  plausible, with nothing distinguishing wrong from right.
- **Action Priority** replaces RPN ranking: High = S≥9 always, or S≥7 with (O≥5 or D≥7);
  Medium = S 5–8 with moderate O and D; Low = the rest. RPN may be reported as a secondary
  sort only. Calibrate first: score three sample findings, have ONE fresh context
  (`usability-fmea-calibrator`) score the same three blind, adjudicate the differences,
  then score the rest.

Every recommendation carries: the named best practice; the circumstances in which it does
NOT apply; the function, process, object or event concerned, named concretely enough to
open a ticket from; and the triage fields `owner-component, dependencies, estimate-band
(S/M/L) with confidence, validation test`. Effort bands are estimates, not commitments.

## 9. Report

Write to `REPORT-usability-<SCENARIO_ID>-<RUN_ID>.md`:

1. Executive summary (≤1 page): top findings by Action Priority, and an explicit
   statement of what the session CAN claim — system facts and inspection findings —
   against what needs human confirmation.
2. Method as executed, deviations log, isolation fidelity statement, run manifest
   reference.
3. Oracle table and fixture-validity results.
4. Route selection (S1), labelled synthetic hypothesis.
5. Per-persona task records with the decision-artifact content and oracle-based adequacy
   judgements.
6. Authoring study; matched comparison suite; variance analysis over matched cells only,
   with cross-case observations kept separate; invariant matrix with evidence.
7. Heuristic consolidation (n=2 passes).
8. Findings register and FMEA, observed and predicted separated.
9. Recommendations by Action Priority; within High, quick wins against substantial
   against strategic, with triage fields.
10. Limitations — synthetic personas, single-model evaluator, fixture gaps, scenario scope
    — and the shortlist of hypotheses that most deserve a small human-validation round.
11. Cleanup and verified-restoration statement, at both catalog and worktree level.

**Acceptance.** The report is labelled "complete" only if every participant ran every
stage the scenario calls for. Otherwise it is "partial": name what was cut in the
deviations log, and make no holistic-coverage claims. A partial report is still useful; a
partial report presented as complete is not.

## Sequencing

S0 → S0A → S1 (all participants) → S2 → S3 → S4 → S5 → S6. Stages are resumable: on
context exhaustion, finish the current artifact, then continue from the artifacts in a
fresh session — never from memory.
