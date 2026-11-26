# Judge a stress analysis against a test set

This guide shows how to keep a test set of stressors apart from a stress analysis, judge the naive
architecture and an adapted one against it, and read the residuality coefficient that results. It
assumes an analysis has been started and that some design stressors are already written; see
[Run a stress analysis](stress-analysis.md) for the whole analysis.

&nbsp;

## Why the test set is kept apart

The design stressors are the ones the analysis walks: each is ticked against the components it hits,
grouped under an end state and answered by an adaptation. An architecture adapted against a set of
stressors will survive those stressors, so they cannot show whether the adaptations made it more
resilient in general.

The test set answers that question. Its stressors come from the same scope and are judged against
the same naive architecture, but nobody adapts against them. At the end, the naive architecture and
the adapted one are each judged on every test stressor, and the difference between the two is the
residuality coefficient.

Nothing in the product prevents a test stressor from being read during design work. The procedure
depends on the people doing the analysis:

1. Write the test set, or hold it out, before adapting.
2. Do not read it while adapting.
3. Judge the naive architecture, then adapt and integrate, then judge the integration.

The workspace shows these steps as progress in the test-set section. It does not block any of them.

&nbsp;

## Fill the test set

The workspace shows **Add a test set** below the analysis tables while the analysis has none. Select
it to open the test-set section. There are two ways to fill it.

**Hold out a random third.** With three or more design stressors written, select **Hold out a
random third** and confirm the question that opens in the section. A third of the design stressors,
chosen at random on the server, move into the test set. The confirmation names the stressors moved and the seed used; the same seed over the same
stressors moves the same ones again. Holding out works best before the design stressors are walked.

**Write test stressors directly.** Type a stressor into the line in the test-set section and press
`Enter`. A stressor is one line of text; nothing else is required.

Test stressors appear only in the test-set section. The Stressors tab, the incidence grid, the end
states, the progress list and the coverage hints show the design set alone.

Under each stressor line is a row of **perspectives**: PESTLE, Five forces, Business model canvas and
Organisation & people. Opening one lists its perspectives, each with a guiding question shown on
hover or focus. **Random perspective** highlights one. Choosing a perspective sets the stressor's
optional kind; once stressors carry kinds, a perspective without any stressor is marked with a small
circle. The perspectives describe the organisation's environment and never name an element of the
architecture.

A repository can offer perspectives of its own. Write them to `.arch-repo/stress-perspectives.json`:

```json
{"frameworks": [{"id": "regulation", "name": "Regulation", "perspectives": [
  {"name": "Data residency", "question": "What if data must stay in the country it was collected in?"}
]}]}
```

A framework with its own id is offered after the shipped ones. A framework with a shipped
framework's id (`pestle`, `five-forces`, `business-model-canvas`, `organisation`) takes that
framework's place. The coverage hints count the perspectives the repository offers. A file that
cannot be read in this shape is reported when the perspectives are read, naming the framework at
fault.

&nbsp;

## Judge an architecture

Each architecture judged so far has a line in the test-set section. The naive architecture always has
one, and so does every candidate that has been integrated into the model.

The integration also always has a line. Where one integrated candidate stacks on all the others, its
own line is the integration's. Where candidates were integrated separately, the section adds a line
for **The integration of** those candidates, judged as one architecture: the model as they left it.

1. Open the test-set section and select **Judge** beside an architecture. To judge a candidate that
   has no line yet, choose it under **Evaluate against the test set**.
2. The section lists the test stressors, and the canvas shows the architecture being judged. A
   candidate is marked with what it changes from the naive architecture.
3. Select a stressor and choose **Survives**, **Degrades** or **Fails**. Write the reasoning in the
   field below and press `Enter`.
4. If a stressor cannot be walked, or contradicts itself, write the reason and select **Strike as
   unusable…**, then **Strike**. A struck stressor leaves the count for every architecture.
   **Restore** takes it back.
5. Select **Next unjudged →** to move on, and **Done** to close the walk.

Each verdict is a row of the analysis document's Test Set table, naming the stressor, the
architecture (`naive`, the candidate's id, or `integration` for candidates integrated separately), the
verdict, whether the stressor is usable, and the
reasoning. A later verdict on the same stressor and architecture replaces the earlier one.

&nbsp;

## Read the residuality coefficient

For an architecture A, over the n usable test stressors:

```
R(A) = (Y − X) / n
```

X is the number of stressors the naive architecture survives and Y the number A survives. A
*degrades* verdict counts as one half. R ranges from −1 to 1, and 0 means A survives no more than the
naive architecture does.

The line for A reads, for example, `Residuality +0.33 · survives 8 of 12 (naive 4)`. Hovering over
it shows the strict figure, which counts full survivals only, and the number of degraded and failed
verdicts. Until both A and the naive architecture have a verdict on every usable stressor, the line
shows how many are judged instead of a figure.

The coefficient is computed each time it is read and is never stored. A candidate's page, and each
candidate in a comparison, shows the same line for every analysis that has judged it.

&nbsp;

## From an agent

The MCP tools cover the same steps:

| Tool | What it does |
|---|---|
| `analysis_perspectives` | Lists the perspectives and their guiding questions |
| `analysis_hold_out_test_set` | Moves a random third of the design stressors into the test set; dry run by default. Without a `seed` the draw is the analysis's own, so the dry run shows what the write moves. Asked again, it answers the test set already held and moves nothing |
| `analysis_test_set` | Reads the test set, the verdicts, each architecture's residuality and the procedure's progress |
| `analysis_residuality` | Reads a candidate's residuality in each analysis that judged it |

Test stressors and verdicts are written with `artifact_edit_document_table`, as rows of the
`stressors` table (with `set` = `test`) and the `survival` table.

---

*Back to [Architecture modeling](index.md)*
