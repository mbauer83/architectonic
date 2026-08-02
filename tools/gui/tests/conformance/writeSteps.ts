import { Effect } from 'effect'
import type { ModelRepository } from '../../src/ports/ModelRepository'

/**
 * One write the client performs, named by the repository method that performs it.
 *
 * The engagement-tier counterpart of `READ_STEPS`, and the same principle: the step calls the **real
 * adapter method**, so the URL comes from the adapter's own builder and the answer is decoded by the
 * adapter's own schema. Nothing here restates either.
 *
 * **Ordered and stateful, unlike the reads.** A write surface is not a set of independent calls —
 * nothing can edit what it has not created, and a delete has to be handed something it may destroy. So
 * these run in declared order against one origin, threading ids through a mutable `WriteContext`, in
 * the same shape as `tools/quality/rest_write_walk.py`. That is deliberate duplication of *shape* and
 * not of content: the REST walk proves the operations are served; this proves the GUI's own client
 * reaches them and can decode what they answer, which is a different claim and the one that failed in
 * 0.2.0.
 *
 * **Against a fixture origin, never `:8000`.** Every step here authors or destroys. The orchestrator is
 * `tools/quality/gui_write_walk.py`, which builds a disposable repository, serves it on its own port and
 * points `E2E_BASE_URL` at that — so pointing this at a developer's backend is something you have to do
 * on purpose rather than by forgetting.
 */
export interface WriteStep {
  /** The `ModelRepository` method this exercises. Held against the port's own keys. */
  readonly method: keyof ModelRepository
  /** Optional suffix when one method is worth exercising more than once. */
  readonly variant?: string
  readonly run: (repo: ModelRepository, context: WriteContext) => Effect.Effect<unknown, unknown>
  /**
   * Ids this step publishes for later ones, read out of what it answered.
   *
   * Declared as data rather than done inside `run`, so `writes.conformance.test.ts` needs no per-step
   * knowledge and a step that captured nothing cannot look like one that did.
   */
  readonly captures?: (answer: unknown, context: WriteContext) => void
  /**
   * Whether this step must report that it *wrote*.
   *
   * Off for the previews. `wrote: false` is a refusal from a mutation and the correct answer from a
   * dry run — the same value meaning opposite things depending on what was asked, which is why both
   * Python walks carry this flag too and why forgetting it here reported three working previews as
   * broken.
   */
  readonly mutates?: boolean
}

/** What the fixture published, and what the walk has made so far. */
export interface WriteContext {
  /** An entity the fixture authored, with a connection already on it. */
  readonly fixtureEntity: string
  /** The other end of that connection. */
  readonly fixtureOtherEntity: string
  /** An entity nothing references, so a delete has something it may destroy. */
  readonly doomedEntity: string
  /** The ArchiMate diagram over the two connected entities. */
  readonly fixtureDiagram: string
  /** The datatype diagram, its classifier, and the attribute on it. */
  readonly annotated: { diagram: string, classifier: string, attribute: string }
  /** Filled in as the walk goes. */
  readonly created: Record<string, string>
  /** The group slug, which `renameGroup` moves — read, never assumed. */
  groupSlug: string
}

const artifactIdOf = (answer: unknown): string => {
  const identifier = (answer as { artifact_id?: unknown } | null)?.artifact_id
  if (typeof identifier !== 'string' || identifier === '') {
    throw new Error(`no artifact_id in ${JSON.stringify(answer)?.slice(0, 300)}`)
  }
  return identifier
}

/** Remember `answer.artifact_id` under `key`, for the steps that address it. */
const capture = (key: string) => (answer: unknown, context: WriteContext): void => {
  context.created[key] = artifactIdOf(answer)
}

const held = (context: WriteContext, key: string): string => {
  const value = context.created[key]
  if (value === undefined) throw new Error(`nothing captured ${key}: an earlier step did not run`)
  return value
}

const ADR_BODY = [
  '## Context', '', 'Created by the GUI write walk.', '',
  '## Decision', '', 'Call the adapter method.', '',
  '## Consequences', '', 'None: a later step deletes this document.', '',
].join('\n')

/** A viewpoint definition the walk owns, so nothing shipped is edited. */
const viewpointDefinition = (name: string) => ({
  slug: 'gui-walk-viewpoint',
  version: 1,
  name,
})

