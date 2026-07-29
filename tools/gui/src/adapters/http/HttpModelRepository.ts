import { Effect, Schema, Either } from 'effect'
import type { ModelRepository, ListParams, Direction } from '../../ports/ModelRepository'
import { NetworkError } from '../../domain/errors'
import {
  StatsSchema,
  EntityListSchema,
  EntityTaxonomySchema,
  EntityDetailSchema,
  EntityContextSchema,
  ConnectionListSchema,
  NeighborsSchema,
  SearchHitSchema,
  DocumentTypesSchema,
  DocumentListSchema,
  DocumentDetailSchema,
  ArtifactSearchResultSchema,
  ReferenceSearchResultSchema,
  DiagramListSchema,
  DiagramDetailSchema,
  DiagramTypeSummarySchema,
  DiagramTypeUiConfigSchema,
  DatatypeTypeCatalogSchema,
  DatatypeTypeUsagesSchema,
  AllocatedIdentifierSchema,
  DiagramContextSchema,
  DiagramEntityDiscoverySchema,
  WriteResultSchema,
  SyncDiagramToModelResultSchema,
  DiagramRefsSchema,
  OntologyClassificationSchema,
  OntologyPairSchema,
  EntitySchemaInfoSchema,
  EntitySummarySchema,
  EntityDisplayInfoSchema,
  EntityDisplaySearchResultSchema,
  DiagramPreviewResultSchema,
  DiagramConnectionSchema,
  MatrixConfigSchema,
  MatrixPreviewResultSchema,
  PromotionPlanSchema,
  PromotionResultSchema,
  SyncStatusSchema,
  SyncSaveResultSchema,
  ServerInfoSchema,
  ModuleSummaryListSchema,
  WriteHelpSchema,
  GroupListSchema,
  AuthoringGuidanceSchema,
  ViewpointProjectionSchema,
  ViewpointDiagramResultSchema,
  ViewpointDefinitionListSchema,
  CriteriaCatalogSchema,
  ViewpointSummarizeResultSchema,
  ViewpointPersistResultSchema,
  ViewpointPinsSchema,
  ViewpointReferencerListSchema,
  ViewpointExecutionResultSchema,
} from '../../domain/schemas'
import { SyncChangesResultSchema } from '../../domain/schemas-changes'
import {
  buildUrl, deleteReq, fetchJson, fetchJsonNotFound, fetchText, fetchWithTimeout,
  patchJson, postJson, putJson,
} from './httpTransport'
import { parseMarkdown } from '../../application/MarkdownService'

// Viewpoint execution runs bounded graph derivation over the scoped population — legitimately
// slower than the CRUD/read endpoints above, especially against a cold index. The 10s transport
// default exists to fail fast on a genuinely hung request; that's the wrong bound for these routes.
const VIEWPOINT_EXECUTION_TIMEOUT_MS = 60000
let serverInfoPromise: Promise<unknown> | null = null

// ── Factory ───────────────────────────────────────────────────────────────────

