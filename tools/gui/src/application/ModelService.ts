import type { ModelRepository, ListParams, Direction } from '../ports/ModelRepository'

/**
 * Application service: use-case orchestration layer.
 * Wraps the outbound port and exposes named operations for the UI.
 */
export type ModelService = ReturnType<typeof makeModelService>

export const makeModelService = (repo: ModelRepository) =>
  ({
    getServerInfo: () => repo.getServerInfo(),
    listModules: () => repo.listModules(),
    getStats: () => repo.getStats(),
    listEntities: (params: ListParams = {}) => repo.listEntities(params),
    listEntityTaxonomy: (params: ListParams = {}) => repo.listEntityTaxonomy(params),
    listEntitiesGlobal: (params: ListParams = {}) => repo.listEntities({ ...params, scope: 'global' }),
    getEntity: (id: string) => repo.getEntity(id),
    getEntityContext: (id: string) => repo.getEntityContext(id),
    getConnections: (entityId: string, direction: Direction = 'any') =>
      repo.getConnections(entityId, direction),
    getConnectionsAmong: (entityIds: readonly string[]) => repo.getConnectionsAmong(entityIds),
    search: (query: string, limit?: number) => repo.search(query, limit),
    listDocumentTypes: () => repo.listDocumentTypes(),
    listDocuments: (params?: Parameters<ModelRepository['listDocuments']>[0]) => repo.listDocuments(params),
    getDocument: (id: string) => repo.getDocument(id),
    createDocument: (body: Parameters<ModelRepository['createDocument']>[0]) => repo.createDocument(body),
    editDocument: (id: string, body: Parameters<ModelRepository['editDocument']>[1]) => repo.editDocument(id, body),
    deleteDocument: (id: string) => repo.deleteDocument(id),
    artifactSearch: (query: string, params?: Parameters<ModelRepository['artifactSearch']>[1]) =>
      repo.artifactSearch(query, params),
    searchReferenceArtifacts: (params: Parameters<ModelRepository['searchReferenceArtifacts']>[0]) =>
      repo.searchReferenceArtifacts(params),
    listDiagrams: (params?: Parameters<ModelRepository['listDiagrams']>[0]) => repo.listDiagrams(params),
    listDiagramTypes: () => repo.listDiagramTypes(),
    getDiagramTypeUiConfig: (type: string) => repo.getDiagramTypeUiConfig(type),
    getDatatypeTypes: (params?: Parameters<ModelRepository['getDatatypeTypes']>[0]) =>
      repo.getDatatypeTypes(params),
    getDatatypeTypeUsages: (typeId: string) => repo.getDatatypeTypeUsages(typeId),
    allocateDiagramEntityId: (body: Parameters<ModelRepository['allocateDiagramEntityId']>[0]) =>
      repo.allocateDiagramEntityId(body),
    getDiagram: (id: string) => repo.getDiagram(id),
    getDiagramContext: (id: string) => repo.getDiagramContext(id),
    diagramImageUrl: (filename: string) => repo.diagramImageUrl(filename),
    getDiagramRefs: (sourceId: string, targetId: string) =>
      repo.getDiagramRefs(sourceId, targetId),
    addConnection: (body: Parameters<ModelRepository['addConnection']>[0]) =>
      repo.addConnection(body),
    editConnection: (id: string, body: Parameters<ModelRepository['editConnection']>[1]) =>
      repo.editConnection(id, body),
    previewRemoveConnection: (id: string) => repo.previewRemoveConnection(id),
    removeConnection: (id: string) => repo.removeConnection(id),
    manageConnectionAssociations: (
      id: string, body: Parameters<ModelRepository['manageConnectionAssociations']>[1],
    ) => repo.manageConnectionAssociations(id, body),
    getWriteHelp: () => repo.getWriteHelp(),
    getOntologyClassification: (sourceType: string) => repo.getOntologyClassification(sourceType),
    getOntologyPair: (sourceType: string, targetType: string) => repo.getOntologyPair(sourceType, targetType),
    getAuthoringGuidance: (params: Parameters<ModelRepository['getAuthoringGuidance']>[0]) =>
      repo.getAuthoringGuidance(params),
    createEntity: (body: Parameters<ModelRepository['createEntity']>[0]) => repo.createEntity(body),
    editEntity: (id: string, body: Parameters<ModelRepository['editEntity']>[1]) =>
      repo.editEntity(id, body),
    previewDeleteEntity: (id: string) => repo.previewDeleteEntity(id),
    deleteEntity: (id: string) => repo.deleteEntity(id),
    getEntitySchemata: (artifactType: string, specialization?: string) =>
      repo.getEntitySchemata(artifactType, specialization),
    getDiagramEntities: (diagramId: string) => repo.getDiagramEntities(diagramId),
    getDiagramConnections: (diagramId: string) => repo.getDiagramConnections(diagramId),
    getDiagramSvg: (diagramId: string) => repo.getDiagramSvg(diagramId),
    getEntityDisplayItem: (artifactId: string) => repo.getEntityDisplayItem(artifactId),
    searchEntityDisplay: (params: Parameters<ModelRepository['searchEntityDisplay']>[0]) =>
      repo.searchEntityDisplay(params),
    discoverDiagramEntities: (params: Parameters<ModelRepository['discoverDiagramEntities']>[0]) =>
      repo.discoverDiagramEntities(params),
    previewDiagram: (body: Parameters<ModelRepository['previewDiagram']>[0]) => repo.previewDiagram(body),
    createDiagram: (body: Parameters<ModelRepository['createDiagram']>[0]) => repo.createDiagram(body),
    editDiagram: (id: string, body: Parameters<ModelRepository['editDiagram']>[1]) =>
      repo.editDiagram(id, body),
    patchDiagramClassifierMetadata: (
      id: string, classifierId: string,
      body: Parameters<ModelRepository['patchDiagramClassifierMetadata']>[2],
    ) => repo.patchDiagramClassifierMetadata(id, classifierId, body),
    patchDiagramAttributeMetadata: (
      id: string, classifierId: string, attributeId: string,
      body: Parameters<ModelRepository['patchDiagramAttributeMetadata']>[3],
    ) => repo.patchDiagramAttributeMetadata(id, classifierId, attributeId, body),
    getViewpointProjection: (diagramId: string) => repo.getViewpointProjection(diagramId),
    listViewpointDefinitions: () => repo.listViewpointDefinitions(),
    getCriteriaCatalog: () => repo.getCriteriaCatalog(),
    executeViewpoint: (request: Parameters<ModelRepository['executeViewpoint']>[0]) => repo.executeViewpoint(request),
    executeViewpointProjection: (request: Parameters<ModelRepository['executeViewpointProjection']>[0]) =>
      repo.executeViewpointProjection(request),
    executeViewpointDiagram: (request: Parameters<ModelRepository['executeViewpointDiagram']>[0]) =>
      repo.executeViewpointDiagram(request),
    summarizeViewpointQuery: (query: unknown) => repo.summarizeViewpointQuery(query),
    exportViewpointCsv: (body: Parameters<ModelRepository['exportViewpointCsv']>[0]) =>
      repo.exportViewpointCsv(body),
    createViewpointDefinition: (body: Parameters<ModelRepository['createViewpointDefinition']>[0]) =>
      repo.createViewpointDefinition(body),
    replaceViewpointDefinition: (
      slug: string,
      body: Parameters<ModelRepository['replaceViewpointDefinition']>[1],
    ) => repo.replaceViewpointDefinition(slug, body),
    previewDeleteViewpointDefinition: (slug: string) => repo.previewDeleteViewpointDefinition(slug),
    deleteViewpointDefinition: (slug: string) => repo.deleteViewpointDefinition(slug),
    getViewpointReferencers: (slug: string) => repo.getViewpointReferencers(slug),
    getViewpointPins: () => repo.getViewpointPins(),
    setViewpointPins: (slugs: readonly string[]) => repo.setViewpointPins(slugs),
    previewDeleteDiagram: (id: string) => repo.previewDeleteDiagram(id),
    deleteDiagram: (id: string) => repo.deleteDiagram(id),
    syncDiagramToModel: (id: string, body: Parameters<ModelRepository['syncDiagramToModel']>[1]) =>
      repo.syncDiagramToModel(id, body),
    setEdgeLabel: (
      id: string, edgeKey: string, body: Parameters<ModelRepository['setEdgeLabel']>[2],
    ) => repo.setEdgeLabel(id, edgeKey, body),
    adminCreateEntity: (body: Parameters<ModelRepository['adminCreateEntity']>[0]) => repo.adminCreateEntity(body),
    adminEditEntity: (id: string, body: Parameters<ModelRepository['adminEditEntity']>[1]) =>
      repo.adminEditEntity(id, body),
    previewAdminDeleteEntity: (id: string) => repo.previewAdminDeleteEntity(id),
    adminDeleteEntity: (id: string) => repo.adminDeleteEntity(id),
    adminAddConnection: (body: Parameters<ModelRepository['adminAddConnection']>[0]) => repo.adminAddConnection(body),
    previewAdminRemoveConnection: (id: string) => repo.previewAdminRemoveConnection(id),
    adminRemoveConnection: (id: string) => repo.adminRemoveConnection(id),
    previewAdminDeleteDiagram: (id: string) => repo.previewAdminDeleteDiagram(id),
    adminDeleteDiagram: (id: string) => repo.adminDeleteDiagram(id),
    planPromotion: (body: Parameters<ModelRepository['planPromotion']>[0]) => repo.planPromotion(body),
    executePromotion: (body: Parameters<ModelRepository['executePromotion']>[0]) => repo.executePromotion(body),
    getSyncStatus: () => repo.getSyncStatus(),
    saveEngagementChanges: (body: Parameters<ModelRepository['saveEngagementChanges']>[0]) => repo.saveEngagementChanges(body),
    saveEnterpriseChanges: (body: Parameters<ModelRepository['saveEnterpriseChanges']>[0]) => repo.saveEnterpriseChanges(body),
    submitEnterpriseChanges: () => repo.submitEnterpriseChanges(),
    withdrawEnterpriseChanges: () => repo.withdrawEnterpriseChanges(),
    getChanges: (scope: Parameters<ModelRepository['getChanges']>[0]) => repo.getChanges(scope),
    getMatrixConfig: (id: string) => repo.getMatrixConfig(id),
    previewMatrix: (body: Parameters<ModelRepository['previewMatrix']>[0]) => repo.previewMatrix(body),
    createMatrixDiagram: (body: Parameters<ModelRepository['createMatrixDiagram']>[0]) => repo.createMatrixDiagram(body),
    editMatrixDiagram: (id: string, body: Parameters<ModelRepository['editMatrixDiagram']>[1]) =>
      repo.editMatrixDiagram(id, body),
    listGroups: (kind?: string) => repo.listGroups(kind),
    createGroup: (body: Parameters<ModelRepository['createGroup']>[0]) => repo.createGroup(body),
    renameGroup: (kind: string, slug: string, body: Parameters<ModelRepository['renameGroup']>[2]) =>
      repo.renameGroup(kind, slug, body),
    archiveGroup: (kind: string, slug: string, body: Parameters<ModelRepository['archiveGroup']>[2]) =>
      repo.archiveGroup(kind, slug, body),
    unarchiveGroup: (kind: string, slug: string) => repo.unarchiveGroup(kind, slug),
    deleteGroup: (kind: string, slug: string, confirm?: string) => repo.deleteGroup(kind, slug, confirm),
    updateGroup: (kind: string, slug: string, body: Parameters<ModelRepository['updateGroup']>[2]) =>
      repo.updateGroup(kind, slug, body),
    listScratchpads: (params?: Parameters<ModelRepository['listScratchpads']>[0]) =>
      repo.listScratchpads(params),
    getScratchpad: (id: string) => repo.getScratchpad(id),
    createScratchpad: (body: Parameters<ModelRepository['createScratchpad']>[0]) =>
      repo.createScratchpad(body),
    replaceScratchpad: (id: string, body: Parameters<ModelRepository['replaceScratchpad']>[1]) =>
      repo.replaceScratchpad(id, body),
    deleteScratchpad: (id: string) => repo.deleteScratchpad(id),
    liftScratchpad: (id: string, body: Parameters<ModelRepository['liftScratchpad']>[1]) =>
      repo.liftScratchpad(id, body),
  }) as const
