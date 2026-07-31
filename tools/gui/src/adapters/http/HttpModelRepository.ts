import { Effect, Schema, Either } from 'effect'
import type { ModelRepository, ListParams, Direction } from '../../ports/ModelRepository'
import { NetworkError } from '../../domain/errors'
import {
  StatsSchema,
  EntityListSchema,
  EntityTaxonomySchema,
  EntityDetailSchema,
  EntityContextSchema,
  ConnectionListResponseSchema,
  DirectNeighborhoodSchema,
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
} from '../../domain/schemas'
import { SyncChangesResultSchema } from '../../domain/schemas-changes'
import {
  buildUrl, deleteNoContent, deleteReq, entityAddress, fetchJson, fetchJsonNotFound, fetchText,
  fetchWithTimeout, patchJson, postJson, putJson,
} from './httpTransport'
import { encodeIdentitySegment } from '../../ui/router/artifactRoutes'
import { parseMarkdown } from '../../application/MarkdownService'
import { enterpriseAdminMethods } from './HttpEnterpriseAdminRepository'
import { viewpointMethods } from './HttpViewpointRepository'

// Timeout budgets are no longer set here. Viewpoint execution and the other derived-graph
// routes are classified in `routeTimeoutPolicy`, which the transport and the dev proxy both
// read — a budget passed at the call site could only ever agree with the proxy by coincidence.
let serverInfoPromise: Promise<unknown> | null = null

// A group is addressed by the pair (axis kind, slug); both segments are encoded, because a slug is
// author-chosen text and an axis is a vocabulary term neither of which the URL grammar guarantees.
const groupPath = (kind: string, slug: string, action = ''): string =>
  `/groups/${encodeIdentitySegment(kind)}/${encodeIdentitySegment(slug)}${action}`