export const makeHttpModelRepository = (): ModelRepository => ({
  getServerInfo: () => Effect.tryPromise({
    try: async () => {
      if (serverInfoPromise === null) {
        serverInfoPromise = fetchWithTimeout(buildUrl('/server-info', undefined, true))
          .then(async (resp) => {
            if (!resp.ok) throw new NetworkError({ status: resp.status, message: resp.statusText })
            return resp.json() as Promise<unknown>
          })
          .catch((e) => {
            serverInfoPromise = null
            throw e
          })
      }
      return await serverInfoPromise
    },
    catch: (e) =>
      e instanceof NetworkError ? e : new NetworkError({ status: 0, message: String(e) }),
  }).pipe(Effect.flatMap(Schema.decodeUnknown(ServerInfoSchema))),
  listModules: () => fetchJson(buildUrl('/modules'), ModuleSummaryListSchema),
  getStats: () => fetchJson(buildUrl('/stats'), StatsSchema),

  listEntities: (params: ListParams = {}) =>
    fetchJson(buildUrl('/entities', {
      domain: params.domain, artifact_type: params.artifactType,
      status: params.status, scope: params.scope, limit: params.limit, offset: params.offset,
      group: params.group, meta_ontology: params.metaOntology,
      sort: params.sort, order: params.order,
    }), EntityListSchema),

  listEntityTaxonomy: (params: ListParams = {}) =>
    fetchJson(buildUrl('/entity-taxonomy', {
      scope: params.scope, meta_ontology: params.metaOntology, group: params.group,
    }), EntityTaxonomySchema),

  getEntity: (id: string) =>
    fetchJsonNotFound(buildUrl('/entity', { id }), EntityDetailSchema, id).pipe(
      Effect.flatMap((entity) => {
        if (entity.content_text) {
          return parseMarkdown(entity.content_text, 'model').pipe(
            Effect.map((html) => ({ ...entity, content_html: html })),
          )
        }
        return Effect.succeed({ ...entity })
      }),
    ),

  getEntityContext: (id: string) =>
    fetchJsonNotFound(buildUrl('/entity-context', { id }), EntityContextSchema, id).pipe(
      Effect.flatMap((context) => {
        if (context.entity.content_text) {
          return parseMarkdown(context.entity.content_text, 'model').pipe(
            Effect.map((html) => ({ ...context, entity: { ...context.entity, content_html: html } })),
          )
        }
        return Effect.succeed({ ...context, entity: { ...context.entity } })
      }),
    ),

  getConnections: (entityId: string, direction: Direction = 'any', connType?: string) =>
    fetchJson(buildUrl('/connections', { entity_id: entityId, direction, conn_type: connType }), ConnectionListSchema),
  getNeighbors: (entityId: string, maxHops = 1) =>
    fetchJson(buildUrl('/neighbors', { entity_id: entityId, max_hops: maxHops }), NeighborsSchema),
  search: (query: string, limit = 20) => {
    const RawSearchResultSchema = Schema.Struct({ query: Schema.String, hits: Schema.Array(Schema.Unknown) })
    const decodeHit = Schema.decodeUnknownEither(SearchHitSchema)
    return fetchJson(buildUrl('/search', { q: query, limit }), RawSearchResultSchema).pipe(
      Effect.map((raw) => ({
        query: raw.query,
        hits: raw.hits.flatMap((h) => {
          const result = decodeHit(h)
          if (Either.isLeft(result)) {
            console.warn('[search] skipped unrecognised search hit', h)
            return []
          }
          return [result.right]
        }),
      })),
    )
  },

  listDocumentTypes: () =>
    fetchJson(buildUrl('/document-types'), DocumentTypesSchema).pipe(
      Effect.map((items) => [...items] as import('../../domain').DocumentType[]),
    ),

  listDocuments: (
    params: {
      doc_type?: string; status?: string; limit?: number; offset?: number; group?: string; scope?: string;
    } = {},
  ) =>
    fetchJson(buildUrl('/documents', {
      doc_type: params.doc_type, status: params.status,
      limit: params.limit, offset: params.offset, group: params.group, scope: params.scope,
    }), DocumentListSchema),

  getDocument: (id) =>
    fetchJsonNotFound(buildUrl('/document', { id }), DocumentDetailSchema, id),

  createDocument: (body) =>
    postJson(buildUrl('/document'), body, WriteResultSchema),

  editDocument: (id, body) =>
    putJson(buildUrl(`/document/${encodeURIComponent(id)}`), body, WriteResultSchema),

  deleteDocument: (id, dry_run) =>
    deleteReq(buildUrl(`/document/${encodeURIComponent(id)}`, { dry_run }), WriteResultSchema),

  artifactSearch: (q, params = {}) =>
    fetchJson(buildUrl('/artifact-search', { q, ...params }), ArtifactSearchResultSchema),

  searchReferenceArtifacts: (params) =>
    fetchJson(buildUrl('/reference-search', {
      q: params.q, kind: params.kind, domains: params.domains?.join(','),
      entity_types: params.entity_types?.join(','), doc_types: params.doc_types?.join(','), limit: params.limit,
    }), ReferenceSearchResultSchema),

  listDiagrams: (params: { diagram_type?: string; status?: string; group?: string; scope?: string } = {}) =>
    fetchJson(buildUrl('/diagrams', {
      diagram_type: params.diagram_type, status: params.status, group: params.group, scope: params.scope,
    }), DiagramListSchema),

  listDiagramTypes: () =>
    fetchJson(buildUrl('/diagram-types'), Schema.Array(DiagramTypeSummarySchema))
      .pipe(Effect.map((arr) => [...arr])),

  getDiagramTypeUiConfig: (type: string) =>
    fetchJsonNotFound(buildUrl(`/diagram-types/${encodeURIComponent(type)}/ui-config`), DiagramTypeUiConfigSchema, type),

  getDatatypeTypes: (params = {}) =>
    fetchJson(buildUrl('/diagram-types/datatype/types', {
      query: params.query,
      scope: params.scope,
      kind: params.kind,
      limit: params.limit,
      cursor: params.cursor,
      diagram_id: params.diagramId,
    }), DatatypeTypeCatalogSchema),

  getDatatypeTypeUsages: (typeId: string) =>
    fetchJson(buildUrl('/diagram-types/datatype/type-usages', { type_id: typeId }), DatatypeTypeUsagesSchema),

  allocateDiagramEntityId: (body) =>
    postJson(buildUrl('/identifiers/allocate'), body, AllocatedIdentifierSchema),

  getDiagram: (id: string) =>
    fetchJsonNotFound(buildUrl('/diagram', { id }), DiagramDetailSchema, id),

  getDiagramContext: (id: string) =>
    fetchJsonNotFound(buildUrl('/diagram-context', { id }), DiagramContextSchema, id),

  diagramImageUrl: (filename: string) => `/api/diagram-image/${encodeURIComponent(filename)}`,

  getDiagramRefs: (sourceId: string, targetId: string) =>
    fetchJson(buildUrl('/diagram-refs', { source_id: sourceId, target_id: targetId }), DiagramRefsSchema),

  addConnection: (body) => postJson(buildUrl('/connection'), body, WriteResultSchema),

  editConnection: (body) => postJson(buildUrl('/connection/edit'), body, WriteResultSchema),

  removeConnection: (body) => postJson(buildUrl('/connection/remove'), body, WriteResultSchema),

  manageConnectionAssociations: (body) =>
    postJson(buildUrl('/connection/associate'), body, WriteResultSchema),

  getWriteHelp: () => fetchJson(buildUrl('/write-help'), WriteHelpSchema),

  getOntologyClassification: (sourceType: string) =>
    fetchJson(buildUrl('/ontology', { source_type: sourceType }), OntologyClassificationSchema),
  getOntologyPair: (sourceType: string, targetType: string) =>
    fetchJson(buildUrl('/ontology', { source_type: sourceType, target_type: targetType }), OntologyPairSchema),
  getAuthoringGuidance: (params) =>
    fetchJson(buildUrl('/authoring-guidance', {
      entity_type: params.entityTypes?.length ? params.entityTypes.join(',') : undefined,
      domain: params.domains?.length ? params.domains.join(',') : undefined,
      diagram_type: params.diagramType,
      target: params.target,
    }), AuthoringGuidanceSchema),

  createEntity: (body) => postJson(buildUrl('/entity'), body, WriteResultSchema),

  editEntity: (body) => postJson(buildUrl('/entity/edit'), body, WriteResultSchema),
  deleteEntity: (body) => postJson(buildUrl('/entity/remove'), body, WriteResultSchema),

  getEntitySchemata: (artifactType: string, specialization?: string) =>
    fetchJson(
      buildUrl('/entity-schemata', {
        artifact_type: artifactType,
        specialization: specialization || undefined,
      }),
      EntitySchemaInfoSchema,
    ),

  getDiagramEntities: (diagramId: string) =>
    fetchJson(buildUrl('/diagram-entities', { id: diagramId }), Schema.Array(EntitySummarySchema)).pipe(
      Effect.map((arr) => arr as import('../../domain').EntitySummary[]),
    ),

  getDiagramConnections: (diagramId: string) =>
    fetchJson(buildUrl('/diagram-connections', { id: diagramId }), Schema.Array(DiagramConnectionSchema)).pipe(
      Effect.map((arr) => arr as import('../../domain').DiagramConnection[]),
    ),

  getDiagramSvg: (diagramId: string) =>
    fetchText(buildUrl('/diagram-svg', { id: diagramId })),

  getEntityDisplayItem: (artifactId: string) =>
    fetchJson(buildUrl('/entity-display-item', { id: artifactId }), EntityDisplayInfoSchema),

  searchEntityDisplay: ({ query, limit = 20, diagramType, domains, entityTypes, keywords, cursor, viewpoint }) =>
    fetchJson(buildUrl('/entity-display-search', {
      q: query, limit, diagram_type: diagramType,
      domains: domains?.join(','), entity_types: entityTypes?.join(','),
      keywords: keywords?.join(','), cursor, viewpoint,
    }), EntityDisplaySearchResultSchema),
  discoverDiagramEntities: ({ includedEntityIds = [], query, diagramType, maxHops = 2, limit = 20, viewpoint }) =>
    fetchJson(buildUrl('/diagram-entity-discovery', {
      q: query, diagram_type: diagramType, max_hops: maxHops, limit,
      included_entity_ids: includedEntityIds.join(','), viewpoint,
    }), DiagramEntityDiscoverySchema),

  previewDiagram: (body) =>
    postJson(buildUrl('/diagram/preview'), body, DiagramPreviewResultSchema),

  createDiagram: (body) => postJson(buildUrl('/diagram'), body, WriteResultSchema),
  editDiagram: (body) => postJson(buildUrl('/diagram/edit'), body, WriteResultSchema),
  patchDiagramEntityMetadata: (body) => postJson(buildUrl('/diagram/entity-metadata'), body, WriteResultSchema),
  deleteDiagram: (body) =>
    postJson(buildUrl('/diagram/remove'), body, WriteResultSchema),
  getViewpointProjection: (diagramId: string) =>
    fetchJson(
      buildUrl(`/diagrams/${encodeURIComponent(diagramId)}/viewpoint-projection`),
      ViewpointProjectionSchema,
      VIEWPOINT_EXECUTION_TIMEOUT_MS,
    ),
  listViewpointDefinitions: () =>
    fetchJson(buildUrl('/viewpoints'), ViewpointDefinitionListSchema).pipe(Effect.map((r) => r.viewpoints)),
  getCriteriaCatalog: () => fetchJson(buildUrl('/viewpoints/criteria-catalog'), CriteriaCatalogSchema),
  executeViewpoint: (request) =>
    postJson(buildUrl('/viewpoints/execute'), request, ViewpointExecutionResultSchema, VIEWPOINT_EXECUTION_TIMEOUT_MS),
  executeViewpointProjection: (request) =>
    postJson(buildUrl('/viewpoints/execute-projection'), request, ViewpointProjectionSchema, VIEWPOINT_EXECUTION_TIMEOUT_MS),
  executeViewpointDiagram: (request) =>
    postJson(buildUrl('/viewpoints/execute-diagram'), request, ViewpointDiagramResultSchema, VIEWPOINT_EXECUTION_TIMEOUT_MS),
  summarizeViewpointQuery: (query: unknown) =>
    postJson(buildUrl('/viewpoints/summarize'), { query }, ViewpointSummarizeResultSchema).pipe(
      Effect.map((r) => r.summary),
    ),
  exportViewpointCsv: (body) =>
    Effect.tryPromise({
      try: async () => {
        const resp = await fetchWithTimeout(buildUrl('/viewpoints/export-csv'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })
        if (!resp.ok) {
          const text = await resp.text().catch(() => resp.statusText)
          throw new NetworkError({ status: resp.status, message: text })
        }
        return resp.text()
      },
      catch: (e) => (e instanceof NetworkError ? e : new NetworkError({ status: 0, message: String(e) })),
    }),
  createViewpointDefinition: (body) => postJson(buildUrl('/viewpoints'), body, ViewpointPersistResultSchema),
  editViewpointDefinition: (body) => postJson(buildUrl('/viewpoints/edit'), body, ViewpointPersistResultSchema),
  deleteViewpointDefinition: (body) => postJson(buildUrl('/viewpoints/remove'), body, ViewpointPersistResultSchema),
  getViewpointReferencers: (slug: string) =>
    fetchJson(buildUrl(`/viewpoints/${encodeURIComponent(slug)}/referencers`), ViewpointReferencerListSchema).pipe(
      Effect.map((r) => r.referencers),
    ),
  getViewpointPins: () => fetchJson(buildUrl('/viewpoints/pins'), ViewpointPinsSchema),
  setViewpointPins: (slugs: readonly string[]) =>
    putJson(buildUrl('/viewpoints/pins'), { slugs: [...slugs] }, ViewpointPinsSchema),
  syncDiagramToModel: (body) =>
    postJson(buildUrl('/diagram/sync'), body, SyncDiagramToModelResultSchema),

  setEdgeLabel: (body) =>
    putJson(buildUrl('/diagram/edge-label'), body, WriteResultSchema),

  getMatrixConfig: (id: string) =>
    fetchJson(buildUrl('/matrix-config', { id }), MatrixConfigSchema),

  previewMatrix: (body: object) =>
    postJson(buildUrl('/matrix/preview'), body, MatrixPreviewResultSchema),

  createMatrixDiagram: (body: object) =>
    postJson(buildUrl('/matrix'), body, WriteResultSchema),

  editMatrixDiagram: (body: object) =>
    postJson(buildUrl('/matrix/edit'), body, WriteResultSchema),

  adminCreateEntity: (body) =>
    postJson(buildUrl('/entity', undefined, true), body, WriteResultSchema),
  adminEditEntity: (body) =>
    postJson(buildUrl('/entity/edit', undefined, true), body, WriteResultSchema),
  adminDeleteEntity: (body) =>
    postJson(buildUrl('/entity/remove', undefined, true), body, WriteResultSchema),
  adminAddConnection: (body) =>
    postJson(buildUrl('/connection', undefined, true), body, WriteResultSchema),
  adminRemoveConnection: (body) =>
    postJson(buildUrl('/connection/remove', undefined, true), body, WriteResultSchema),
  adminDeleteDiagram: (body) =>
    postJson(buildUrl('/diagram/remove', undefined, true), body, WriteResultSchema),

  planPromotion: (body) =>
    postJson(buildUrl('/promote/plan'), body, PromotionPlanSchema),

  executePromotion: (body) =>
    postJson(buildUrl('/promote/execute'), body, PromotionResultSchema),

  getSyncStatus: () => fetchJson('/api/sync/status', SyncStatusSchema),
  saveEngagementChanges: (body) => postJson('/api/sync/engagement/save', { push: true, ...body }, SyncSaveResultSchema),
  saveEnterpriseChanges: (body) => postJson('/api/sync/enterprise/save', body, SyncSaveResultSchema),
  submitEnterpriseChanges: () => postJson('/api/sync/enterprise/submit', {}, SyncSaveResultSchema),
  withdrawEnterpriseChanges: () => postJson('/api/sync/enterprise/withdraw', { confirm: true }, SyncSaveResultSchema),
  getChanges: (repo) => fetchJson(buildUrl('/sync/changes', { repo }), SyncChangesResultSchema),

  listGroups: (kind?: string) =>
    fetchJson(buildUrl('/groups', kind ? { kind } : undefined), GroupListSchema),
  createGroup: (body) =>
    postJson(buildUrl('/group'), body, Schema.Record({ key: Schema.String, value: Schema.Unknown })),
  renameGroup: (body) =>
    putJson(buildUrl('/group'), body, Schema.Record({ key: Schema.String, value: Schema.Unknown })),
  archiveGroup: (body) =>
    postJson(buildUrl('/group/archive'), body, Schema.Record({ key: Schema.String, value: Schema.Unknown })),
  unarchiveGroup: (body) =>
    postJson(buildUrl('/group/unarchive'), body, Schema.Record({ key: Schema.String, value: Schema.Unknown })),
  deleteGroup: ({ kind, target, confirm }) =>
    deleteReq(buildUrl('/group', { kind, target, confirm }), Schema.Record({ key: Schema.String, value: Schema.Unknown })),
  updateGroup: (body) =>
    patchJson(buildUrl('/group'), body, Schema.Record({ key: Schema.String, value: Schema.Unknown })),
})
