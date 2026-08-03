import { Effect } from 'effect'
import type { ModelRepository } from '../../src/ports/ModelRepository'
import type { ConformanceSeed } from './seed'

/**
 * One read the client performs, named by the repository method that performs it.
 *
 * The step calls the **real adapter method**, so the URL comes from the adapter's own builder and
 * the body is decoded by the adapter's own schema. Nothing here restates either. A step that
 * needed its own copy of a path would be a second spelling with no compiler between the two, which
 * is the defect shape (§1.1 Shape B) this harness exists downstream of.
 *
 * `needs` names the seeds the step cannot run without. An absent seed *fails* the step and says
 * which seed was missing, rather than skipping it: an unexercised read reported as success — or as a
 * skip nobody reads — is the green lie the harness is a response to.
 */
export interface ReadStep {
  /** The `ModelRepository` method this exercises. Held against the port's own keys. */
  readonly method: keyof ModelRepository
  /** Optional suffix when one method is worth exercising more than once. */
  readonly variant?: string
  readonly needs?: readonly (keyof ConformanceSeed)[]
  readonly run: (repo: ModelRepository, seed: ConformanceSeed) => Effect.Effect<unknown, unknown>
}

const need = (seed: ConformanceSeed, key: keyof ConformanceSeed): string => {
  const value = seed[key]
  if (value === null) throw new Error(`seed ${key} is absent`)
  return value
}

/**
 * The reads and the non-mutating write-shaped operations — previews, plans, query execution.
 *
 * Mutating writes are deliberately absent and registered as such in
 * `readCoverage.conformance.test.ts`: they are the next slice (handoff §1.9 step 4), and they need
 * a fixture repository they can create into rather than the dogfood repository this walks.
 */
