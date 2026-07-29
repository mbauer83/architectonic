# Executing a usability run — harness setup

How to set up either harness to run `method.md` for one scenario, with the intended mixed
model-class and reasoning-effort assignment, on either harness. The role-to-model matrix
is the same everywhere:

| Role | Claude family | GPT-5.6 family | Effort | Isolation mechanism |
|---|---|---|---|---|
| Orchestrator / evaluator | Fable 5 | Sol | high (xhigh for the oracle and synthesis stages) | main session |
| ALL persona contexts | Opus 4.8 | Terra | medium — **uniform across personas, never varied** | fresh subagent / fresh process |
| Heuristic pass A | Fable 5 | Sol | high | fresh subagent / fresh process |
| Heuristic pass B | Opus 4.8 | Terra | high | fresh subagent / fresh process |
| FMEA calibration scorer | Opus 4.8 | Terra | high | fresh subagent / fresh process |
| Sonnet 5 / Luna tier | — | — | — | mechanical glue only; never personas or judgement |

Record the exact model identity per role in `environment.json` (the run manifest requires
it). Model uniformity across personas is a validity requirement, not a preference: a
mid-run model change breaks every cross-persona comparison.

Prerequisites (both harnesses): the backend on `:8000` **restarted on current code**; for
GUI scenarios, the frontend dev server on `:5173` and Playwright browser automation; for
MCP scenarios, the read MCP servers reachable by the persona harness. The scenario file,
`personas.yaml`, `vocabularies.yaml`, the helper scripts and this directory's configs must
be consistent with each other — `uv run pytest tests/common/test_usability_catalog.py
tests/common/test_usability_scenarios.py tests/tools/test_usability_helpers.py` checks
exactly that, so run it before the run rather than discovering a stale answer key midway.

Pick the scenario first:

```bash
uv run python tools/usability_test/compose_brief.py --list
```

---

## Claude Code

The run needs five subagents. They are not checked in — an agent definition carries a
model and a tool allowlist, which are a deployment's choice rather than the method's — so
create them under `.claude/agents/` before the first run. The **tool allowlist is the
enforcement**: the isolation and no-writes rules hold because the tools are absent, not
because the prompt asks nicely.

| Subagent | Model | Effort | Tools |
|---|---|---|---|
| `usability-persona-gui` | opus | medium | `Read`, `mcp__plugin_playwright_playwright__*` |
| `usability-persona-mcp` | opus | medium | `Read`, `mcp__arch-repo-read__*`, `mcp__arch-assurance-read__*`, `mcp__arch-repo-write__artifact_authoring_guidance`, `mcp__arch-repo-write__artifact_help` |
| `usability-heuristic-reviewer-a` | fable | high | `Read`, `mcp__plugin_playwright_playwright__*` |
| `usability-heuristic-reviewer-b` | opus | high | `Read`, `mcp__plugin_playwright_playwright__*` |
| `usability-fmea-calibrator` | opus | high | `Read` |

Neither persona gets Bash or Write, and the MCP persona's two write-server entries are the
non-mutating guidance tools — it cannot change anything whatever its brief says. The two
heuristic reviewers are deliberately different model classes: two passes from one model are
one opinion twice.

Uniform model and effort across ALL personas in a run is a methodological requirement — a
finding must be attributable to the surface, not to which model happened to read it.

Run it:

1. Start a **fresh** session in this repository: `claude --model fable --effort high`
   (or `/model fable` and `/effort high` inside the session).
2. First message: `Run usability scenario <SCENARIO_ID>.` — that invokes the
   `usability-scenario-run` skill, which loads `method.md` and this file.
3. The orchestrator spawns personas via the Agent tool with `subagent_type:
   "usability-persona-gui"` or `"usability-persona-mcp"` according to the scenario's
   channel, passing ONLY the composed brief
   (`uv run python tools/usability_test/compose_brief.py --scenario <ID> --persona <ID>`)
   plus the failure decision table, the recording contract, the run-prefix rule, and — from
   the second stage onwards — that persona's own prior selections. Custom subagents start
   with a clean context: this is the zero-history spawn the method requires. Never use a
   fork.
4. Heuristic passes: `subagent_type: "usability-heuristic-reviewer-a"` and `"-b"`; FMEA
   calibration: `"usability-fmea-calibrator"`.
5. For the oracle-derivation and synthesis stages the orchestrator may switch itself to
   `/effort xhigh`, returning to `high` afterwards; note the switch in the deviations log.
6. Model and effort per role must NOT be overridden at spawn time — the agent definitions
   are the single source of truth.

Caveat: all Claude Code subagents share one Playwright browser. The method's
storage-clearing step between personas is the mitigation; record this as "approximated
isolation" in the report, as the method requires.

## Codex CLI (GPT-5.6 family)

1. Merge `codex-profiles.toml` into `~/.codex/config.toml` and substitute the real
   GPT-5.6 model ids for your tenant. Verify the key names against your `codex --help`
   version (see the caveat in that file).
2. Orchestrator, interactive, from the repository root:
   `codex --profile usability-orchestrator`, with the same first message as above. The
   stage logic is harness-neutral.
3. Isolated contexts are **separate processes**. Codex has no in-session subagent
   registry, and that is an advantage here: a fresh `codex exec` process is a stronger
   zero-history guarantee, and each spawns its own MCP servers, so GUI personas get their
   own browser. The orchestrator shells out per persona:

   ```bash
   uv run python tools/usability_test/compose_brief.py \
       --scenario "$SCENARIO" --persona "$PERSONA" > /tmp/usability-brief.md
   cat /tmp/usability-brief.md /tmp/usability-protocol.md \
     | codex exec --profile usability-persona --skip-git-repo-check \
         --output-last-message test-results/usability/$RUN_ID/logs/$PERSONA-s2.md -
   ```

   where `/tmp/usability-protocol.md` holds the failure decision table, the recording
   contract, the run-prefix rule and, from the second stage onwards, that persona's own
   prior selections. `sandbox_mode = "read-only"` stops personas writing files or running
   repository commands; their log comes back as the final message.
4. Heuristic passes: `codex exec --profile usability-heuristic-a - <
   surfaces-and-anchors.md`, likewise `usability-heuristic-b`; FMEA calibration via
   `--profile usability-fmea` with the sample findings on stdin.
5. Effort bump for the oracle and synthesis stages: run those orchestrator phases with
   `-c model_reasoning_effort=xhigh` (or a dedicated profile), and log the switch.
6. Where a scenario's write policy permits saves, the persona's GUI save steps need write
   access to the *backend through the browser*, which read-only sandboxing does not block:
   it is an HTTP call from the browser, not a file write. The run-prefix and manifest
   rules still apply verbatim.
7. MCP-channel personas on this harness reach the read servers only. A scenario whose
   tasks call the non-mutating authoring-guidance tool must run on Claude Code, whose
   per-agent allowlist can admit that one tool without admitting the writes that share its
   server.

## Shared rules regardless of harness

- One harness for the WHOLE run. Do not mix Claude Code and Codex within a run; a
  cross-harness comparison is a separate study with its own manifest.
- Every persona in a run: same agent or profile, same model, same effort. If any of that
  has to change mid-run, abort and restart the run.
- The report states, per role: harness, model id, effort, and whether browser isolation
  was approximated (Claude Code) or per-process (Codex).
