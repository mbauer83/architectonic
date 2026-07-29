# AI-BOM (model-derived ML-BOM)

An **AI-BOM** is a bill of materials for the AI parts of a system — models, datasets, agents,
prompts, vector stores, serving runtimes, tool interfaces — and their provenance, licensing,
governance, and dependencies. Regulators and procurement (the EU AI Act's technical
documentation, NIST's AI RMF, enterprise AI questionnaires) increasingly ask for one.

## Why model-derived, not manifest-scanned

The common approach scans a running system or a dependency manifest and guesses which
packages are "AI". That answers *what libraries are installed*, not *what the system does with
AI* — it cannot say which model was trained on which dataset, who is accountable for it, or
which agent calls which tool, because those facts are not in a manifest.

This platform derives the AI-BOM **from the architecture model you already maintain**. The
relationships that a manifest lacks — a model *trained-on* a dataset, an owner *accountable-for*
a component, an agent *depending-on* a model — are edges in the model. Four of the hardest
CycloneDX ML-BOM fields (datasets, governance, the dependency graph, considerations) are
*derived from relationships*, not re-entered. The BOM is a projection of the model, so it stays
truthful as the model changes and never drifts from a separate document.

## Marking AI components

An entity becomes an AI component by carrying an **AI specialization** — set it on the entity
like any other specialization (GUI entity page, or `artifact_edit_entity` with a
`specialization`). The eight specializations, on their natural base types:

| Specialization | Base type | Is |
|---|---|---|
| `ai-model` | application-component | the trained model artifact (the model card lives here) |
| `ai-agent` | application-component | an agent or pipeline built on models + tools |
| `ai-inference-service` | service | the served inference endpoint |
| `ai-dataset` | data-object | training / evaluation / fine-tuning data |
| `ai-prompt-asset` | data-object | system prompts, prompt templates |
| `ai-vector-store` | data-object | an embedding / RAG index |
| `ai-runtime` | system-software | the serving engine (vLLM, ONNX Runtime, …) |
| `ai-tool-interface` | application-interface | the tool/function surface an agent can call |

The **candidate scan** (AI-BOM panel, or `/api/assurance/aibom/scan`) is assistive only — it
ranks unmarked entities by name/type heuristics so you can find likely components; you confirm
each by marking it. An already-marked entity is skipped.

## Authoring the model card

The model card is a set of ordinary attributes on the specialization — `Approach`, `Task`,
`Architecture Family`, `Performance Metrics`, `Ethical Considerations`, supplier, licences —
so you author them in the **entity's own Properties editor**, typed by the schema (enums as
dropdowns, lists as add/remove editors). There is no separate wizard: deriving from the model
means authoring is ordinary entity authoring. Dataset links, governance owners, and the
dependency graph are **not** authored — they come from the connections.

## Derivation roles

How a repository expresses each relationship is configurable. A closed set of **derivation
roles** (`trained-on`, `evaluated-on`, `fine-tuned-from`, `embeds-into`, `served-by`,
`uses-tool`, `guarded-by`, `governed-by`, `consumes-prompt`) binds to the connection type(s)
and target specialization(s) that realise it. The archimate-4 module ships defaults; a repo
overrides them in `.arch-repo/aibom-roles.yaml` (merged per role). The roles are closed (the
exporter must know each to place it in the BOM); the bindings are open (each repo declares its
own conventions). A role no connection type binds to is a coverage finding — never a silently
empty BOM.

## Coverage — what is missing for a valid AI-BOM

The coverage report (AI-BOM panel, or `/api/assurance/aibom/coverage`) answers, per AI
component, what is missing — in two tiers so optional/unavailable information is handled
sensibly:

- **Blocking** (the component is under-documented): a missing **required** attribute, a model/
  agent with no **dataset** link, a component with no **governance** edge.
- **Advisory**: a missing **recommended** attribute — surfaced to help, never a validity
  blocker. Optional attributes are not tracked as gaps at all.

Plus the repo-wide **unbound derivation roles**. Coverage is dedicated code, not a viewpoint:
it is schema- and binding-relative (validation), not a graph projection.

## Export

Export (AI-BOM panel, `POST /api/assurance/aibom/export`, or `artifact_aibom_export` on
arch-repo-read) emits a CycloneDX 1.6 ML-BOM derived from the model, validated against the
CycloneDX 1.6 schema. It reads only the public architecture model — no confidential assurance
store — so it is un-gated. Seal an emitted BOM into the assurance archive via
`assurance_seal_baseline`. SPDX 3.0 AI Profile is a documented future second emitter.

---

*Next: [Assurance MCP tools →](mcp-tools.md)*
