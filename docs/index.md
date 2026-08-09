# Documentation

Architecture-as-code for humans and AI agents — a typed, git-versioned, verifiable model
reachable through a GUI, a REST API, a CLI, and MCP tools, with a confidential assurance
capability alongside it.

New here? Start with the [Quickstart in the README](../README.md#quickstart), then read the
[motivation](01-motivation.md) for the why.

**Pick your entry path:**

- **New to architecture modeling** → the [first-model tutorial](07-first-model.md), then the
  [showcase](06-showcase.md) to see where it leads.
- **Architect** → [Architecture Modeling](03-modeling/index.md) (views, diagramming,
  viewpoints), then [Git sync & promotion](reference/git-sync-promotion.md) for the two-tier
  workflow.
- **Safety / security analyst** → [Assurance methods](04-assurance/methods.md) and
  [Storage & confidentiality](04-assurance/storage-and-confidentiality.md).
- **Running AI agents against the model** → [Interfaces & MCP](03-modeling/interfaces-and-mcp.md),
  [Authoring guidance](05-extensibility/guidance.md), and the
  [assurance MCP tools](04-assurance/mcp-tools.md).

&nbsp;

## Sections

| # | Section | For |
|---|---|---|
| 1 | [Motivation, Ideas, Goals & Scope](01-motivation.md) | Understanding why the project exists and what it does not try to do |
| 2 | [Installation & Setup](02-installation.md) | Getting it running on macOS, Linux, WSL2, or Docker |
| 3 | [Architecture Modeling](03-modeling/index.md) | Projects, views, graph exploration, diagramming, viewpoints, and the MCP/REST surface |
| 4 | [Assurance — Safety, Security, GRC](04-assurance/index.md) | STPA/CAST/GRC/FMEA methods, assurance diagrams, confidential storage |
| 5 | [Extensibility](05-extensibility/index.md) | Attribute profiles, guidance, document types, ontology & diagram-type modules, the hexagonal core |
| 6 | [Showcase: the platform's own model](06-showcase.md) | A guided read through the self-model, strategy to assurance |
| 7 | [Tutorial: your first model](07-first-model.md) | From a running backend to a model that answers a real question |
| — | [Reference](reference/configuration.md) | Configuration, CLI, upgrades, deployment, APIs, licensing |

&nbsp;

## Section 3 — Architecture Modeling

- [Overview](03-modeling/index.md)
- [Scratchpad](03-modeling/scratchpad.md)
- [Projects & grouping](03-modeling/projects-and-grouping.md)
- [Views & exploration](03-modeling/views-and-exploration.md)
- [Diagramming](03-modeling/diagramming.md)
- [Viewpoints](03-modeling/viewpoints.md)
- [Motivation coverage](03-modeling/coverage-semantics.md)
- [Interfaces & MCP](03-modeling/interfaces-and-mcp.md)

&nbsp;

## Section 4 — Assurance

- [Overview](04-assurance/index.md)
- [Methods](04-assurance/methods.md)
- [Exploring assurance](04-assurance/exploring-assurance.md)
- [Diagrams](04-assurance/diagrams.md)
- [Storage & confidentiality](04-assurance/storage-and-confidentiality.md)
- [AI-BOM](04-assurance/aibom.md)
- [MCP tools](04-assurance/mcp-tools.md)

&nbsp;

## Section 5 — Extensibility

- [Overview](05-extensibility/index.md)
- [Attribute profiles & frontmatter schemata](05-extensibility/schemata-and-profiles.md)
- [Authoring guidance](05-extensibility/guidance.md)
- [Document types](05-extensibility/document-types.md)
- [Ontology modules](05-extensibility/ontology-modules.md)
- [Diagram-type modules](05-extensibility/diagram-type-modules.md)
- [Hexagonal architecture](05-extensibility/hexagonal-architecture.md)

&nbsp;

## Reference

- [Configuration](reference/configuration.md)
- [CLI & backend](reference/cli-and-backend.md)
- [Upgrading a deployment](reference/upgrade-guide.md)
- [Git sync & promotion](reference/git-sync-promotion.md)
- [Docker Compose deployment](reference/docker-compose.md)
- [REST API](reference/rest-api.md)
- [Viewpoints — schema reference](reference/viewpoints-schema.md)
- [ArchiMate 4.0 conformance](reference/archimate-4-conformance.md)
- [Licensing](reference/licensing.md)
- [Architecture decision records](architecture/decisions.md) · [Dependency policy](architecture/dependency-policy.md) · [Glossary](architecture/glossary.md)

&nbsp;

## The model documents itself

The system's own architecture is modeled inside
[`engagements/ENG-ARCH-REPO/`](../engagements/ENG-ARCH-REPO/). Browse it through the GUI or
the `arch-repo-read` MCP tools — the screenshots in these docs are the tool describing its
own design, and the [showcase](06-showcase.md) walks the model end to end.
