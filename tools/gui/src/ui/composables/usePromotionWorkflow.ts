import { computed, ref, watch, type Ref } from 'vue'
import { Effect, Exit } from 'effect'
import type { EntityContextConnection, EntityDisplayInfo, PromotionGroupMappingEntry, PromotionPlan, PromotionResult, StructuralClosureRequirement } from '../../domain'
import type { RepoError } from '../../ports/ModelRepository'
import type { ModelService } from '../../application/ModelService'
import { useMutation } from './useMutation'
import { useQuery } from './useQuery'
import { formatArtifactFallbackName, loadPromotionDiagram, loadPromotionDocument, loadPromotionEntity, searchPromotionArtifacts, toggledSet, type ConflictStrategy, type PromotionArtifact, type PromotionArtifactKind, type Step } from './promotionShared'
import { usePromotionSearch } from './usePromotionSearch'

export const usePromotionWorkflow = (
  svc: ModelService,
  routeQuery: Ref<Record<string, unknown>>,
) => {
  const step = ref<Step>('pick')
  const selectedRoot = ref<PromotionArtifact | null>(null)

  const includedEntities = ref<EntityDisplayInfo[]>([])
  const includedDocuments = ref<PromotionArtifact[]>([])
  const includedDiagrams = ref<PromotionArtifact[]>([])
  const newInclusionIds = ref<Set<string>>(new Set())
  const allModelConns = ref<Map<string, EntityContextConnection>>(new Map())
  const includedConnIds = ref<Set<string>>(new Set())
  const expandedConnectionEntityIds = ref<Set<string>>(new Set())
  const expandedRelatedEntityIds = ref<Set<string>>(new Set())

  const rootSearch = usePromotionSearch((query) => searchPromotionArtifacts(svc, query, new Set()))
  const addSearch = usePromotionSearch((query) => searchPromotionArtifacts(svc, query, selectedArtifactIds.value))

  const planQuery = useQuery<PromotionPlan, RepoError>()
  const executeMutation = useMutation<PromotionResult, RepoError>()
  const conflictStrategies = ref<Record<string, ConflictStrategy>>({})
  const groupMappingResolutions = ref<Record<string, string>>({})

  const includedEntityIds = computed(() => new Set(includedEntities.value.map((entity) => entity.artifact_id)))
  const selectedArtifactIds = computed(() => new Set([
    ...includedEntities.value.map((entity) => entity.artifact_id), ...includedDocuments.value.map((document) => document.artifact_id), ...includedDiagrams.value.map((diagram) => diagram.artifact_id),
  ]))

  watch(() => planQuery.data.value, (newPlan) => {
    if (!newPlan) return
    const nextStrategies: Record<string, ConflictStrategy> = {}
    for (const conflict of newPlan.conflicts) {
      nextStrategies[conflict.engagement_id] = conflictStrategies.value[conflict.engagement_id] ?? 'accept_enterprise'
    }
    for (const conflict of newPlan.doc_conflicts) {
      nextStrategies[conflict.engagement_id] = conflictStrategies.value[conflict.engagement_id] ?? 'accept_enterprise'
    }
    for (const conflict of newPlan.diagram_conflicts) {
      nextStrategies[conflict.engagement_id] = conflictStrategies.value[conflict.engagement_id] ?? 'accept_enterprise'
    }
    conflictStrategies.value = nextStrategies

    // Auto-initialize group mapping resolutions from the plan
    const nextGroupMapping: Record<string, string> = {}
    for (const entry of (newPlan.group_mapping ?? [])) {
      // matched_by_id and new: use default enterprise_slug; conflict: preserve any existing choice
      nextGroupMapping[entry.engagement_slug] =
        groupMappingResolutions.value[entry.engagement_slug] ?? entry.enterprise_slug
    }
    groupMappingResolutions.value = nextGroupMapping
  })

  const executeError = computed(() => {
    const result = executeMutation.result.value
    if (result && !result.executed) return result.verification_errors.join('\n') || 'Execution failed'
    return executeMutation.errorMessage.value
  })

  const selectionRows = computed(() =>
    includedEntities.value.map((entity) => ({
      entity,
      newInclusion: newInclusionIds.value.has(entity.artifact_id),
      badgeText: newInclusionIds.value.has(entity.artifact_id) ? 'new' : undefined,
      actionKind: 'remove' as const,
      actionTitle: 'Remove entity from promotion set',
    })),
  )

  const relatedEntitiesById = computed<Record<string, EntityDisplayInfo[]>>(() => {
    const related: Record<string, EntityDisplayInfo[]> = {}
    const seenByEntity = new Map<string, Set<string>>()
    for (const entity of includedEntities.value) related[entity.artifact_id] = []
    for (const conn of allModelConns.value.values()) {
      const endpoints: Array<[string, string]> = [[conn.source, conn.target], [conn.target, conn.source]]
      for (const [ownerId, otherId] of endpoints) {
        if (!includedEntityIds.value.has(ownerId) || includedEntityIds.value.has(otherId)) continue
        const seen = seenByEntity.get(ownerId) ?? new Set<string>()
        if (seen.has(otherId)) continue
        seen.add(otherId)
        seenByEntity.set(ownerId, seen)
        const isSource = ownerId === conn.source
        related[ownerId].push({
          artifact_id: otherId,
          name: isSource ? (conn.target_name ?? otherId) : (conn.source_name ?? otherId),
          artifact_type: (isSource ? conn.target_artifact_type : conn.source_artifact_type),
          domain: (isSource ? conn.target_domain : conn.source_domain),
          subdomain: '',
          status: isSource ? conn.target_scope : conn.source_scope,
          display_alias: '',
          element_type: isSource ? conn.target_artifact_type : conn.source_artifact_type,
          element_label: isSource ? (conn.target_name ?? otherId) : (conn.source_name ?? otherId), diagram_internal: false,
        })
      }
    }
    for (const entityId of Object.keys(related)) related[entityId].sort((left, right) => left.name.localeCompare(right.name))
    return related
  })

  const unresolvedConflicts = computed(() => {
    const plan = planQuery.data.value
    if (!plan) return []
    return [
      ...plan.conflicts.map((conflict) => conflict.engagement_id),
      ...plan.doc_conflicts.map((conflict) => conflict.engagement_id),
      ...plan.diagram_conflicts.map((conflict) => conflict.engagement_id),
    ].filter((artifactId) => !conflictStrategies.value[artifactId])
  })
  const unresolvedGroupConflicts = computed<PromotionGroupMappingEntry[]>(() => {
    const plan = planQuery.data.value
    if (!plan) return []
    return (plan.group_mapping ?? []).filter(
      (entry) => entry.match_status === 'conflict' && !groupMappingResolutions.value[entry.engagement_slug],
    )
  })
  const totalSelectedArtifacts = computed(() => includedEntities.value.length + includedDocuments.value.length + includedDiagrams.value.length)
  const structuralClosure = computed(() => planQuery.data.value?.structural_closure ?? [])
  const canExecute = computed(
    () => totalSelectedArtifacts.value > 0
      && unresolvedConflicts.value.length === 0
      && unresolvedGroupConflicts.value.length === 0
      && structuralClosure.value.length === 0,
  )
  const promotionTargetCount = computed(() => {
    const plan = planQuery.data.value
    if (!plan) return 0
    return plan.entities_to_add.length + plan.conflicts.length + plan.documents_to_add.length
      + plan.doc_conflicts.length + plan.diagrams_to_add.length + plan.diagram_conflicts.length
  })

  const refreshEntityDiscovery = async () => {
    if (!includedEntities.value.length) {
      allModelConns.value = new Map()
      return
    }
    const exit = await Effect.runPromiseExit(
      svc.discoverDiagramEntities({
        includedEntityIds: includedEntities.value.map((entity) => entity.artifact_id),
        maxHops: 1,
        limit: 20,
      }),
    )
    Exit.match(exit, {
      onSuccess: (discovery) => {
        allModelConns.value = new Map(discovery.candidate_connections.map((conn) => [conn.artifact_id, conn]))
      },
      onFailure: () => {},
    })
  }

  const refreshPlan = () => {
    if (!totalSelectedArtifacts.value) {
      planQuery.reset()
      conflictStrategies.value = {}
      return
    }
    planQuery.run(svc.planPromotion({
      entity_id: selectedRoot.value?.record_type === 'entity' ? selectedRoot.value.artifact_id : undefined,
      entity_ids: includedEntities.value.map((entity) => entity.artifact_id),
      connection_ids: [...includedConnIds.value],
      document_ids: includedDocuments.value.map((document) => document.artifact_id),
      diagram_ids: includedDiagrams.value.map((diagram) => diagram.artifact_id),
    }))
  }

  const includeEntity = async (artifactId: string, markNew: boolean) => {
    if (includedEntityIds.value.has(artifactId)) return
    const entity = await loadPromotionEntity(svc, artifactId)
    if (!entity) return
    includedEntities.value.push(entity)
    if (markNew) newInclusionIds.value = new Set(newInclusionIds.value).add(artifactId)
    await refreshEntityDiscovery()
    const nextConnIds = new Set(includedConnIds.value)
    for (const conn of allModelConns.value.values()) {
      const otherId = conn.source === artifactId ? conn.target : conn.source
      if ((conn.source === artifactId || conn.target === artifactId) && includedEntityIds.value.has(otherId)) {
        nextConnIds.add(conn.artifact_id)
      }
    }
    includedConnIds.value = nextConnIds
  }
  const includeDocument = async (artifactId: string, fallbackName: string, markNew: boolean) => {
    if (includedDocuments.value.some((document) => document.artifact_id === artifactId)) return
    includedDocuments.value.push(await loadPromotionDocument(svc, artifactId, fallbackName))
    if (markNew) newInclusionIds.value = new Set(newInclusionIds.value).add(artifactId)
  }

  const includeDiagram = async (artifactId: string, fallbackName: string, markNew: boolean) => {
    if (includedDiagrams.value.some((diagram) => diagram.artifact_id === artifactId)) return
    includedDiagrams.value.push(await loadPromotionDiagram(svc, artifactId, fallbackName))
    if (markNew) newInclusionIds.value = new Set(newInclusionIds.value).add(artifactId)
  }

  const addArtifact = async (artifact: PromotionArtifact, markNew = true) => {
    if (artifact.record_type === 'entity') await includeEntity(artifact.artifact_id, markNew)
    if (artifact.record_type === 'document') await includeDocument(artifact.artifact_id, artifact.name, markNew)
    if (artifact.record_type === 'diagram') await includeDiagram(artifact.artifact_id, artifact.name, markNew)
    addSearch.clear()
    refreshPlan()
  }

  /** One-action closure fix: include a blocked junction/grouping's missing
   * meaning-carrying entities, then re-plan — the block clears once complete. */
  const includeClosureEntities = async (requirement: StructuralClosureRequirement) => {
    for (const entity of requirement.missing) await includeEntity(entity.artifact_id, true)
    refreshPlan()
  }

  const selectRoot = (artifact: PromotionArtifact) => {
    selectedRoot.value = artifact
    rootSearch.query.value = artifact.name
    rootSearch.results.value = []
    rootSearch.showDropdown.value = false
  }

  const removeEntity = async (artifactId: string) => {
    includedEntities.value = includedEntities.value.filter((entity) => entity.artifact_id !== artifactId)
    newInclusionIds.value = new Set([...newInclusionIds.value].filter((id) => id !== artifactId))
    expandedConnectionEntityIds.value = new Set([...expandedConnectionEntityIds.value].filter((id) => id !== artifactId))
    expandedRelatedEntityIds.value = new Set([...expandedRelatedEntityIds.value].filter((id) => id !== artifactId))
    includedConnIds.value = new Set([...includedConnIds.value].filter((id) => {
      const conn = allModelConns.value.get(id)
      return !(conn && (conn.source === artifactId || conn.target === artifactId))
    }))
    await refreshEntityDiscovery()
    refreshPlan()
  }
  const removeArtifact = (kind: Exclude<PromotionArtifactKind, 'entity'>, artifactId: string) => {
    if (kind === 'document') includedDocuments.value = includedDocuments.value.filter((document) => document.artifact_id !== artifactId)
    if (kind === 'diagram') includedDiagrams.value = includedDiagrams.value.filter((diagram) => diagram.artifact_id !== artifactId)
    newInclusionIds.value = new Set([...newInclusionIds.value].filter((id) => id !== artifactId))
    refreshPlan()
  }

  const execute = () => {
    if (!canExecute.value) return
    step.value = 'execute'
    const conflictResolutions = Object.entries(conflictStrategies.value).map(([engagement_id, strategy]) => ({ engagement_id, strategy }))
    const run = async () => {
      const exit = await executeMutation.run(svc.executePromotion({
        entity_id: selectedRoot.value?.record_type === 'entity' ? selectedRoot.value.artifact_id : undefined,
        entity_ids: includedEntities.value.map((entity) => entity.artifact_id),
        connection_ids: [...includedConnIds.value],
        document_ids: includedDocuments.value.map((document) => document.artifact_id),
        diagram_ids: includedDiagrams.value.map((diagram) => diagram.artifact_id),
        conflict_resolutions: conflictResolutions,
        group_mapping_resolutions: { ...groupMappingResolutions.value },
        dry_run: false,
      }))
      Exit.match(exit, {
        onSuccess: (result) => { step.value = result.executed ? 'done' : 'review' },
        onFailure: () => { step.value = 'review' },
      })
    }
    void run()
  }

  const setConflictStrategy = (artifactId: string, strategy: ConflictStrategy) => {
    conflictStrategies.value = { ...conflictStrategies.value, [artifactId]: strategy }
  }

  const setGroupMapping = (engagementSlug: string, enterpriseSlug: string) => {
    groupMappingResolutions.value = { ...groupMappingResolutions.value, [engagementSlug]: enterpriseSlug }
  }

  const startPromotion = async () => {
    if (!selectedRoot.value) return
    includedEntities.value = []
    includedDocuments.value = []
    includedDiagrams.value = []
    newInclusionIds.value = new Set()
    allModelConns.value = new Map()
    includedConnIds.value = new Set()
    expandedConnectionEntityIds.value = new Set()
    expandedRelatedEntityIds.value = new Set()
    executeMutation.reset()
    await addArtifact(selectedRoot.value, false)
    step.value = 'review'
  }

  const initializeFromRoute = async () => {
    const entityId = routeQuery.value.entity_id as string | undefined
    const documentId = routeQuery.value.document_id as string | undefined
    const diagramId = routeQuery.value.diagram_id as string | undefined
    const artifactId = entityId ?? documentId ?? diagramId
    if (!artifactId) return
    selectedRoot.value = { artifact_id: artifactId, name: formatArtifactFallbackName(artifactId), record_type: entityId ? 'entity' : (documentId ? 'document' : 'diagram'), status: '' }
    await startPromotion()
  }

  const cleanup = () => { rootSearch.cleanup(); addSearch.cleanup() }

  return {
    step,
    selectedRoot,
    includedEntities,
    includedDocuments,
    includedDiagrams,
    allModelConns,
    includedConnIds,
    expandedConnectionEntityIds,
    expandedRelatedEntityIds,
    rootQuery: rootSearch.query,
    rootResults: rootSearch.results,
    showRootDropdown: rootSearch.showDropdown,
    addQuery: addSearch.query,
    addResults: addSearch.results,
    showAddDropdown: addSearch.showDropdown,
    planQuery,
    executeMutation,
    conflictStrategies,
    includedEntityIds,
    selectionRows,
    relatedEntitiesById,
    unresolvedConflicts,
    totalSelectedArtifacts,
    canExecute,
    promotionTargetCount,
    executeError,
    scheduleRootSearch: rootSearch.scheduleSearch,
    scheduleAddSearch: addSearch.scheduleSearch,
    closeRootDropdown: rootSearch.closeDropdown,
    closeAddDropdown: addSearch.closeDropdown,
    toggleConnections: (entityId: string) => {
      expandedConnectionEntityIds.value = toggledSet(expandedConnectionEntityIds.value, entityId)
    },
    toggleRelated: (entityId: string) => {
      expandedRelatedEntityIds.value = toggledSet(expandedRelatedEntityIds.value, entityId)
    },
    toggleConnection: (artifactId: string) => {
      includedConnIds.value = toggledSet(includedConnIds.value, artifactId)
      refreshPlan()
    },
    groupMappingResolutions,
    unresolvedGroupConflicts,
    setGroupMapping,
    setConflictStrategy,
    structuralClosure,
    includeClosureEntities,
    selectRoot,
    addArtifact,
    removeEntity,
    removeArtifact,
    startPromotion,
    execute,
    restart: () => {
      step.value = 'pick'
      selectedRoot.value = null
      includedEntities.value = []
      includedDocuments.value = []
      includedDiagrams.value = []
      newInclusionIds.value = new Set()
      allModelConns.value = new Map()
      includedConnIds.value = new Set()
      expandedConnectionEntityIds.value = new Set()
      expandedRelatedEntityIds.value = new Set()
      rootSearch.clear()
      addSearch.clear()
      planQuery.reset()
      executeMutation.reset()
      conflictStrategies.value = {}
      groupMappingResolutions.value = {}
    },
    initializeFromRoute,
    cleanup,
  }
}
