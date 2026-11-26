# Run a stress analysis

A stress analysis tests an architecture against what its environment may do to it. You write
stressors, mark which parts of the architecture each one hits, group them under the end states they
lead to, and answer the end states with adaptations. A test set kept apart from that work then shows
whether the adapted architecture survives more than the one you started from.

This guide runs an analysis end to end in the GUI. Holding out and judging the test set is described
in more detail in [Judge a stress analysis against a test set](stress-test-set.md), and the
operations behind it in [Candidate architectures](candidate-architectures.md#stress-analyses).

&nbsp;

## The pieces

| Piece | What it is |
|---|---|
| **Naive architecture** | The architecture under evaluation as it stands before any stressor. It is a [candidate architecture](candidate-architectures.md), defined on its own canvas |
| **Stressor** | One line of free text about something that may happen in the environment, with an optional kind |
| **Incidence** | Which elements of the naive architecture a stressor hits |
| **End state** | Where one or more stressors lead, with the requirement stating the behaviour wanted there, or the reason no change is needed |
| **Adaptation** | A candidate architecture stacked on the naive one that answers one or more end states |
| **Test set** | Stressors held apart from the design work, judged at the end on the naive architecture and on the adapted ones |

The analysis is a document of the `stress-analysis` type. Its stressors, end states, incidence,
adaptations and verdicts are rows of its tables, and progress, incidence and coverage are computed
from them on every read.

&nbsp;

## Worked example: the promotion pipeline

The example asks whether the self-model's promotion pipeline needs a queue as the number of
engagements grows.

### 1. Start the analysis

On **Documents**, select **+ New stress analysis** (the **Plan › Stress analyses** list leads there
too). The start page asks for three things:

- **Name** — *Stress analysis — promotion pipeline*. The default is "Stress analysis — " followed by
  the architecture's name, numbered where another analysis already has that title.
- **Context**, optional — the environment the architecture is evaluated in and the decision the
  evaluation informs: *Engagements multiply over the next two years; the analysis informs whether
  promotion needs a queue.*
- **The architecture under evaluation** — the naive architecture's name: *Promotion pipeline as it
  stands*.

**Start and sketch the naive architecture** writes the analysis document and the naive candidate in
one write and opens the workspace on the naive architecture's canvas.

<!-- TODO screenshot: the start page with Name, Context and "The architecture under evaluation"
     filled in. Suggested name: docs/media/stress-start.png -->

### 2. Define the naive architecture on its canvas

The naive architecture starts empty. Its canvas needs no stored diagram:

- Search for *Repository Promotion Service*, *Artifact Index Store* and *Git Sync Service* under
  **Add from model**, and drag them onto the canvas or press `Enter` on a row. The naive
  architecture then reads over those elements, live, as the model changes.
- Right-click the canvas to create an element the model does not hold yet, such as a
  *Promotion Queue* application component, and draw relations between elements. Each becomes an
  operation of the naive candidate, listed on the left.
- To begin from a picture you already have, choose **A diagram** or **On top of a candidate** in the
  panel while the canvas is still empty.

Changes are saved to the candidate as you sketch, and nothing reaches the model before the naive
architecture is applied. Select **Done sketching · on to Stressors** when it is complete.

<!-- TODO screenshot: the workspace sketching the naive architecture — the tabs and operations list
     on the left, the canvas with the three placed elements and the created Promotion Queue on the
     right. Suggested name: docs/media/stress-naive-canvas.png -->

### 3. Write stressors

On the **Stressors** tab, type a stressor into **Write a stressor and press Enter**:

```
Forty engagements promote in the same week
The enterprise repository host is unavailable for two days
The organisation merges with a company that uses another repository
Promotion reviewers leave and are not replaced
A regulator requires every promotion to be signed off by a named person
A second architecture team adopts its own modelling conventions
```

A stressor describes the environment and never names an element of the architecture. The
**Perspectives** line under the input helps with that: PESTLE, Five forces, Business model canvas
and Organisation & people each open a list of perspectives with a guiding question, and
**Random perspective** picks one. Choosing a perspective sets the kind of the next stressor; the kind
is optional and can be removed before it is written. Once stressors carry kinds, a perspective with
no stressor yet is marked with a small circle. **Coverage hints** lists what the stressors have not
looked at yet: elements no stressor hits, end states with a single stressor, and stressors without
an end state.

Each row says what is still missing: *No component is ticked*, *What happens is not written*. Write
what happens under the stressor in its row.

### 4. Mark what each stressor hits

Select a stressor's row, then press an element on the canvas: the element is ticked as hit by that
stressor, and the **Hits** column counts it. The incidence panel below lists the ticked elements
with a note each. **Coupling** lists pairs of elements that stressors hit together.

### 5. Group stressors under end states

Open a stressor's **End state** cell and type a name, *Promotions stall*, then press `Enter` to
create the end state; later stressors choose it from the list. `M` on a focused row opens the same
chooser, and on the **End states** tab stressors are dragged between cards.

Each end state card names its **Required behaviour**, a requirement of the model, or
**No change needed, because…** with the reason. **Focus** turns the incidence grid to the end
state's stressors and marks on the canvas what they hit.

### 6. Adapt

On the **Adaptations** tab, select **New candidate on top of Promotion pipeline as it stands…**, name
the adaptation *Queued promotions*, choose the end state it answers, and select **Stack on…**. The
adaptation is a candidate stacked on the naive architecture; sketch its changes on its canvas as for
any candidate. Its page lists its operations against the naive architecture.

**What is left** in the header lists what the analysis has not done yet: stressors not walked or not
grouped, end states not answered. **Apply…** shows that list, then the dry run of the candidate you
choose, before anything is written. Applying does not wait for the list to be empty.

### 7. Integrate

The **Integration** tab lists the adaptations stacked on the naive architecture. Tick the ones to
combine, name the integration and select **Integrate**; conflicts are settled as described in
[Integrate candidates](candidate-architectures.md#integrate-candidates).

### 8. Judge against the test set

The test set belongs to the same analysis and the same naive architecture, and is kept apart from
the design work. Its progress line reads **Judge the naive → Adapt → Integrate → Judge the
integration**.

1. Before adapting, select **Add a test set** and fill it: write test stressors into its own input,
   or select **Hold out a random third**. With the six stressors above, the section asks
   *Move 2 of the 6 design stressors, chosen at random, into the test set?*; the notice after it
   names the stressors moved and the seed.
2. Do not read the test set while adapting. Test stressors appear only in this section; the
   Stressors tab, the incidence grid, the end states and the coverage hints show the design set.
3. Select **Judge** beside *Naive architecture*. For each test stressor choose **Survives**,
   **Degrades** or **Fails** and write the reasoning. **Strike as unusable…** removes a stressor
   that cannot be walked from the count for every architecture.
4. After adapting and integrating, judge the integration the same way, and any candidate chosen
   under **Evaluate against the test set**.

Each architecture's line then shows its residuality, for example
`Queued promotions  Residuality +0.33 · survives 3 of 6 (naive 2)`.

<!-- TODO screenshot: the test-set section after judging — the progress line, the naive line and an
     adaptation's residuality line, with the judging walk open on one stressor.
     Suggested name: docs/media/stress-test-set.png -->

&nbsp;

## Reading the residuality coefficient

Adapting against a set of stressors makes the architecture survive those stressors, so the design
set cannot show whether the adaptations made it more resilient in general. The test set can,
because nobody adapted against it. Residuality measures the difference.

For an architecture A, over the *n* usable test stressors:

```
R(A) = (Y − X) / n
```

*X* is the number of test stressors the naive architecture survives and *Y* the number A survives. A
*degrades* verdict counts as one half. R runs from −1 to 1; 0 means A survives no more than the naive
architecture.

| | Survives | Degrades | Fails | Counted |
|---|---|---|---|---|
| Naive architecture | 2 | 0 | 4 | X = 2 |
| *Queued promotions* | 3 | 2 | 1 | Y = 3 + 2 × ½ = 4 |

With six usable stressors, R = (4 − 2) / 6 = +0.33. Hovering the line shows the **strict** figure,
which counts full survivals only: (3 − 2) / 6 = +0.17. A large gap between the two means much of the
gain is degraded service.

Until both A and the naive architecture have a verdict on every usable stressor, the line shows how
many are judged instead of a figure. The coefficient is computed whenever it is read and is never
stored. A candidate's page, and each candidate on a comparison page, shows the same line for every
analysis that judged it.

**The integration's figure.** Where one integrated candidate stacks on all the others, its own line
is the integration's. Where adaptations were integrated into the model separately, the test-set
section adds a line *The integration of* those candidates, judged as one architecture: the model as
they left it. That is the figure the analysis ends on.

&nbsp;

## From an agent

The analysis is started with `analysis_start` and its tables are written with
`artifact_edit_document_table`. `analysis_progress`, `analysis_incidence`, `analysis_test_set` and
`analysis_perspectives` read it, and `analysis_hold_out_test_set` holds out the random third. See
[Stress test set](stress-test-set.md#from-an-agent) and
[Candidate architectures](candidate-architectures.md#stress-analyses).

---

*Next: [Judge a stress analysis against a test set →](stress-test-set.md)*
