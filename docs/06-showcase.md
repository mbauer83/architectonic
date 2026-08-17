# Showcase: The Platform's Own Model

This platform models itself: its motivation, strategy, runtime architecture, decisions,
and its own safety/security analysis all live in the bundled
[`engagements/ENG-ARCH-REPO/`](../engagements/ENG-ARCH-REPO/) repository and its
assurance store seed. This page is a guided read through that model — every stop names
the real artifact, with a deep link into a locally running app (default port assumed;
adjust the host if yours differs).

It comes in two parts, mirroring the boundary the product itself draws: the
**architecture model** (git-tracked, public) and the **assurance capability** over it
(separately stored, confidential by default — shown here from the platform's own
public self-model content).

&nbsp;

## Part 1 — From a force in the world to running code

**1. A driver and the double bind it creates.** The model starts from the force reshaping
software work: [*AI-Assisted and Agentic Development as a Dominant Production Mode*](http://localhost:8000/entities/DRV%401776628131.GR9prv)
(driver). At **agentic velocity** it produces a double bind — the assessment
[*Autonomy at Agentic Velocity Threatens Unity of Effort*](http://localhost:8000/entities/ASS%401780220699.CK90bp)
on one side, [*Centralized Governance Cannot Scale at Agentic Velocity*](http://localhost:8000/entities/ASS%401776628138.a6vxyj)
on the other.

**2. The core trade-off it forces.** Those failure modes sit on a trade-off between
stakeholder values — the *differentiation* pull of
[*Local Autonomy*](http://localhost:8000/entities/VAL%401784845185.fduAv-),
[*Team Solution Fitness*](http://localhost:8000/entities/VAL%401784845185.-RyIvn), and
[*Local Efficiency*](http://localhost:8000/entities/VAL%401784845186.56mLXu) against the
*integration* pull of [*Unity of Effort*](http://localhost:8000/entities/VAL%401784845184.pIkrDX),
[*Enterprise Adaptability*](http://localhost:8000/entities/VAL%401784845185.tL9l4U), and
[*Enterprise Efficiency & Solution Fitness*](http://localhost:8000/entities/VAL%401784845185.2xkN4J) —
all feeding [*Enterprise Viability*](http://localhost:8000/entities/VAL%401784845186.hFq7vl).
The whole tension is one view,
[*The Core Trade-off*](http://localhost:8000/diagrams/ARC%401784849983.W6j62G.the-core-trade-off-local-autonomy-and-enterprise-adaptability).

![The core trade-off between local autonomy and enterprise adaptability](media/motivation-core-trade-off.svg)

**3. The apex goal that answers it.** The apex goal
[*Sustain Unity of Effort at Agentic Velocity*](http://localhost:8000/entities/GOL%401780220699.FCfDuc)
answers the trade-off by splitting into
[*Preserve Local Autonomy*](http://localhost:8000/entities/GOL%401784845186.L4Ceuf) and
[*Enable Coherent, Traceable Enterprise Action*](http://localhost:8000/entities/GOL%401784845186.7RZp1S).
That second goal is the *end* that model fidelity serves: the subordinate goal
[*Maintain a Coherent, Traceable Architecture Model*](http://localhost:8000/entities/GOL%401712870400.Po1Qw3)
positively influences it and is realized through the outcome
[*Increased Architectural Coherence and Integrity*](http://localhost:8000/entities/OUT%401712870400.LrpdG0).
Two guiding principles bound the response —
[*Keep Shared Architecture Explicit and Machine-Checkable*](http://localhost:8000/entities/PRI%401784845187.cM0Xea)
and [*Governance Is Proportional to Impact and Risk*](http://localhost:8000/entities/PRI%401784845187.E3_ttJ).

**4. The strategy that answers it.** The course of action
[*Dogfood via the Recursive Self-Model*](http://localhost:8000/entities/COA%401784483697.FI0Xbj)
influences that outcome, and is realized by the capability
[*Architecture Knowledge Management*](http://localhost:8000/entities/CAP%401784482403.pLMHKe) —
one of five capabilities on the
[capability map](http://localhost:8000/diagrams/ARC%401784484044.GU6kjx.capability-map).
The full strategy layer is one view:
[Strategy Overview](http://localhost:8000/diagrams/ARC%401784483951.yBNaaU.strategy-overview).

<!-- media: docs/media/strategy-overview.png — captured by the deterministic media suite -->
![Strategy overview connecting the platform motivation, courses of action, capabilities, resources, and value streams](media/strategy-overview.png)

**5. The value it delivers.** That capability serves the value stream
[*Model & Validate the Architectural Design*](http://localhost:8000/entities/VS%401784483014.xrSjjJ) —
stage by stage, from scoping a change to feeding implementation learnings back — shown
end to end in
[*Deliver an Architecture-Aligned Change*](http://localhost:8000/diagrams/ARC%401784483996.YRywG6.value-stream-deliver-an-architecture-aligned-change).
The [Resource Investment Map](http://localhost:8000/diagrams/ARC%401784488894.WwyJAa.resource-investment-map)
renders the same strategy layer as a heat map over each resource's modeled
`investment_level`.

<!-- media: docs/media/value-stream-deliver-change.png -->
![Deliver an Architecture-Aligned Change value stream with its five sequential stages](media/value-stream-deliver-change.png)

<!-- media: docs/media/resource-investment-map.png -->
![Resource investment map connecting architecture resources to the capabilities they support](media/resource-investment-map.png)

**6. Down to the running system.** The C4 progression describes the platform's own
runtime, model-backed at every level:
[System Context](http://localhost:8000/diagrams/CSC%401780829783.z8RRON.amp-system-context) →
[Containers](http://localhost:8000/diagrams/CC%401780829785.Z_fI-N.amp-containers) → the backend
one concern at a time:
[Write Path](http://localhost:8000/diagrams/CC%401786952709.BT0ZHFR.architecture-backend-write-path),
[Read and Query Path](http://localhost:8000/diagrams/CC%401786972094.IZeGsvN.architecture-backend-read-and-query-path),
[Scratchpad Authoring](http://localhost:8000/diagrams/CC%401786961496.l3LvPfT.architecture-backend-scratchpad-authoring),
[Diagram Rendering](http://localhost:8000/diagrams/CC%401786961513.BTHvKLy.architecture-backend-diagram-rendering)
and [Assurance Module](http://localhost:8000/diagrams/CC%401786961588.b0QXPS5.architecture-backend-assurance-module).
Each derives its membership from a grouping in the model, so a component added to the model appears
without the diagram being edited.

<!-- media: docs/media/c4-context.png -->
![C4 system context for the Architecture Management Platform and its users and external systems](media/c4-context.png)

<!-- media: docs/media/c4-containers.png -->
![C4 container view of the Architecture Management Platform: the backend, the browser client, the command line and the MCP bridges, with the people and external systems around them](media/c4-containers.png)

<!-- media: docs/media/c4-backend-components.png -->
![C4 component view of the architecture backend's write path: the MCP adapter, the write queue, the bulk handlers, the staged transaction manager, the operation registry and the model verifier, inside a Write Pipeline boundary](media/c4-backend-components.png)

**7. And into its decisions.** From the
[Architecture Backend](http://localhost:8000/entities/APP%401777293133.OYEmP1) entity,
document backlinks lead to the ADRs that shaped it — for instance
[*One Unified Backend Authority; Every Write Through the Same Verified Pipeline*](http://localhost:8000/documents/ADR%401783406851.pGCuZn.one-unified-backend-authority-every-write-through-the-same-verified-pipeline) —
decisions authored as structured documents, linked to the entities they govern.

<!-- media: docs/media/guidance-wizard-context.png -->
![Guided modeling wizard with the application-component guidance and composed application-domain context expanded](media/guidance-wizard-context.png)

**Honesty checkpoint.** The same model that shows what exists also shows what's missing:
executing the [motivation-coverage](03-modeling/coverage-semantics.md) viewpoint against
this very model reports real, current gaps — goals whose branches do not all terminate
in realized requirements. The self-model is a working model, not a brochure.

<!-- media: docs/media/motivation-coverage-gaps.png — live model fallback with pinned scope and group -->
![Motivation coverage table showing passing and incomplete realization branches](media/motivation-coverage-gaps.png)

**7a. And the tier that lets someone start before any of this.** Every entity above asked for a
type before it could exist, which is the barrier the model itself names. The answer is the
[scratchpad](03-modeling/scratchpad.md) — modelled here like anything else, in
[*Why a scratchpad*](http://localhost:8000/diagrams/ARC%401786231345.EBLKfJU.why-a-scratchpad) and
[*The scratchpad, end to end*](http://localhost:8000/diagrams/ARC%401786231310.HEP_wga.the-scratchpad-end-to-end),
with the reasoning in
[*The scratchpad: a preliminary tier that lifts into the model, never syncs with it*](http://localhost:8000/documents/ADR%401786233058.fWkHZrZ).

It is worth pausing on what that means for this walk: the feature that removes the product's own
barrier to entry was designed *in* the product — drivers, an assessment, requirements realizing
outcomes, and a decision record that names the alternative it rejected. The model reports on the
tier that exists so people can contribute to the model.

&nbsp;

## Part 2 — The platform analyzing itself

The assurance store's seed content is the platform's own analysis, made with the
platform's own method tooling.

**8. A real hazard analysis of a real fix.** The STPA-Sec analysis
*PlantUML Preprocessor Untrusted-Input Disclosure* (`STPA@1784721732.pflr.3e4395` in the
seeded store) analyzes an actual security finding in the diagram-rendering path — a
preprocessor feature that could read files on user-submitted input — and carries the
constraints that were then shipped as code. Open it in the
[assurance explorer](04-assurance/exploring-assurance.md) and walk hazard →
loss scenario → constraint; the control-structure binding lands on the Architecture
Backend, the same entity you reached in Part 1.

<!-- media: docs/media/assurance-graph-explore.png -->
![Assurance graph centered on the PlantUML untrusted-input hazard with connected losses and unsafe control action](media/assurance-graph-explore.png)

<!-- media: docs/media/assurance-method-workflow.png -->
![STPA-Sec wizard review for the PlantUML preprocessor analysis with all coverage checks passing](media/assurance-method-workflow.png)

**9. Supply-chain posture on the same entities.** The backend's and the GUI's own SBOMs
are ingested as [security signals](04-assurance/security-signals.md) against their
self-model entities, and the `security-posture` viewpoint renders the result over the
application layer — with the fail-closed locked state and the stamped export path the
capability guarantees.

<!-- media: docs/media/security-posture-viewpoint.png — synthetic documentation findings are visibly marked -->
![Security posture viewpoint comparing three application components at synthetic CVSS scores 0.0, 5.4, and 9.1](media/security-posture-viewpoint.png)

<!-- media: docs/media/security-metrics-locked.png -->
![Architecture Backend entity page when assurance metrics are unavailable because the store is locked](media/security-metrics-locked.png)

<!-- media: docs/media/security-export-stamped.png — synthetic documentation findings are visibly marked -->
![Stamped TLP WHITE security posture export preserving its synthetic basis and three color-coded component scores](media/security-export-stamped.png)

&nbsp;

## Reproduce this walk yourself

```bash
uv run arch-init && uv run arch-backend --daemon          # the bundled workspace IS the self-model
uv run arch-assurance init && uv run arch-assurance seed --with-signals   # optional: the assurance side
```

Then follow the links above — or hand the same walk to an agent: every stop on this
page is reachable through `artifact_query_read_artifact`,
`artifact_query_find_connections_for`, and the `arch-assurance-read` tools.

---

*Try building your own: [Your first model →](07-first-model.md)*
