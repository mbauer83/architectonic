# Assurance Methods

The assurance capability is **guidance-first**: each method has create-when / never-create
guidance on every entity type, and a method-completion verifier reports what a given analysis
still needs. The aim is to let a small team run a rigorous analysis without a resident
specialist.

&nbsp;

## STPA (System-Theoretic Process Analysis)

A top-down safety analysis built on the STAMP model. The flow follows the entity graph:

1. **Losses** — name the unacceptable, stakeholder-level outcomes. Everything traces back
   here.
2. **Hazards** — system states that, under worst-case conditions, can lead to a loss.
3. **Control structure** — model controllers and controlled processes as
   `control-structure-node`s, and the `control-action`s that flow between them. Binding a
   node to an architecture entity ties the analysis to the real system; an unbound node
   flags a modeling gap.
4. **Unsafe control actions (UCAs)** — for each control action, work the guidewords: *not
   provided*, *provided in unsafe context* (a well-formed command issued in a state where it must
   not be), *provided incorrectly* (issuing it is called for, its content is not), *wrong timing or
   order*, and — for a control action held over time only — *stopped too soon or applied too long*.
   The two "providing" guidewords are the Handbook's single one split, because a wrong context and a
   wrong command call for different constraints. Each UCA references one control action and its
   controller.
5. **Loss scenarios** — the causal pathways explaining how a UCA leads to a hazard.
6. **Assurance constraints** — derived from scenarios; carry the safety/security framing,
   disposition, and integrity level. A constraint links to an ArchiMate requirement via a
   one-way `refines` edge rather than being merged into it.

&nbsp;

## STPA-Sec (security)

The same machinery, framed for security: a hazard is also a vulnerable system state
exploitable by a threat actor. The `concern_class` field distinguishes safety from security
on hazards and constraints, so a single control structure can carry both analyses.

&nbsp;

## CAST (Causal Analysis based on System Theory)

Retrospective analysis of an event that actually happened. An **incident** anchors a
reconstruction of the control structure *as it existed*, against a sealed analysis baseline.
UCAs and loss scenarios created in CAST are marked `mode=observed` (versus `hypothesized` for
STPA). **Corrective actions** capture recommendations and derive assurance constraints that
then enter the GRC lifecycle.

&nbsp;

## FMEA (Failure Mode and Effects Analysis)

A bottom-up analysis of how each component fails, run **on top of an existing hazard analysis**
rather than beside one. Where STPA asks how the system's control can produce a loss, FMEA asks how
each part can fail — and neither covers the other's ground. A failure-mode analysis will not find a
coordination flaw where nothing failed; a control-structure analysis will not tell you which
component to harden next. Treat FMEA as prioritisation of effort, never as extra coverage.

**Nothing about consequence is restated.** A failure mode's effect is a `leads-to` link to a hazard
the analysis already has, and its severity is read from the losses that hazard reaches. There is no
second effect vocabulary, no second severity scale, and no second account of the same consequence to
reconcile later. The corollary is a rule the guidance enforces: a finding where nothing failed is not
a failure mode, and a failure mode that names an outcome rather than a failure is a hazard in
disguise.

### The guidewords

Each candidate element is examined against five guidewords — deliberately parallel to the five UCA
guidewords, which ask the same shape of question about a control action:

| Guideword | The question |
|---|---|
| No function | Does it fail to perform at all? |
| Partial or degraded function | Does it perform below what is required? |
| Excessive function | Does it perform beyond what is required? |
| Intermittent function | Does it perform unreliably over time? |
| Unintended function | Does it perform something it was never meant to? |

A cell examined and judged **not credible** is recorded as such, with who decided and why. That is a
finding, it counts as coverage, and it is what keeps an unstarted matrix from looking like a finished
one. The matrix therefore has three cell states, not two: recorded, dismissed as not credible, and
never looked at.

**Rows are a nomination, not a census.** Every element against five guidewords is thousands of cells
nobody completes. The candidates are the elements a control structure already names — the hazard
analysis has already said those matter — plus the ones the architecture graph shows to be
load-bearing: a single point of failure, or something a great many typed dependents lean on. Those
are counted from declared relationship roles and strengths, never from raw edge count, and an element
with nothing modelled around it yields *absence* rather than zero.

