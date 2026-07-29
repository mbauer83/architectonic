import { reactive, watch } from 'vue'

export interface WizardCreatedEntity {
  readonly artifactId: string
  readonly artifactType: string
  readonly domain: string
  readonly name: string
}

export interface WizardCreatedConnection {
  readonly sourceId: string
  readonly connectionType: string
  readonly targetId: string
  readonly summary: string
}

/**
 * A ranked, commit-ready connection suggestion: enough to render a one-line sentence
 * ("*X* probably **realizes** *Y*") and, on accept, call `addConnection` directly without
 * re-resolving anything.
 */
export interface WizardSuggestion {
  readonly id: string
  readonly domain: string
  readonly summary: string
  readonly sourceId: string
  readonly sourceName: string
  readonly connectionType: string
  readonly targetId: string
  readonly targetName: string
}

export interface WizardSessionState {
  activeDomain: string | null
  createdEntities: WizardCreatedEntity[]
  createdConnections: WizardCreatedConnection[]
  pendingSuggestions: WizardSuggestion[]
  reviewLaterQueue: WizardSuggestion[]
  /** Entity ids (created *or* found) completed as questionnaire steps, across all domains —
   * the cross-domain spine. Later domains' suggestion ranking biases toward graph neighbors
   * of these, so a business questionnaire ranks candidates near the motivation chain. */
  spineAnchorIds: string[]
}

export interface WizardStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

// v2: added createdConnections + commit-ready suggestion fields (sourceId/connectionType/
// targetId/etc.) — a v1 session would render suggestions with no way to commit them, so the
// key bumps rather than silently coexisting with the old shape.
export const WIZARD_SESSION_STORAGE_KEY = 'arch.model-wizard.session.v2'

export const initialWizardSessionState = (): WizardSessionState => ({
  activeDomain: null,
  createdEntities: [],
  createdConnections: [],
  pendingSuggestions: [],
  reviewLaterQueue: [],
  spineAnchorIds: [],
})

export const parseWizardSessionState = (raw: string | null): WizardSessionState => {
  if (!raw) return initialWizardSessionState()
  try {
    const parsed = JSON.parse(raw) as Partial<WizardSessionState>
    return {
      activeDomain: typeof parsed.activeDomain === 'string' ? parsed.activeDomain : null,
      createdEntities: Array.isArray(parsed.createdEntities) ? parsed.createdEntities : [],
      createdConnections: Array.isArray(parsed.createdConnections) ? parsed.createdConnections : [],
      pendingSuggestions: Array.isArray(parsed.pendingSuggestions) ? parsed.pendingSuggestions : [],
      reviewLaterQueue: Array.isArray(parsed.reviewLaterQueue) ? parsed.reviewLaterQueue : [],
      spineAnchorIds: Array.isArray(parsed.spineAnchorIds) ? parsed.spineAnchorIds : [],
    }
  } catch {
    return initialWizardSessionState()
  }
}

export const createdCountByDomain = (state: WizardSessionState): Record<string, number> => {
  const counts: Record<string, number> = {}
  for (const entity of state.createdEntities) counts[entity.domain] = (counts[entity.domain] ?? 0) + 1
  return counts
}

/**
 * Reactive wizard draft store (created ids, pending suggestions, review-later queue),
 * persisted to `storage` so a reload resumes the same in-progress session.
 */
export const useWizardSession = (storage: WizardStorage = window.sessionStorage) => {
  const state = reactive<WizardSessionState>(parseWizardSessionState(storage.getItem(WIZARD_SESSION_STORAGE_KEY)))

  watch(
    state,
    (next) => storage.setItem(WIZARD_SESSION_STORAGE_KEY, JSON.stringify(next)),
    { deep: true, flush: 'sync' },
  )

  const setActiveDomain = (domain: string | null) => { state.activeDomain = domain }

  const recordCreated = (entity: WizardCreatedEntity) => {
    if (state.createdEntities.some((e) => e.artifactId === entity.artifactId)) return
    state.createdEntities.push(entity)
  }

  const undoCreated = (artifactId: string) => {
    state.createdEntities = state.createdEntities.filter((e) => e.artifactId !== artifactId)
    state.spineAnchorIds = state.spineAnchorIds.filter((id) => id !== artifactId)
  }

  const recordSpineAnchor = (artifactId: string) => {
    if (state.spineAnchorIds.includes(artifactId)) return
    state.spineAnchorIds.push(artifactId)
  }

  const recordConnectionCreated = (connection: WizardCreatedConnection) => {
    const exists = state.createdConnections.some((c) =>
      c.sourceId === connection.sourceId
      && c.connectionType === connection.connectionType
      && c.targetId === connection.targetId)
    if (exists) return
    state.createdConnections.push(connection)
  }

  const undoConnectionCreated = (sourceId: string, connectionType: string, targetId: string) => {
    state.createdConnections = state.createdConnections.filter((c) =>
      !(c.sourceId === sourceId && c.connectionType === connectionType && c.targetId === targetId))
  }

  const queueSuggestion = (suggestion: WizardSuggestion) => {
    if (state.pendingSuggestions.some((s) => s.id === suggestion.id)) return
    state.pendingSuggestions.push(suggestion)
  }

  const dismissSuggestion = (id: string) => {
    state.pendingSuggestions = state.pendingSuggestions.filter((s) => s.id !== id)
  }

  const deferToReviewLater = (id: string) => {
    const suggestion = state.pendingSuggestions.find((s) => s.id === id)
    if (!suggestion) return
    state.pendingSuggestions = state.pendingSuggestions.filter((s) => s.id !== id)
    if (!state.reviewLaterQueue.some((s) => s.id === id)) state.reviewLaterQueue.push(suggestion)
  }

  const resolveReviewLater = (id: string) => {
    state.reviewLaterQueue = state.reviewLaterQueue.filter((s) => s.id !== id)
  }

  const reset = () => {
    Object.assign(state, initialWizardSessionState())
    storage.removeItem(WIZARD_SESSION_STORAGE_KEY)
  }

  return {
    state,
    setActiveDomain,
    recordCreated,
    undoCreated,
    recordSpineAnchor,
    recordConnectionCreated,
    undoConnectionCreated,
    queueSuggestion,
    dismissSuggestion,
    deferToReviewLater,
    resolveReviewLater,
    reset,
  }
}