export const WRITE_STEPS: readonly WriteStep[] = [
  // ── Entities ────────────────────────────────────────────────────────────────
  {
    method: 'createEntity',
    run: (r) => r.createEntity({
      artifact_type: 'application-component',
      name: 'GUI Walk Created Component',
      summary: 'Authored through the GUI\'s own adapter.',
      dry_run: false,
    }),
    captures: capture('entity'),
  },
  {
    method: 'editEntity',
    run: (r, c) => r.editEntity(held(c, 'entity'), {
      summary: 'Edited through the GUI\'s own adapter.',
      dry_run: false,
    }),
  },

  // ── Connections: onto the entity just made ──────────────────────────────────
  {
    method: 'addConnection',
    run: (r, c) => r.addConnection({
      source_entity: held(c, 'entity'),
      connection_type: 'archimate-serving',
      target_entity: c.fixtureEntity,
      description: 'Authored by the GUI write walk.',
      dry_run: false,
    }),
    captures: capture('connection'),
  },
  {
    method: 'editConnection',
    run: (r, c) => r.editConnection(held(c, 'connection'), {
      description: 'Edited by the GUI write walk.',
      dry_run: false,
    }),
  },
  {
    method: 'manageConnectionAssociations',
    run: (r, c) => r.manageConnectionAssociations(held(c, 'connection'), {
      add_entities: [c.fixtureOtherEntity],
      dry_run: false,
    }),
  },
  // `removeConnection` answers 204 and decodes nothing, so it goes last of the connection steps:
  // everything above needs the connection to still be there.
  {
    method: 'removeConnection',
    run: (r, c) => r.removeConnection(held(c, 'connection')),
  },

  // ── Documents: the full create → edit → delete round trip ───────────────────
  {
    method: 'createDocument',
    run: (r) => r.createDocument({
      doc_type: 'adr',
      title: 'GUI Walk Created Decision',
      body: ADR_BODY,
      dry_run: false,
    }),
    captures: capture('document'),
  },
  {
    method: 'editDocument',
    run: (r, c) => r.editDocument(held(c, 'document'), {
      title: 'GUI Walk Edited Decision',
      dry_run: false,
    }),
  },
  { method: 'deleteDocument', run: (r, c) => r.deleteDocument(held(c, 'document')) },

  // ── Diagrams ────────────────────────────────────────────────────────────────
  {
    method: 'createDiagram',
    run: (r, c) => r.createDiagram({
      diagram_type: 'archimate-application',
      name: 'GUI Walk Application View',
      entity_ids: [c.fixtureEntity, c.fixtureOtherEntity],
      connection_ids: [],
      dry_run: false,
    }),
    captures: capture('diagram'),
  },
  {
    method: 'editDiagram',
    run: (r, c) => r.editDiagram(held(c, 'diagram'), {
      diagram_type: 'archimate-application',
      name: 'GUI Walk Application View (replaced)',
      entity_ids: [c.fixtureEntity, c.fixtureOtherEntity],
      connection_ids: [],
      dry_run: false,
    }),
  },
  {
    method: 'syncDiagramToModel',
    run: (r, c) => r.syncDiagramToModel(held(c, 'diagram'), { dry_run: false }),
  },
  {
    // The edge key is read from the diagram's own context, which is where the product publishes it and
    // where the GUI's label editor gets it. Deriving it would mean copying the renderer's alias rule.
    method: 'setEdgeLabel',
    run: (r, c) => Effect.flatMap(
      r.getDiagramContext(c.fixtureDiagram),
      (context) => {
        const edge = context.connections.find((connection) => Boolean(connection.edge_key))
        if (edge?.edge_key === undefined || edge.edge_key === null) {
          return Effect.fail(new Error('the fixture diagram publishes no edge to label'))
        }
        return r.setEdgeLabel(c.fixtureDiagram, edge.edge_key, {
          label: 'labelled by the GUI write walk',
          dry_run: false,
        })
      },
    ),
  },
  {
    method: 'patchDiagramClassifierMetadata',
    run: (r, c) => r.patchDiagramClassifierMetadata(c.annotated.diagram, c.annotated.classifier, {
      patch: { note: 'Annotated by the GUI write walk.' },
      dry_run: false,
    }),
  },
  {
    // The three-level address: diagram → classifier → attribute. A separate method because it is a
    // separate resource — this walk is what found the port carrying it as a body field the server
    // forbids, so every attribute edit in the shipped UI answered 422.
    method: 'patchDiagramAttributeMetadata',
    run: (r, c) => r.patchDiagramAttributeMetadata(
      c.annotated.diagram, c.annotated.classifier, c.annotated.attribute,
      { patch: { multiplicity: '0..1', note: 'Annotated by the GUI write walk.' }, dry_run: false },
    ),
  },
  { method: 'deleteDiagram', run: (r, c) => r.deleteDiagram(held(c, 'diagram')) },

  // ── Matrices: their own contract, entity ids and connection-type configs ─────
  {
    method: 'createMatrixDiagram',
    run: (r, c) => r.createMatrixDiagram({
      name: 'GUI Walk Connection Matrix',
      entity_ids: [c.fixtureEntity, c.fixtureOtherEntity],
      conn_type_configs: [{ conn_type: 'archimate-serving', active: true }],
      dry_run: false,
    }),
    captures: capture('matrix'),
  },
  {
    method: 'editMatrixDiagram',
    run: (r, c) => r.editMatrixDiagram(held(c, 'matrix'), {
      name: 'GUI Walk Connection Matrix (replaced)',
      entity_ids: [c.fixtureEntity, c.fixtureOtherEntity],
      conn_type_configs: [{ conn_type: 'archimate-serving', active: true }],
      dry_run: false,
    }),
  },

  // ── Viewpoint definitions and pins ──────────────────────────────────────────
  {
    method: 'createViewpointDefinition',
    run: (r) => r.createViewpointDefinition({
      definition: viewpointDefinition('GUI Walk Viewpoint'),
      dry_run: false,
    }),
  },
  {
    method: 'replaceViewpointDefinition',
    run: (r) => r.replaceViewpointDefinition('gui-walk-viewpoint', {
      definition: viewpointDefinition('GUI Walk Viewpoint (replaced)'),
      dry_run: false,
    }),
  },
  { method: 'setViewpointPins', run: (r) => r.setViewpointPins(['gui-walk-viewpoint']) },
  // Unpinned before it is deleted: a pin naming a definition that no longer exists is a broken
  // reference, and leaving one behind would make the *next* step's failure about the wrong thing.
  { method: 'setViewpointPins', variant: 'cleared', run: (r) => r.setViewpointPins([]) },
  {
    method: 'deleteViewpointDefinition',
    run: (r) => r.deleteViewpointDefinition('gui-walk-viewpoint'),
  },

  // ── Groups: the whole lifecycle, including the rename that moves the address ─
  {
    method: 'createGroup',
    run: (r) => r.createGroup({ kind: 'model-project', slug: 'gui-walk-project', name: 'GUI Walk Project' }),
  },
  {
    method: 'updateGroup',
    run: (r, c) => r.updateGroup('model-project', c.groupSlug, { name: 'GUI Walk Project Renamed' }),
  },
  {
    method: 'renameGroup',
    run: (r, c) => Effect.tap(
      r.renameGroup('model-project', c.groupSlug, {
        name: 'GUI Walk Project Moved',
        new_slug: 'gui-walk-project-moved',
      }),
      // The resource's address changed, so the context has to follow it: a rename that left the later
      // steps addressing the old slug would report the rename working and fail on the archive.
      () => Effect.sync(() => { c.groupSlug = 'gui-walk-project-moved' }),
    ),
  },
  { method: 'archiveGroup', run: (r, c) => r.archiveGroup('model-project', c.groupSlug, {}) },
  { method: 'unarchiveGroup', run: (r, c) => r.unarchiveGroup('model-project', c.groupSlug) },
  {
    // A typed slug confirmation, not a formality: without it the route answers 400 and names the
    // value it wanted.
    method: 'deleteGroup',
    run: (r, c) => r.deleteGroup('model-project', c.groupSlug, c.groupSlug),
  },

  // ── The destructive single, against content nothing else needs ──────────────
  { method: 'deleteEntity', run: (r, c) => r.deleteEntity(c.doomedEntity) },

  // ── Git: promotion, then the save/submit/withdraw lifecycle it enables ──────
  // Last, and in this order. `saveEngagementChanges` refuses when nothing is uncommitted, so every
  // step above is what it commits; and the enterprise lifecycle presupposes a promotion having put
  // something in the enterprise repository to commit.
  {
    method: 'executePromotion',
    run: (r, c) => r.executePromotion({ entity_id: held(c, 'entity'), dry_run: false }),
  },
  {
    method: 'saveEngagementChanges',
    run: (r) => r.saveEngagementChanges({ message: 'Saved by the GUI write walk', push: true }),
  },
  {
    method: 'saveEnterpriseChanges',
    run: (r) => r.saveEnterpriseChanges({ message: 'Promoted by the GUI write walk' }),
  },
  { method: 'submitEnterpriseChanges', run: (r) => r.submitEnterpriseChanges() },
  {
    // Irreversible, and it takes the branch just submitted with it. Safe only because the remote is a
    // bare repository the fixture made and throws away. The typed confirmation the REST body wants is
    // the adapter's business, not the caller's — which is the port doing its job.
    method: 'withdrawEnterpriseChanges',
    run: (r) => r.withdrawEnterpriseChanges(),
  },
]

