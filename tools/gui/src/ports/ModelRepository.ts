import type { Effect } from 'effect'
import type { EnterpriseAdminRepository } from './EnterpriseAdminRepository'
import type { RepoError } from './repositoryErrors'
import type { SyncChangesResult } from '../domain/schemas-changes'
import type {
  Stats,
  EntityList,
  RenderedEntityDetail,
  RenderedEntityContext,
  ConnectionList,
  Neighbors,
  SearchResult,
  DocumentType,
  DocumentList,
  DocumentDetail,
  ArtifactSearchResult,
  ReferenceSearchResult,
  DiagramList,
  DiagramDetail,
  DiagramTypeSummary,
  DiagramTypeUiConfig,
  DatatypeTypeCatalog,
  DatatypeTypeUsages,
  AllocatedIdentifier,
  DiagramContext,
  DiagramEntityDiscovery,
  WriteResult,
  SyncDiagramToModelResult,
  DiagramRefs,
  OntologyClassification,
  OntologyPair,
  EntitySchemaInfo,
  DiagramContextEntity,
  EntityDisplayInfo,
  EntityDisplaySearchResult,
  DiagramPreviewResult,
  DiagramConnection,
  MatrixConfig,
  MatrixPreviewResult,
  PromotionPlan,
  PromotionResult,
  SyncStatus,
  SyncSaveResult,
  ServerInfo,
  ModuleSummary,
  WriteHelp,
  GroupList,
  EntityTaxonomy,
  AuthoringGuidance,
  DiagramViewpointProjection,
  ViewpointProjection,
  ViewpointDefinitionEnvelope,
  CriteriaCatalog,
  ViewpointPersistResult,
  ViewpointPins,
  ViewpointReferencer,
  ViewpointExecutionRequest,
  ViewpointExecutionResult,
  ViewpointDiagramResult,
} from '../domain'
import type { NotFoundError } from '../domain'
import type { MarkdownError } from '../application/MarkdownService'

export type Direction = 'any' | 'outbound' | 'inbound'

export type RepoScope = 'engagement' | 'global'

export interface ListParams {
  readonly domain?: string
  readonly artifactType?: string
  readonly status?: string
  readonly scope?: RepoScope
  readonly limit?: number
  readonly offset?: number
  readonly group?: string
  readonly metaOntology?: string
  /** Server-side ordering over the whole filtered population, applied before the page slice. */
  readonly sort?: string
  readonly order?: 'asc' | 'desc'
}

export type { RepoError }