### The three factors, and where each comes from

| Factor | Basis |
|---|---|
| **Severity** | Derived: the worst `severity` among the losses reachable from the failure mode through its hazard. Absent when no hazard or loss is linked — a coverage gap, never a default. |
| **Occurrence** | Asserted only. Nothing in the model measures a failure rate, so there is no derived value to correct. |
| **Detectability** | Derived from the controls that `detect` this failure mode — a property of the controls present, not a statistic. |

A derived value may be overridden by a human judgement, which is stored as an immutable revision
carrying its rationale, its author, and a digest of the picture of the model it was made against.
When the model moves, the judgement stops applying and the derived value takes over again, with the
revision retained. An asserted severity may *lower* what the hazard chain reaches — the chain can
overstate what one particular failure does — but never exceed it, which would invent consequence and
then let it drive a priority.

**The detectability axis runs the opposite way from conventional FMEA's "D" number.** Here
`detectability` rates how detectable the failure is, so **higher is better**, and `very-low` means
"nothing would catch this". Read it the conventional way round and the most dangerous row in any
analysis becomes a low priority.

**Severity and classification are independent, and neither is readable off the other.** A loss's
severity says how bad the outcome would be for the deployment the analysis is of; its TLP says how
restricted *this record of it* is. The worked analysis in these pages is the clearest case of the two
diverging: its nodes sit at a low TLP and its exposure ceiling withholds nothing, because the
analysis is published deliberately — while the losses are rated for a deployment holding assurance
work that is genuinely confidential, which is what the capability exists to serve. Rating severity
down to match a permissive ceiling would analyse the wrong system, and raising a TLP to match a high
severity would hide an example that exists to be read.

### Action Priority, and why there is no RPN

Priority comes from a decision table over the three factors — never from a product. Multiplying
severity by occurrence by detectability treats three ordinals as if they were ratio quantities: the
step from `major` to `catastrophic` is not the same size as the step from `minor` to `moderate`, so
the product measures nothing. It also conceals what it claims to rank, since 10·1·1 and 1·10·1 share
a score of 10 while describing completely different situations, one of them catastrophic. The 2019
AIAG-VDA handbook replaced the number with a decision table for these reasons, and this follows it.

The table is severity-dominant by construction: a catastrophic outcome that nothing would detect is
`high` however rarely it happens, because rarity is no comfort when the consequence is unrecoverable
and nobody would see it coming. A row missing a factor that could have changed the answer is
`indeterminate` — its own band, not `low`. An unrated row is a gap to close, and rendering it as low
priority is how an un-analysed component comes to look safe. When several rows roll up to one
component, the most urgent band wins and `indeterminate` never outranks a real finding; it is counted
separately.

Because severity and detectability are both derived, the surface knows the band *before* asking
anything. For twelve of the twenty-five severity × detectability pairs no occurrence value can change
the outcome, and there the field is not shown at all: asking for a judgement that cannot matter
teaches people to answer carelessly, and those same people then answer the rows where it does matter.

&nbsp;

## GRC (Governance, Risk & Compliance)

Two overlays on top of the safety/security model:

- **Risk** — an evaluation overlay that *assesses* a hazard or loss scenario and records a
  treatment (`mitigate` / `transfer` / `avoid` / `accept`). A risk entity is optional and can
  never be a precondition for a constraint, and `accept` is unavailable for safety
  concern-classes — this is where *safety is never subordinate to risk* is enforced.
- **Obligation** — a compliance instance: "does the system comply with requirement X of
  standard/regulation Y?" It cites a public framework code (for example `ISO26262:6-8`) while
  keeping status and evidence confidential in the assurance store.

&nbsp;

## Supply-chain signals

External supply-chain and cybersecurity signals are ingested as **signal
snapshots** anchored on architecture entities, then read back as component
inventories, vulnerability findings, and impact analysis. See
[Security signals](security-signals.md) for the full capability.

```bash
uv run arch-assurance seed --with-signals  # bootstrap a store, then ingest for its declared anchors
uv run tools/assurance/ingest_security_signals.py --target python --anchor <entity-id>
uv run arch-assurance export-aibom         # emit a CycloneDX 1.6 AI-BOM from component data
uv run arch-assurance scan-ai-candidates   # heuristic scan of architecture entities for AI-BOM relevance
```

