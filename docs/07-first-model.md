# Tutorial: Your First Model

This tutorial takes you from a running backend to a small engagement model that answers a
real question. It exists because "installed" and "modeling" are different states — and the
measure of a first model is not that files were created, but that **it answers a question
you actually had**.

Prerequisites: the [Quickstart](../README.md#quickstart) is done (backend running, GUI
reachable), and ideally [authoring guidance is imported](02-installation.md#3-initialize-the-workspace)
so the forms can advise you as you go.

The worked question: *"Which parts of my system actually realize the requirement that
matters most right now?"* Substitute your own — the point of the exercise is that at the
end, your model answers it.

&nbsp;

## 1. Create an engagement

An engagement repository holds one project's model. Scaffold a fresh one beside your
workspace:

```bash
uv run arch-switch-engagement MY-FIRST --local ../my-first-architecture --create
```

This creates the standard structure (`model/`, `docs/`, `diagram-catalog/`,
`.arch-repo/` with default schemata), initializes a git repository, makes the engagement
active, and restarts the backend against it. The GUI now shows an empty engagement.

&nbsp;

## 2. Sketch it first, before naming a type

The typed path below asks you to pick an element type as its first move. If you already know
which types you want, skip to step 3. If you do not — which is the ordinary case at the start of
a piece of work — start on a **[scratchpad](03-modeling/scratchpad.md)** instead, where nothing
needs a type at all.

From the GUI's **Scratchpads** entry, name one and open it. Then:

1. **Double-click** the canvas and type a thought — *"Customers can rely on order status being
   current"*. A title is all a note needs.
2. Add a second — *"Order status updates propagate within one minute"* — and a third for the part
   of your system that would do it.
3. **Drag a note's right-hand handle** onto another to link them. The links render dashed,
   because nothing here has been committed to yet.

There is no save button; the canvas writes for you once editing settles. Notice what you were
*not* asked: which of these is a goal, which a requirement, whether that link is a realization.
Those are good questions, and they are easier to answer once the shape is in front of you.

Keep this scratchpad open — the model you build next is the same thinking, decided.

> **Coming next:** binding a note to something the model already has, narrowing a note down the
> ontology's [classification levels](05-extensibility/ontology-modules.md#classification-levels),
> and lifting a selection into verified model content in one transaction. Until those land, the
> step below is how thinking becomes model content.

&nbsp;

## 3. Model the question — a goal, a requirement, and what realizes it

Three entities and two connections are enough to make the question answerable. In the
GUI, use the entity list's create action (or the guided modeling wizard at
`/model/wizard`):

1. **Goal** (motivation domain) — the outcome you care about, e.g.
   *"Customers can rely on order status being current."*
2. **Requirement** (motivation domain) — what the system must do for the goal, e.g.
   *"Order status updates propagate within one minute."* Connect it to the goal with a
   **realization** connection (the requirement realizes the goal).
3. **Application Component** (application domain) — the part of your system that
   fulfills the requirement, e.g. *"Order Status Service."* Connect it to the
   requirement with a **realization** connection.

Notice what the editor is doing for you: the connection rows on an entity's detail page
offer only the connection types and target types the ontology permits, guidance text
(once imported) frames each type choice, and every write is verified before it lands —
a typo'd reference or an illegal connection is rejected at the door, not discovered
later.

&nbsp;

## 4. The same authoring, as an agent

Everything you just clicked is equally available to an AI agent through the
`arch-repo-write` MCP server — this is the same model, through typed tools:

```
artifact_create_entity   (artifact_type="goal",                  name="…", summary="…")
artifact_create_entity   (artifact_type="requirement",           name="…", summary="…")
artifact_create_entity   (artifact_type="application-component", name="…", summary="…")
artifact_add_connection  (source_entity=<requirement-id>, target_entity=<goal-id>,        connection_type="archimate-realization")
artifact_add_connection  (source_entity=<component-id>,   target_entity=<requirement-id>, connection_type="archimate-realization")
```

Write tools default to a dry run — the agent sees the validated outcome before
committing it. Point an MCP client at the servers as shown in
[Configure MCP access](02-installation.md#5-configure-mcp-access-for-ai-agents) and ask
an agent to extend your model; the verifier holds it to the same rules it holds you to.

&nbsp;

## 5. Ask the model your question

Now make the model answer. Open **Viewpoints** and execute **Requirements Coverage
(gaps)** — the shipped viewpoint that badges every requirement by whether *anything*
realizes it. Your requirement shows as realized, with the component as the reason; any
requirement you add without a realizing element shows as an explicit gap, not a blank.

Two more ways to ask, worth trying with the same tiny model:

- **Graph exploration** (`/graph`): start from the goal and walk outward — the chain
  goal ← requirement ← component is your question, answered visually.
- **An agent asks for you**: `artifact_query_viewpoint (action="execute",
  slug="requirements-coverage-gaps")` returns the same verdicts as structured data.

&nbsp;

## 6. Save it

Open the **Changes** menu in the top bar and save — your model is a git commit in your
engagement repository, diffable and reviewable like any other code.

&nbsp;

## Where to go next

- See what a grown model looks like — the platform's own — in the
  [self-model showcase](06-showcase.md).
- Add diagrams over what you modeled: [Diagramming](03-modeling/diagramming.md).
- Let coverage thinking scale with you: [Motivation coverage](03-modeling/coverage-semantics.md)
  explains what "covered" honestly means once goals fan out.

---

*Back to [Documentation](index.md)*