const groupUrl = (kind: string, slug: string, action = ''): string =>
  buildUrl(groupPath(kind, slug, action))

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
    fetchJsonNotFound(entityAddress(id), EntityDetailSchema, id).pipe(
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
    fetchJsonNotFound(
      buildUrl(`/entities/${encodeIdentitySegment(id)}/context`), EntityContextSchema, id,
    ).pipe(
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
    fetchJson(
      buildUrl('/connections', { entity_id: entityId, direction, conn_type: connType }),
      ConnectionListResponseSchema,
    ).pipe(Effect.map((response) => response.items)),
  getNeighbors: (entityId: string, maxHops = 1) =>
    fetchJson(
      buildUrl(`/entities/${encodeIdentitySegment(entityId)}/neighbors`, { max_hops: maxHops }),
      DirectNeighborhoodSchema,
    ).pipe(Effect.map((response) => response.hops)),
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
    fetchJsonNotFound(buildUrl(`/documents/${encodeIdentitySegment(id)}`), DocumentDetailSchema, id),

  createDocument: (body) =>
    postJson(buildUrl('/documents'), body, WriteResultSchema),

  editDocument: (id, body) =>
    patchJson(buildUrl(`/documents/${encodeIdentitySegment(id)}`), body, WriteResultSchema),

  deleteDocument: (id) =>
    deleteNoContent(buildUrl(`/documents/${encodeIdentitySegment(id)}`)),

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
    fetchJson(
      buildUrl(`/diagram-types/datatype/types/${encodeIdentitySegment(typeId)}/usages`),
      DatatypeTypeUsagesSchema,
    ),

  allocateDiagramEntityId: (body) =>
    postJson(buildUrl('/identifiers/allocate'), body, AllocatedIdentifierSchema),

  getDiagram: (id: string) =>
    fetchJsonNotFound(buildUrl(`/diagrams/${encodeIdentitySegment(id)}`), DiagramDetailSchema, id),

  getDiagramContext: (id: string) =>
    fetchJsonNotFound(buildUrl(`/diagrams/${encodeIdentitySegment(id)}/context`), DiagramContextSchema, id),

  diagramImageUrl: (filename: string) => `/api/diagram-images/${encodeURIComponent(filename)}`,

  getDiagramRefs: (sourceId: string, targetId: string) =>
    fetchJson(
      buildUrl('/diagram-refs', { source_id: sourceId, target_id: targetId }),
      Schema.Struct({ items: DiagramRefsSchema }),
    ).pipe(Effect.map((r) => r.items)),

  addConnection: (body) => postJson(buildUrl('/connections'), body, WriteResultSchema),

  editConnection: (connectionId, body) =>
    patchJson(buildUrl(`/connections/${encodeIdentitySegment(connectionId)}`), body, WriteResultSchema),

  previewRemoveConnection: (connectionId) =>
    deleteReq(
      buildUrl(`/connections/${encodeIdentitySegment(connectionId)}`, { dry_run: true }),
      WriteResultSchema,
    ),
  removeConnection: (connectionId) =>
    deleteNoContent(
      buildUrl(`/connections/${encodeIdentitySegment(connectionId)}`, { dry_run: false }),
    ),

  manageConnectionAssociations: (connectionId, body) =>
    patchJson(
      buildUrl(`/connections/${encodeIdentitySegment(connectionId)}/associated-entities`),
      body,
      WriteResultSchema,
    ),

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

  createEntity: (body) => postJson(buildUrl('/entities'), body, WriteResultSchema),

  editEntity: (id, body) =>
    patchJson(buildUrl(`/entities/${encodeIdentitySegment(id)}`), body, WriteResultSchema),
  previewDeleteEntity: (id) =>
    deleteReq(buildUrl(`/entities/${encodeIdentitySegment(id)}`, { dry_run: true }), WriteResultSchema),
  deleteEntity: (id) =>
    deleteNoContent(buildUrl(`/entities/${encodeIdentitySegment(id)}`, { dry_run: false })),

  getEntitySchemata: (artifactType: string, specialization?: string) =>
    fetchJson(
      buildUrl(`/entity-schemata/${encodeIdentitySegment(artifactType)}`, {
        specialization: specialization || undefined,
      }),
      EntitySchemaInfoSchema,
    ),

  getDiagramEntities: (diagramId: string) =>
    fetchJson(
      buildUrl(`/diagrams/${encodeIdentitySegment(diagramId)}/entities`),
      Schema.Struct({ items: Schema.Array(EntitySummarySchema) }),
    ).pipe(Effect.map((r) => r.items as import('../../domain').EntitySummary[])),

  getDiagramConnections: (diagramId: string) =>
    fetchJson(
      buildUrl(`/diagrams/${encodeIdentitySegment(diagramId)}/connections`),
      Schema.Struct({ items: Schema.Array(DiagramConnectionSchema) }),
    ).pipe(Effect.map((r) => r.items as import('../../domain').DiagramConnection[])),

  getDiagramSvg: (diagramId: string) =>
    fetchText(buildUrl(`/diagrams/${encodeIdentitySegment(diagramId)}/svg`)),

  getEntityDisplayItem: (artifactId: string) =>
    fetchJson(
      buildUrl(`/entities/${encodeIdentitySegment(artifactId)}/display-item`),
      EntityDisplayInfoSchema,
    ),

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
    postJson(buildUrl('/diagrams/preview'), body, DiagramPreviewResultSchema),

  createDiagram: (body) => postJson(buildUrl('/diagrams'), body, WriteResultSchema),
  editDiagram: (id, body) =>
    putJson(buildUrl(`/diagrams/${encodeIdentitySegment(id)}`), body, WriteResultSchema),
  patchDiagramEntityMetadata: (id, classifierId, body) =>
    patchJson(
      buildUrl(
        `/diagrams/${encodeIdentitySegment(id)}/entities/${encodeIdentitySegment(classifierId)}/metadata`,
      ),
      body,
      WriteResultSchema,
    ),
  previewDeleteDiagram: (id) =>
    deleteReq(buildUrl(`/diagrams/${encodeIdentitySegment(id)}`, { dry_run: true }), WriteResultSchema),
  deleteDiagram: (id) =>
    deleteNoContent(buildUrl(`/diagrams/${encodeIdentitySegment(id)}`, { dry_run: false })),
  ...viewpointMethods(),
  syncDiagramToModel: (id, body) =>
    postJson(
      buildUrl(`/diagrams/${encodeIdentitySegment(id)}/sync`), body, SyncDiagramToModelResultSchema,
    ),

  setEdgeLabel: (id, edgeKey, body) =>
    putJson(
      buildUrl(`/diagrams/${encodeIdentitySegment(id)}/edges/${encodeIdentitySegment(edgeKey)}/label`),
      body,
      WriteResultSchema,
    ),

  getMatrixConfig: (id: string) =>
    fetchJson(buildUrl(`/matrices/${encodeIdentitySegment(id)}/config`), MatrixConfigSchema),

  previewMatrix: (body: object) =>
    postJson(buildUrl('/matrices/preview'), body, MatrixPreviewResultSchema),

  createMatrixDiagram: (body: object) =>
    postJson(buildUrl('/matrices'), body, WriteResultSchema),

  editMatrixDiagram: (id: string, body: object) =>
    putJson(buildUrl(`/matrices/${encodeIdentitySegment(id)}`), body, WriteResultSchema),

  ...enterpriseAdminMethods(),

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
  createGroup: (body) => postJson(buildUrl('/groups'), body, Schema.Record({ key: Schema.String, value: Schema.Unknown })),
  renameGroup: (kind, slug, body) =>
    postJson(groupUrl(kind, slug, '/rename'), body, Schema.Record({ key: Schema.String, value: Schema.Unknown })),
  archiveGroup: (kind, slug, body) =>
    postJson(groupUrl(kind, slug, '/archive'), body, Schema.Record({ key: Schema.String, value: Schema.Unknown })),
  unarchiveGroup: (kind, slug) =>
    postJson(groupUrl(kind, slug, '/unarchive'), {}, Schema.Record({ key: Schema.String, value: Schema.Unknown })),
  deleteGroup: (kind, slug, confirm) =>
    deleteReq(buildUrl(groupPath(kind, slug), { confirm }), Schema.Record({ key: Schema.String, value: Schema.Unknown })),
  updateGroup: (kind, slug, body) => patchJson(groupUrl(kind, slug), body, Schema.Record({ key: Schema.String, value: Schema.Unknown })),
})