export const READ_STEPS: readonly ReadStep[] = [
  // ── Platform ────────────────────────────────────────────────────────────────
  { method: 'getServerInfo', run: (r) => r.getServerInfo() },
  { method: 'listModules', run: (r) => r.listModules() },
  { method: 'getStats', run: (r) => r.getStats() },
  { method: 'getSyncStatus', run: (r) => r.getSyncStatus() },
  { method: 'getChanges', run: (r) => r.getChanges('engagement') },
  { method: 'getChanges', variant: 'enterprise', run: (r) => r.getChanges('enterprise') },
  { method: 'getWriteHelp', run: (r) => r.getWriteHelp() },

  // ── Entities ────────────────────────────────────────────────────────────────
  { method: 'listEntities', run: (r) => r.listEntities({ limit: 5 }) },
  {
    method: 'listEntities',
    variant: 'filtered',
    run: (r) => r.listEntities({ domain: 'business', limit: 2, sort: 'name', order: 'asc' }),
  },
  { method: 'listEntityTaxonomy', run: (r) => r.listEntityTaxonomy({}) },
  {
    method: 'getEntity',
    needs: ['entityId'],
    run: (r, s) => r.getEntity(need(s, 'entityId')),
  },
  {
    method: 'getEntityContext',
    needs: ['entityId'],
    run: (r, s) => r.getEntityContext(need(s, 'entityId')),
  },
  {
    method: 'getEntitySchemata',
    needs: ['entityType'],
    run: (r, s) => r.getEntitySchemata(need(s, 'entityType')),
  },
  {
    method: 'getEntityDisplayItem',
    needs: ['entityId'],
    run: (r, s) => r.getEntityDisplayItem(need(s, 'entityId')),
  },
  {
    method: 'previewDeleteEntity',
    needs: ['deletableEntityId'],
    run: (r, s) => r.previewDeleteEntity(need(s, 'deletableEntityId')),
  },

  // ── Connections ─────────────────────────────────────────────────────────────
  {
    method: 'getConnections',
    needs: ['entityId'],
    run: (r, s) => r.getConnections(need(s, 'entityId')),
  },
  {
    method: 'getConnections',
    variant: 'outbound',
    needs: ['entityId'],
    run: (r, s) => r.getConnections(need(s, 'entityId'), 'outbound'),
  },
  {
    method: 'getNeighbors',
    needs: ['entityId'],
    run: (r, s) => r.getNeighbors(need(s, 'entityId'), 2),
  },
  {
    method: 'previewRemoveConnection',
    needs: ['connectionId'],
    run: (r, s) => r.previewRemoveConnection(need(s, 'connectionId')),
  },

  // ── Search ──────────────────────────────────────────────────────────────────
  { method: 'search', run: (r) => r.search('a', 5) },
  { method: 'artifactSearch', run: (r) => r.artifactSearch('a', { limit: 5 }) },
  {
    method: 'searchReferenceArtifacts',
    run: (r) => r.searchReferenceArtifacts({ q: 'a', limit: 5 }),
  },
  { method: 'searchEntityDisplay', run: (r) => r.searchEntityDisplay({ query: 'a', limit: 5 }) },

  // ── Diagrams ────────────────────────────────────────────────────────────────
  { method: 'listDiagrams', run: (r) => r.listDiagrams({}) },
  { method: 'listDiagramTypes', run: (r) => r.listDiagramTypes() },
  {
    method: 'getDiagramTypeUiConfig',
    needs: ['diagramTypeKey'],
    run: (r, s) => r.getDiagramTypeUiConfig(need(s, 'diagramTypeKey')),
  },
  { method: 'getDiagram', needs: ['diagramId'], run: (r, s) => r.getDiagram(need(s, 'diagramId')) },
  {
    method: 'getDiagramContext',
    needs: ['diagramId'],
    run: (r, s) => r.getDiagramContext(need(s, 'diagramId')),
  },
  {
    method: 'getDiagramEntities',
    needs: ['diagramId'],
    run: (r, s) => r.getDiagramEntities(need(s, 'diagramId')),
  },
  {
    method: 'getDiagramConnections',
    needs: ['diagramId'],
    run: (r, s) => r.getDiagramConnections(need(s, 'diagramId')),
  },
  {
    method: 'getDiagramSvg',
    needs: ['diagramId'],
    run: (r, s) => r.getDiagramSvg(need(s, 'diagramId')),
  },
  {
    method: 'getDiagramRefs',
    needs: ['connectionSourceId', 'connectionTargetId'],
    run: (r, s) =>
      r.getDiagramRefs(need(s, 'connectionSourceId'), need(s, 'connectionTargetId')),
  },
  {
    method: 'previewDeleteDiagram',
    needs: ['diagramId'],
    run: (r, s) => r.previewDeleteDiagram(need(s, 'diagramId')),
  },
  { method: 'discoverDiagramEntities', run: (r) => r.discoverDiagramEntities({ query: 'a', limit: 5 }) },
  {
    method: 'previewDiagram',
    needs: ['entityId', 'diagramTypeKey'],
    run: (r, s) =>
      r.previewDiagram({
        diagram_type: need(s, 'diagramTypeKey'),
        name: 'Conformance preview',
        entity_ids: [need(s, 'entityId')],
        connection_ids: [],
      }),
  },
  {
    // The one combination the product actually sends (`DatatypeEditor.vue`). Not seeded from the
    // diagram-type list: an allocation is for a *diagram-owned* type, and which types a kind owns is
    // that module's vocabulary — the first entry of the diagram-type catalogue is a kind, not a type
    // it owns, and passing one for the other is how this step first reported a 400 as a defect.
    method: 'allocateDiagramEntityId',
    run: (r) =>
      r.allocateDiagramEntityId({
        diagram_type: 'datatype',
        entity_type: 'classifier',
        name_hint: 'Conformance classifier',
      }),
  },

  // ── Datatypes ───────────────────────────────────────────────────────────────
  { method: 'getDatatypeTypes', run: (r) => r.getDatatypeTypes({ limit: 5 }) },
  {
    method: 'getDatatypeTypeUsages',
    needs: ['datatypeTypeId'],
    run: (r, s) => r.getDatatypeTypeUsages(need(s, 'datatypeTypeId')),
  },

  // ── Matrices ────────────────────────────────────────────────────────────────
  {
    method: 'getMatrixConfig',
    needs: ['matrixId'],
    run: (r, s) => r.getMatrixConfig(need(s, 'matrixId')),
  },
  {
    method: 'previewMatrix',
    needs: ['entityId'],
    run: (r, s) =>
      r.previewMatrix({
        entity_ids: [need(s, 'entityId')],
        conn_type_configs: [],
        combined: true,
      }),
  },

  // ── Ontology and guidance ───────────────────────────────────────────────────
  {
    method: 'getOntologyClassification',
    needs: ['entityType'],
    run: (r, s) => r.getOntologyClassification(need(s, 'entityType')),
  },
  {
    method: 'getOntologyPair',
    needs: ['entityType'],
    run: (r, s) => r.getOntologyPair(need(s, 'entityType'), need(s, 'entityType')),
  },
  {
    method: 'getAuthoringGuidance',
    needs: ['entityType'],
    run: (r, s) => r.getAuthoringGuidance({ entityTypes: [need(s, 'entityType')] }),
  },

  // ── Documents ───────────────────────────────────────────────────────────────
  { method: 'listDocumentTypes', run: (r) => r.listDocumentTypes() },
  { method: 'listDocuments', run: (r) => r.listDocuments({ limit: 5 }) },
  {
    method: 'getDocument',
    needs: ['documentId'],
    run: (r, s) => r.getDocument(need(s, 'documentId')),
  },

  // ── Groups ──────────────────────────────────────────────────────────────────
  { method: 'listGroups', run: (r) => r.listGroups() },
  {
    method: 'listGroups',
    variant: 'by kind',
    needs: ['groupKind'],
    run: (r, s) => r.listGroups(need(s, 'groupKind')),
  },

  // ── Viewpoints ──────────────────────────────────────────────────────────────
  { method: 'listViewpointDefinitions', run: (r) => r.listViewpointDefinitions() },
  { method: 'getCriteriaCatalog', run: (r) => r.getCriteriaCatalog() },
  { method: 'getViewpointPins', run: (r) => r.getViewpointPins() },
  {
    method: 'getViewpointReferencers',
    needs: ['viewpointSlug'],
    run: (r, s) => r.getViewpointReferencers(need(s, 'viewpointSlug')),
  },
  {
    method: 'previewDeleteViewpointDefinition',
    needs: ['viewpointSlug'],
    run: (r, s) => r.previewDeleteViewpointDefinition(need(s, 'viewpointSlug')),
  },
  {
    method: 'getViewpointProjection',
    needs: ['diagramId'],
    run: (r, s) => r.getViewpointProjection(need(s, 'diagramId')),
  },
  {
    method: 'executeViewpoint',
    needs: ['viewpointSlug'],
    run: (r, s) => r.executeViewpoint({ slug: need(s, 'viewpointSlug'), limit: 5 }),
  },
  {
    method: 'executeViewpointProjection',
    needs: ['viewpointSlug'],
    run: (r, s) => r.executeViewpointProjection({ slug: need(s, 'viewpointSlug'), limit: 5 }),
  },
  {
    method: 'executeViewpointDiagram',
    needs: ['viewpointSlug'],
    run: (r, s) => r.executeViewpointDiagram({ slug: need(s, 'viewpointSlug'), limit: 5 }),
  },
  {
    method: 'summarizeViewpointQuery',
    run: (r) => r.summarizeViewpointQuery({ query_schema: 1 }),
  },
  {
    method: 'exportViewpointCsv',
    needs: ['viewpointSlug'],
    run: (r, s) => r.exportViewpointCsv({ slug: need(s, 'viewpointSlug') }),
  },

  // ── Promotion ───────────────────────────────────────────────────────────────
  {
    method: 'planPromotion',
    needs: ['entityId'],
    run: (r, s) => r.planPromotion({ entity_id: need(s, 'entityId') }),
  },
]

/** The label a report uses for a step: unique, and readable as the method it drives. */
export const stepLabel = (step: ReadStep): string =>
  step.variant === undefined ? step.method : `${step.method} (${step.variant})`