/**
 * The admin tier, walked by a **second, sequential** run against an admin-mode fixture backend.
 *
 * `--admin-mode` is process-wide: without it these answer 403, so they cannot share a run with the
 * steps above. Everything here targets the *enterprise* repository, which is what `/admin/api/*` is
 * for.
 */
export const ADMIN_WRITE_STEPS: readonly WriteStep[] = [
  {
    method: 'adminCreateEntity',
    run: (r) => r.adminCreateEntity({
      artifact_type: 'application-component',
      name: 'GUI Admin Walk Component',
      dry_run: false,
    }),
    captures: capture('adminEntity'),
  },
  {
    method: 'adminEditEntity',
    run: (r, c) => r.adminEditEntity(held(c, 'adminEntity'), {
      summary: 'Patched through the admin surface.',
      dry_run: false,
    }),
  },
  {
    method: 'adminCreateEntity',
    variant: 'counterpart',
    run: (r) => r.adminCreateEntity({
      artifact_type: 'application-component',
      name: 'GUI Admin Walk Counterpart',
      dry_run: false,
    }),
    captures: capture('adminOtherEntity'),
  },
  {
    method: 'adminAddConnection',
    run: (r, c) => r.adminAddConnection({
      source_entity: held(c, 'adminEntity'),
      connection_type: 'archimate-serving',
      target_entity: held(c, 'adminOtherEntity'),
      dry_run: false,
    }),
    captures: capture('adminConnection'),
  },
  {
    method: 'previewAdminRemoveConnection',
    mutates: false,
    run: (r, c) => r.previewAdminRemoveConnection(held(c, 'adminConnection')),
  },
  {
    method: 'adminRemoveConnection',
    run: (r, c) => r.adminRemoveConnection(held(c, 'adminConnection')),
  },
  {
    // The port had no way to make an enterprise diagram until this walk needed one, which left the two
    // steps below reachable only for a diagram some other surface had put there. `adminCreateDiagram`
    // is the gap closed rather than routed around.
    method: 'adminCreateDiagram',
    run: (r, c) => r.adminCreateDiagram({
      diagram_type: 'archimate-application',
      name: 'GUI Admin Walk View',
      entity_ids: [held(c, 'adminEntity'), held(c, 'adminOtherEntity')],
      connection_ids: [],
      dry_run: false,
    }),
    captures: capture('adminDiagram'),
  },
  {
    method: 'previewAdminDeleteDiagram',
    mutates: false,
    run: (r, c) => r.previewAdminDeleteDiagram(held(c, 'adminDiagram')),
  },
  {
    method: 'adminDeleteDiagram',
    run: (r, c) => r.adminDeleteDiagram(held(c, 'adminDiagram')),
  },
  {
    method: 'previewAdminDeleteEntity',
    mutates: false,
    run: (r, c) => r.previewAdminDeleteEntity(held(c, 'adminOtherEntity')),
  },
  {
    method: 'adminDeleteEntity',
    run: (r, c) => r.adminDeleteEntity(held(c, 'adminOtherEntity')),
  },
]
