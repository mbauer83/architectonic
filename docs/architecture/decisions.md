# Architecture Decision Records

The platform's load-bearing decisions are recorded as ADR documents **inside the self-model**
(`engagements/ENG-ARCH-REPO/…/docs/adr/`), authored through the same MCP document tools any
model content uses and linked per-section to the model entities they govern — the tool
documenting its own decisions. Browse them in the running app under *Documents*, or on disk
below.

| Decision | In one line |
|---|---|
| [Markdown file-based architecture repository](../../engagements/ENG-ARCH-REPO/architecture-repository/docs/adr/platform-core/ADR@1780761609.GQWvwi.markdown-file-based-architecture-repository.md) | Entities, connections, and diagrams are plain text files in git — diffable, reviewable, agent-accessible |
| [Adopt ArchiMate 4.0 ontology](../../engagements/ENG-ARCH-REPO/architecture-repository/docs/adr/platform-core/ADR@1783857340.Rax2QD.adopt-archimate-4-0-ontology.md) | Machine-legible modeling vocabulary, loaded as a pluggable module |
| [Artifact identity & directory grouping](../../engagements/ENG-ARCH-REPO/architecture-repository/docs/adr/platform-core/ADR@1783406715.vX4p7z.artifact-identity-typed-epoch-random-identifiers-in-filenames-grouping-by-directory.md) | `TYPE@epoch.random.slug` filenames as stable, coordinator-free identity; grouping by directory placement |
| [Diagram–model bindings](../../engagements/ENG-ARCH-REPO/architecture-repository/docs/adr/platform-core/ADR@1783406738.Y7bzLM.diagram-model-correspondence-via-explicit-bindings-no-silent-model-mutation.md) | Correspondence lives on explicit per-diagram binding records; diagram edits never mutate the model silently |
| [Hexagonal core, test-enforced dependency policy](../../engagements/ENG-ARCH-REPO/architecture-repository/docs/adr/platform-core/ADR@1783406752.kQ__1X.hexagonal-core-with-a-test-enforced-dependency-policy-no-service-locator.md) | Injectable frozen catalogs from composition roots, no service locator, AST-enforced dependency matrix |
| [Two-tier repositories & promotion](../../engagements/ENG-ARCH-REPO/architecture-repository/docs/adr/promotion-and-tiering/ADR@1783406774.id7tSC.two-tier-repositories-with-promotion-as-the-governance-gate.md) | Autonomous engagement repos; one curated enterprise baseline; promotion as the governance gate |
| [Confidential assurance tier](../../engagements/ENG-ARCH-REPO/architecture-repository/docs/adr/assurance/ADR@1783406789.I82vuJ.confidential-assurance-tier-separate-gated-store-with-one-way-persisted-references.md) | Assurance content in a separate gated, encrypted store; references persisted one-way (assurance → architecture) |
| [Canonical artifact index per root](../../engagements/ENG-ARCH-REPO/architecture-repository/docs/adr/platform-core/ADR@1783406811.fm8W_z.one-canonical-artifact-index-per-repository-root-a-combined-view-for-the-pair.md) | One index instance per repository root; a stateless combined view for the engagement+enterprise pair |
| [SQLite read model with Copy-on-Write](../../engagements/ENG-ARCH-REPO/architecture-repository/docs/adr/platform-core/ADR@1783406825.9bDM6y.read-model-on-a-single-sqlite-backend-with-copy-on-write-concurrency.md) | FTS5 + recursive CTEs; lock-free reader snapshots; DuckDB rejected over full-rebuild FTS |
| [Unified backend authority](../../engagements/ENG-ARCH-REPO/architecture-repository/docs/adr/platform-core/ADR@1783406851.pGCuZn.one-unified-backend-authority-every-write-through-the-same-verified-pipeline.md) | One long-running backend; GUI/REST/CLI/MCP are thin surfaces; every write through the same verified pipeline |
| [MCP surface topology](../../engagements/ENG-ARCH-REPO/architecture-repository/docs/adr/platform-core/ADR@1783406863.eEC2t0.mcp-surface-topology-split-read-write-servers-gated-assurance-servers-responsibility-decomposed-tools.md) | Servers split at capability/gating boundaries only; tools decomposed by responsibility with accurate safety annotations |
| [Profile failure semantics](../../engagements/ENG-ARCH-REPO/architecture-repository/docs/adr/platform-core/ADR@1784674023.8alNxn.profile-failure-semantics-blast-radius-classification-and-single-boundary-quarantine.md) | Conflicts classified by blast radius — structural (startup abort) vs scoped (on-demand quarantine at one write boundary), never persisted |

Each ADR names the alternatives it rejected and links the requirements, principles, and
components it governs. The [dependency policy](dependency-policy.md) and
[glossary](glossary.md) complement the hexagonal-core decision.
