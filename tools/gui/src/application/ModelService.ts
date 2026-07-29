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
    search: (query: string, limit?: number) => repo.search(query, limit),
    listDocumentTypes: () => repo.listDocumentTypes(),
    listDocuments: (params?: Parameters<ModelRepository['listDocuments']>[0]) => repo.listDocuments(params),
    getDocument: (id: string) => repo.getDocument(id),
    createDocument: (body: Parameters<ModelRepository['createDocument']>[0]) => repo.createDocument(body),
    editDocument: (id: string, body: Parameters<ModelRepository['editDocument']>[1]) => repo.editDocument(id, body),
    deleteDocument: (id: string, dryRun?: boolean) => repo.deleteDocument(id, dryRun),
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
    editConnection: (body: Parameters<ModelRepository['editConnection']>[0]) =>
      repo.editConnection(body),
    removeConnection: (body: Parameters<ModelRepository['removeConnection']>[0]) =>
      repo.removeConnection(body),
    manageConnectionAssociations: (body: Parameters<ModelRepository['manageConnectionAssociations']>[0]) =>
      repo.manageConnectionAssociations(body),
    getWriteHelp: () => repo.getWriteHelp(),
    getOntologyClassification: (sourceType: string) => repo.getOntologyClassification(sourceType),
    getOntologyPair: (sourceType: string, targetType: string) => repo.getOntologyPair(sourceType, targetType),
    getAuthoringGuidance: (params: Parameters<ModelRepository['getAuthoringGuidance']>[0]) =>
      repo.getAuthoringGuidance(params),
    createEntity: (body: Parameters<ModelRepository['createEntity']>[0]) => repo.createEntity(body),
    editEntity: (body: Parameters<ModelRepository['editEntity']>[0]) => repo.editEntity(body),
    deleteEntity: (body: Parameters<ModelRepository['deleteEntity']>[0]) => repo.deleteEntity(body),
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
    editDiagram: (body: Parameters<ModelRepository['editDiagram']>[0]) => repo.editDiagram(body),
    patchDiagramEntityMetadata: (body: Parameters<ModelRepository['patchDiagramEntityMetadata']>[0]) =>
      repo.patchDiagramEntityMetadata(body),
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
    editViewpointDefinition: (body: Parameters<ModelRepository['editViewpointDefinition']>[0]) =>
      repo.editViewpointDefinition(body),
    deleteViewpointDefinition: (body: Parameters<ModelRepository['deleteViewpointDefinition']>[0]) =>
      repo.deleteViewpointDefinition(body),
    getViewpointReferencers: (slug: string) => repo.getViewpointReferencers(slug),
    getViewpointPins: () => repo.getViewpointPins(),
    setViewpointPins: (slugs: readonly string[]) => repo.setViewpointPins(slugs),
    deleteDiagram: (body: Parameters<ModelRepository['deleteDiagram']>[0]) => repo.deleteDiagram(body),
    syncDiagramToModel: (body: Parameters<ModelRepository['syncDiagramToModel']>[0]) => repo.syncDiagramToModel(body),
    setEdgeLabel: (body: Parameters<ModelRepository['setEdgeLabel']>[0]) => repo.setEdgeLabel(body),
    adminCreateEntity: (body: Parameters<ModelRepository['adminCreateEntity']>[0]) => repo.adminCreateEntity(body),
    adminEditEntity: (body: Parameters<ModelRepository['adminEditEntity']>[0]) => repo.adminEditEntity(body),
    adminDeleteEntity: (body: Parameters<ModelRepository['adminDeleteEntity']>[0]) => repo.adminDeleteEntity(body),
    adminAddConnection: (body: Parameters<ModelRepository['adminAddConnection']>[0]) => repo.adminAddConnection(body),
    adminRemoveConnection: (body: Parameters<ModelRepository['adminRemoveConnection']>[0]) => repo.adminRemoveConnection(body),
    adminDeleteDiagram: (body: Parameters<ModelRepository['adminDeleteDiagram']>[0]) => repo.adminDeleteDiagram(body),
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
    editMatrixDiagram: (body: Parameters<ModelRepository['editMatrixDiagram']>[0]) => repo.editMatrixDiagram(body),
    listGroups: (kind?: string) => repo.listGroups(kind),
    createGroup: (body: Parameters<ModelRepository['createGroup']>[0]) => repo.createGroup(body),
    renameGroup: (body: Parameters<ModelRepository['renameGroup']>[0]) => repo.renameGroup(body),
    archiveGroup: (body: Parameters<ModelRepository['archiveGroup']>[0]) => repo.archiveGroup(body),
    unarchiveGroup: (body: Parameters<ModelRepository['unarchiveGroup']>[0]) => repo.unarchiveGroup(body),
    deleteGroup: (params: Parameters<ModelRepository['deleteGroup']>[0]) => repo.deleteGroup(params),
    updateGroup: (body: Parameters<ModelRepository['updateGroup']>[0]) => repo.updateGroup(body),
  }) as const