/** Outbound port: the application's view of the model backend. */
export interface ModelRepository extends EnterpriseAdminRepository {
  readonly getServerInfo: () => Effect.Effect<ServerInfo, RepoError>
  readonly listModules: () => Effect.Effect<readonly ModuleSummary[], RepoError>
  readonly getStats: () => Effect.Effect<Stats, RepoError>
  readonly listEntities: (params?: ListParams) => Effect.Effect<EntityList, RepoError>
  readonly listEntityTaxonomy: (params?: ListParams) => Effect.Effect<EntityTaxonomy, RepoError>
  readonly getEntity: (id: string) => Effect.Effect<RenderedEntityDetail, RepoError | NotFoundError | MarkdownError>
  readonly getEntityContext: (
    id: string,
  ) => Effect.Effect<RenderedEntityContext, RepoError | NotFoundError | MarkdownError>
  readonly getConnections: (
    entityId: string, direction?: Direction, connType?: string,
  ) => Effect.Effect<ConnectionList, RepoError>
  readonly getNeighbors: (
    entityId: string, maxHops?: number,
  ) => Effect.Effect<Neighbors, RepoError>
  readonly search: (
    query: string, limit?: number,
  ) => Effect.Effect<SearchResult, RepoError>
  readonly listDiagrams: (params?: {
    diagram_type?: string; status?: string; group?: string; scope?: string;
  }) => Effect.Effect<DiagramList, RepoError>
  readonly listDiagramTypes: () => Effect.Effect<DiagramTypeSummary[], RepoError>
  readonly getDiagramTypeUiConfig: (type: string) => Effect.Effect<DiagramTypeUiConfig, RepoError | NotFoundError>
  readonly getDatatypeTypes: (params?: {
    query?: string; scope?: string; kind?: string; limit?: number;
    cursor?: string; diagramId?: string;
  }) => Effect.Effect<DatatypeTypeCatalog, RepoError>
  readonly getDatatypeTypeUsages: (typeId: string) => Effect.Effect<DatatypeTypeUsages, RepoError>
  /** `diagram_type` + `entity_type` are a composite key: the type must be one that diagram type owns. */
  readonly allocateDiagramEntityId: (body: {
    diagram_type: string; entity_type: string; name_hint?: string;
  }) => Effect.Effect<AllocatedIdentifier, RepoError>
  readonly getDiagram: (id: string) => Effect.Effect<DiagramDetail, RepoError | NotFoundError>
  readonly getDiagramContext: (id: string) => Effect.Effect<DiagramContext, RepoError | NotFoundError>
  readonly diagramImageUrl: (filename: string) => string
  readonly getDiagramRefs: (
    sourceId: string, targetId: string,
  ) => Effect.Effect<DiagramRefs, RepoError>
  readonly addConnection: (body: {
    source_entity: string; connection_type: string; target_entity: string;
    description?: string; src_multiplicity?: string; tgt_multiplicity?: string;
    specialization?: string;
    /** Attributes declared by the pair's effective metadata schema. */
    metadata?: Record<string, unknown>;
    dry_run?: boolean;
  }) => Effect.Effect<WriteResult, RepoError>
  /** Identity is the composite id; the body carries only what changes. */
  readonly editConnection: (connectionId: string, body: {
    description?: string; src_multiplicity?: string; tgt_multiplicity?: string;
    specialization?: string;
    /** Replaces the schema-declared attributes wholesale; {} clears them. */
    metadata?: Record<string, unknown>;
    dry_run?: boolean;
  }) => Effect.Effect<WriteResult, RepoError>
  readonly previewRemoveConnection: (connectionId: string) => Effect.Effect<WriteResult, RepoError>
  readonly removeConnection: (connectionId: string) => Effect.Effect<void, RepoError>
  /** A delta over a set-valued relation: what to add and remove, not what the set becomes. */
  readonly manageConnectionAssociations: (connectionId: string, body: {
    add_entities?: string[]; remove_entities?: string[];
    dry_run?: boolean;
  }) => Effect.Effect<WriteResult, RepoError>
  readonly getWriteHelp: () => Effect.Effect<WriteHelp, RepoError>
  readonly getOntologyClassification: (sourceType: string) => Effect.Effect<OntologyClassification, RepoError>
  readonly getOntologyPair: (sourceType: string, targetType: string) => Effect.Effect<OntologyPair, RepoError>
  readonly getAuthoringGuidance: (params: {
    entityTypes?: string[]; domains?: string[]; diagramType?: string; target?: string;
  }) => Effect.Effect<AuthoringGuidance, RepoError>
  readonly createEntity: (body: {
    artifact_type: string; name: string; summary?: string;
    properties?: Record<string, string>; attribute_types?: Record<string, string>;
    notes?: string; keywords?: string[]; specialization?: string; specializations?: string[];
    version?: string; status?: string;
    dry_run?: boolean;
  }) => Effect.Effect<WriteResult, RepoError>
  readonly editEntity: (id: string, body: {
    name?: string; summary?: string;
    properties?: Record<string, string>; attribute_types?: Record<string, string>;
    notes?: string; keywords?: string[]; specialization?: string; specializations?: string[];
    version?: string; status?: string;
    dry_run?: boolean;
  }) => Effect.Effect<WriteResult, RepoError>
  /**
   * What deleting this entity would do. Two names rather than one with a flag: the two are
   * different exchanges — a plan has a body, a committed deletion answers 204 and has none — and a
   * boolean whose value changes the return type is a signature that cannot be read.
   */
  readonly previewDeleteEntity: (id: string) => Effect.Effect<WriteResult, RepoError>
  readonly deleteEntity: (id: string) => Effect.Effect<void, RepoError>
  readonly getEntitySchemata: (artifactType: string, specialization?: string) => Effect.Effect<EntitySchemaInfo, RepoError>
  readonly getDiagramEntities: (diagramId: string) => Effect.Effect<DiagramContextEntity[], RepoError>
  readonly getDiagramConnections: (diagramId: string) => Effect.Effect<DiagramConnection[], RepoError>
  readonly getDiagramSvg: (diagramId: string) => Effect.Effect<string, RepoError>
  readonly getEntityDisplayItem: (artifactId: string) => Effect.Effect<EntityDisplayInfo, RepoError>
  readonly searchEntityDisplay: (params: {
    query: string
    limit?: number
    diagramType?: string
    domains?: string[]
    entityTypes?: string[]
    /** Exact keyword facet — every listed keyword must be on the entity. */
    keywords?: string[]
    cursor?: string
    /** Narrow the accepted entity types by this viewpoint's scope, intersected with diagramType's. */
    viewpoint?: string
  }) => Effect.Effect<EntityDisplaySearchResult, RepoError>
  readonly discoverDiagramEntities: (params: {
    includedEntityIds?: string[]
    query?: string
    diagramType?: string
    maxHops?: number
    limit?: number
    viewpoint?: string
  }) => Effect.Effect<DiagramEntityDiscovery, RepoError>
  readonly previewDiagram: (body: {
    diagram_type: string; name: string;
    entity_ids: string[]; connection_ids: string[];
    diagram_entities?: Record<string, unknown>;
  }) => Effect.Effect<DiagramPreviewResult, RepoError>
  readonly createDiagram: (body: {
    diagram_type: string; name: string;
    entity_ids: string[]; connection_ids: string[];
    diagram_entities?: Record<string, unknown>;
    keywords?: string[]; version?: string; status?: string;
    viewpoint?: { slug: string; version: number; enforcement_override?: 'off' | 'warn' | 'ghost' } | null;
    dry_run?: boolean;
  }) => Effect.Effect<WriteResult, RepoError>
  /** Whole-diagram replacement, so PUT: the body states what the diagram becomes, not a delta. */
  readonly editDiagram: (id: string, body: {
    diagram_type: string; name: string;
    entity_ids: string[]; connection_ids: string[];
    diagram_entities?: Record<string, unknown>;
    version?: string; status?: string;
    viewpoint?: { slug: string; version: number; enforcement_override?: 'off' | 'warn' | 'ghost' } | null;
    dry_run?: boolean;
  }) => Effect.Effect<WriteResult, RepoError>
  /**
   * Merge a whitelisted metadata delta into one datatype classifier. The server reads the file and
   * merges — the GUI sends only the target ids and the delta, never the whole diagram-entities map.
   *
   * Two methods rather than one with an optional `attribute_id`, because they address two different
   * resources and the server says so: `/…/entities/{clf}/metadata` and
   * `/…/entities/{clf}/attributes/{a}/metadata`, two operation ids, and a body that **forbids**
   * `attribute_id` outright. This port used to carry one method with that field in the body, which is
   * the shape the backend's redesign removed and which the client never followed: every attribute
   * metadata edit from the diagram sidebar answered 422, because the field the client sent to select
   * the resource is the field the server rejects. Nothing caught it because nothing had ever driven
   * the method — it was one of 42 in the conformance harness's unexercised register.
   */
  readonly patchDiagramClassifierMetadata: (id: string, classifierId: string, body: {
    patch: Record<string, unknown>; dry_run?: boolean;
  }) => Effect.Effect<WriteResult, RepoError>
  /** The same, one level deeper: the attribute is identity, not a body field. */
  readonly patchDiagramAttributeMetadata: (
    id: string, classifierId: string, attributeId: string, body: {
      patch: Record<string, unknown>; dry_run?: boolean;
    },
  ) => Effect.Effect<WriteResult, RepoError>
  readonly getViewpointProjection: (diagramId: string) => Effect.Effect<DiagramViewpointProjection, RepoError>
  readonly listViewpointDefinitions: () => Effect.Effect<readonly ViewpointDefinitionEnvelope[], RepoError>
  /** Fixed, unstyled content — repository-context execution by slug or ad-hoc query. */
  readonly executeViewpoint: (request: ViewpointExecutionRequest) => Effect.Effect<ViewpointExecutionResult, RepoError>
  /** GUI-only styled sibling of `executeViewpoint` — never exposed to MCP. */
  readonly executeViewpointProjection: (
    request: ViewpointExecutionRequest,
  ) => Effect.Effect<ViewpointProjection, RepoError>
  /** GUI-only ad-hoc ArchiMate-notation rendering behind the `diagram` execution
   * representation — never exposed to MCP, never persisted. */
  readonly executeViewpointDiagram: (
    request: ViewpointExecutionRequest,
  ) => Effect.Effect<ViewpointDiagramResult, RepoError>
  readonly getCriteriaCatalog: () => Effect.Effect<CriteriaCatalog, RepoError>
  readonly summarizeViewpointQuery: (query: unknown) => Effect.Effect<string, RepoError>
  readonly exportViewpointCsv: (body: {
    slug?: string; query?: unknown; parameters?: Record<string, unknown>; presentation?: unknown
  }) => Effect.Effect<string, RepoError>
  readonly createViewpointDefinition: (body: {
    definition: Record<string, unknown>; dry_run?: boolean; fork_of?: string
  }) => Effect.Effect<ViewpointPersistResult, RepoError>
  /** The slug comes from the path; the body carries the definition, whose own slug must agree. */
  readonly replaceViewpointDefinition: (slug: string, body: {
    definition: Record<string, unknown>; dry_run?: boolean
  }) => Effect.Effect<ViewpointPersistResult, RepoError>
  /** What deleting would do, and what stands in its way. Deletes nothing. */
  readonly previewDeleteViewpointDefinition: (
    slug: string,
  ) => Effect.Effect<ViewpointPersistResult, RepoError>
  /** Deletes, and reports nothing — a refusal arrives as a typed error, not as `ok: false`. */
  readonly deleteViewpointDefinition: (slug: string) => Effect.Effect<void, RepoError>
  readonly getViewpointReferencers: (slug: string) => Effect.Effect<readonly ViewpointReferencer[], RepoError>
  readonly getViewpointPins: () => Effect.Effect<ViewpointPins, RepoError>
  readonly setViewpointPins: (slugs: readonly string[]) => Effect.Effect<ViewpointPins, RepoError>
  readonly previewDeleteDiagram: (id: string) => Effect.Effect<WriteResult, RepoError>
  readonly deleteDiagram: (id: string) => Effect.Effect<void, RepoError>
  readonly syncDiagramToModel: (id: string, body: {
    dry_run?: boolean;
  }) => Effect.Effect<SyncDiagramToModelResult, RepoError>
  readonly setEdgeLabel: (id: string, edgeKey: string, body: {
    label: string | null; dry_run?: boolean;
  }) => Effect.Effect<WriteResult, RepoError>
  // Admin writes live in `EnterpriseAdminRepository`; this port extends it, so a caller still
  // sees one surface while the enterprise tier keeps its own file.
  readonly planPromotion: (body: {
    entity_id?: string;
    entity_ids?: string[];
    connection_ids?: string[];
    exclude_entity_ids?: string[];
    exclude_connection_ids?: string[];
    document_ids?: string[];
    diagram_ids?: string[];
  }) => Effect.Effect<PromotionPlan, RepoError>
  readonly executePromotion: (body: {
    entity_id?: string;
    entity_ids?: string[];
    connection_ids?: string[];
    exclude_entity_ids?: string[];
    exclude_connection_ids?: string[];
    document_ids?: string[];
    diagram_ids?: string[];
    conflict_resolutions?: Array<{
      engagement_id: string;
      strategy: 'accept_engagement' | 'accept_enterprise' | 'merge';
      merged_fields?: Record<string, unknown>;
    }>;
    group_mapping_resolutions?: Record<string, string>;
    dry_run?: boolean;
  }) => Effect.Effect<PromotionResult, RepoError>
  // ── Document methods ──────────────────────────────────────────────────────
  readonly listDocumentTypes: () => Effect.Effect<DocumentType[], RepoError>
  readonly listDocuments: (params?: {
    doc_type?: string; status?: string; limit?: number; offset?: number; group?: string; scope?: string;
  }) => Effect.Effect<DocumentList, RepoError>
  readonly getDocument: (id: string) => Effect.Effect<DocumentDetail, RepoError | NotFoundError>
  readonly createDocument: (body: {
    doc_type: string; title: string; body?: string;
    keywords?: string[]; extra_frontmatter?: Record<string, unknown>;
    version?: string; status?: string; dry_run?: boolean;
  }) => Effect.Effect<WriteResult, RepoError>
  readonly editDocument: (id: string, body: {
    title?: string; body?: string; keywords?: string[];
    extra_frontmatter?: Record<string, unknown>;
    status?: string; version?: string; dry_run?: boolean;
  }) => Effect.Effect<WriteResult, RepoError>
  readonly deleteDocument: (id: string) => Effect.Effect<void, RepoError>
  // ── Sync / save workflow ──────────────────────────────────────────────────
  readonly getSyncStatus: () => Effect.Effect<SyncStatus, RepoError>
  readonly saveEngagementChanges: (body: { message: string; push?: boolean }) => Effect.Effect<SyncSaveResult, RepoError>
  readonly saveEnterpriseChanges: (body: { message: string }) => Effect.Effect<SyncSaveResult, RepoError>
  readonly submitEnterpriseChanges: () => Effect.Effect<SyncSaveResult, RepoError>
  readonly withdrawEnterpriseChanges: () => Effect.Effect<SyncSaveResult, RepoError>
  readonly getChanges: (repo: 'engagement' | 'enterprise') => Effect.Effect<SyncChangesResult, RepoError>
  readonly artifactSearch: (q: string, params?: {
    limit?: number; include_documents?: boolean; include_diagrams?: boolean;
  }) => Effect.Effect<ArtifactSearchResult, RepoError>
  readonly searchReferenceArtifacts: (params: {
    q?: string
    kind?: 'entity' | 'diagram' | 'document'
    domains?: string[]
    entity_types?: string[]
    doc_types?: string[]
    limit?: number
  }) => Effect.Effect<ReferenceSearchResult, RepoError>
  readonly getMatrixConfig: (id: string) => Effect.Effect<MatrixConfig, RepoError>
  readonly previewMatrix: (body: object) => Effect.Effect<MatrixPreviewResult, RepoError>
  readonly createMatrixDiagram: (body: object) => Effect.Effect<WriteResult, RepoError>
  readonly editMatrixDiagram: (id: string, body: object) => Effect.Effect<WriteResult, RepoError>
  // ── Group lifecycle ───────────────────────────────────────────────────────────
  readonly listGroups: (kind?: string) => Effect.Effect<GroupList, RepoError>
  readonly createGroup: (body: { kind: string; slug: string; name: string; description?: string; order?: number; meta_ontology?: string; type_filter?: string[] }) => Effect.Effect<Record<string, unknown>, RepoError>
  // A group is named by the pair (axis kind, slug), and both are path parameters — so both are
  // arguments here rather than fields of a body that would say the same thing twice.
  readonly renameGroup: (kind: string, slug: string, body: { name?: string; new_slug?: string }) => Effect.Effect<Record<string, unknown>, RepoError>
  readonly archiveGroup: (kind: string, slug: string, body: { confirm?: string }) => Effect.Effect<Record<string, unknown>, RepoError>
  readonly unarchiveGroup: (kind: string, slug: string) => Effect.Effect<Record<string, unknown>, RepoError>
  readonly deleteGroup: (kind: string, slug: string, confirm?: string) => Effect.Effect<Record<string, unknown>, RepoError>
  readonly updateGroup: (kind: string, slug: string, body: { name?: string; description?: string; meta_ontology?: string; type_filter?: string[] | null }) => Effect.Effect<Record<string, unknown>, RepoError>
}