`seed` reads the active engagement repository's own bundle,
`.arch-repo/assurance-seed.json` — the anchors in it name entities in that repository, so the
bundle belongs to it rather than to the workspace. Pass `--input` for any other bundle.

&nbsp;

## Working an analysis end to end

Every method runs through the same workflow surfaces:

1. **Create an analysis.** An *analysis* is the aggregate a method's content lives in.
   Create one from the method's wizard in the GUI, or with `assurance_create_analysis`
   (MCP). Each analysis names its method, so the completion checks know what "done"
   means for it.
2. **Work the guided wizard.** Each method has a guided flow — `/assurance/analyses/new/stpa`,
   `/assurance/analyses/new/cast`, `/assurance/analyses/new/grc`,
   `/assurance/analyses/new/gsn`, `/assurance/analyses/new/fmea`, and
   `/assurance/supply-chain` — that walks the method's steps in order, creating the
   typed nodes and edges as you go, with the per-type guidance inline. The wizards
   author ordinary store content: anything they create is equally editable from the
   browse/detail views or via the MCP write tools.
3. **Review completeness.** The method-completion verifier (below) reports what the
   analysis still needs; the wizards surface the same checks as you work, and agents
   read them via `assurance_stpa_complete`, `assurance_cast_complete`,
   `assurance_grc_complete`, and `assurance_case_completeness` (GSN), plus
   `assurance_coverage` for how much of the architecture the analysis touches.
4. **Seal a baseline.** `/assurance/baselines` (GUI) or `assurance_seal_baseline`
   (MCP) seals the analysis state into the tamper-evident archive — the reference
   point a CAST reconstruction or a later review compares against.

&nbsp;

## Evidencing a constraint

A constraint states what must hold. **Evidence** is what substantiates it, and it is a node of its
own rather than a field, because the same verification often answers more than one constraint and
because an assurance case needs something to point at.

Each evidence node carries three things: a **pointer** to where the verification lives, the **claim**
it establishes, and the **gate** that runs it — enough to judge sufficiency without opening the code.
Deliberately not recorded: run outcomes and dates. There is no mechanism to keep them fresh, and
point-in-time integrity is what sealing a baseline is for.

The shape is:

- `evidenced-by` from the constraint to the evidence node — the constraint's claim to being answered.
- `binds-to` from the evidence node to the architecture artifact that performs the verification,
  typically a test suite. The verification meaning stays on the assurance edge, because ArchiMate has
  no relation for it: `realization` is false (a suite does not realize what it tests) and
  `association` asserts nothing. The architecture entity is the anchor, not the assertion. An unbound
  evidence node is flagged as pending rather than rejected — confidential-only evidence legitimately
  has no architecture counterpart.
- A verification suite is modelled **when, and because, it evidences a constraint**. This is
  purposeful modelling, not a census of the test tree.

**Evidence is never less restricted than the most restricted thing it evidences.** A `TLP:WHITE`
evidence node attached to a `TLP:GREEN` constraint would be visible to a reader who cannot see the
constraint, and its description would disclose it. The exposure policy filters per node, so nothing
else prevents this; the verifier rejects it as a hard finding.

Evidence nodes are also what a GSN assurance case turns into solutions. An argument whose constraints
carry no evidence produces a goal structure with nothing at the bottom, which is why a constraint with
no `evidenced-by` link is reported as a coverage gap.

&nbsp;

## Method-completion verification

Beyond per-write validation, the assurance verifier reports whether a method is *complete* —
for example, hazards without scenarios, UCAs without a referenced control action, or
constraints lacking an accountable party. This guidance is what makes the analysis tractable
without a method expert in the room, and it doubles as a checklist for review.

For FMEA the checks are mostly about coverage, because the characteristic failure of a per-component
worksheet is not an invalid row but an absent one: an element the control structure names that nobody
examined, an element the architecture graph shows to be load-bearing that no analysis has reached, and
a failure mode with no hazard or no detecting control — the two absences that leave its priority
underivable.

---

*Next: [Diagrams →](diagrams.md)*
