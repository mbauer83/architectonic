<script setup lang="ts">
import { inject, ref, computed, watch } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import type { useWizardSession, WizardSuggestion } from '../composables/useWizardSession'
import { useSuggestionCommit } from '../composables/useSuggestionCommit'
import type { AuthoringGuidance, EntityDisplayInfo } from '../../domain'
import WizardEntityForm from './WizardEntityForm.vue'
import WizardConnectionSuggestions from './WizardConnectionSuggestions.vue'
import { entityTypesForDomain } from './WizardDomainStage.helpers'
import {
  legalConnectionPairs, buildWizardSuggestions, buildChainSuggestions, type ChainAnchor,
} from '../lib/wizardSuggestions'
import { readErrorMessage } from '../lib/errors'

/**
 * One entity of `entityType` per pass, then ranked connection suggestions for it. There is no
 * create-vs-find mode: the form is a single search-as-you-type surface — typing the intended
 * name live-searches existing same-type entities, clicking a match reuses it ("Found"),
 * creating anyway is always one click. Fast users never engage with the matches; cautious
 * users get dedupe and anchor-on-existing for free.
 * Shared by the free-choice hub (`WizardDomainStage.vue`) and the guided questionnaire
 * (`WizardQuestionnaireStage.vue`) — the only difference between those two callers is what
 * happens on `done` (reset to type-choice vs. advance to the next question) and, for the
 * questionnaire, which prior entities count as graph-proximity anchors.
 */
const props = defineProps<{
  entityType: string
  domain: string
  guidance: AuthoringGuidance | null
  session: ReturnType<typeof useWizardSession>
  /** Entity ids from earlier in a guided sequence — biases suggestion ranking toward entities
   * already connected to them (the "spine" a questionnaire is building). */
  proximityAnchors?: string[]
  doneLabel?: string
  /** Example of a well-formed name, passed through to the create form's placeholder. */
  nameHint?: string
  /** Offer "+ Add another <type>" alongside the done action (questionnaire steps that may need
   * several entities of one type — N stakeholders, N affected processes). */
  allowAnother?: boolean
  /** Connection kinds the current step is about — ranked first in chain suggestions (e.g. the
   * subdivision step prefers aggregation over the globally higher-ranked triggering). */
  chainPreference?: string[]
}>()
/** `entity` is set when the user completed a create/find this step, null on plain cancel — a
 * guided sequence needs to tell "advance" from "abandon this question" apart. `another` records
 * the completed entity but stays on the step for one more of the same type. */
const emit = defineEmits<{
  done: [entity: { id: string; name: string } | null]
  another: [entity: { id: string; name: string }]
}>()

const svc = inject(modelServiceKey)!


interface ActiveEntity { id: string; name: string; type: string; wasCreated: boolean }
const activeEntity = ref<ActiveEntity | null>(null)
const suggestionsLoading = ref(false)
const suggestionsError = ref<string | null>(null)
const commitError = ref<string | null>(null)
const busy = ref(false)
const suggestionCommit = useSuggestionCommit(props.session)
const anyBusy = computed(() => busy.value || suggestionCommit.busy.value)
const anyError = computed(() => commitError.value ?? suggestionCommit.error.value)

const activeSuggestions = computed<WizardSuggestion[]>(() => {
  if (!activeEntity.value) return []
  const id = activeEntity.value.id
  return props.session.state.pendingSuggestions.filter((s) => s.sourceId === id || s.targetId === id)
})

const resetActiveEntity = () => {
  activeEntity.value = null
  commitError.value = null
}

const anotherEntity = () => {
  if (!activeEntity.value) return
  emit('another', activeEntity.value)
  resetActiveEntity()
}

async function proximityNeighborIds(entityId: string): Promise<Set<string>> {
  const anchors = [entityId, ...(props.proximityAnchors ?? [])]
  try {
    const discovery = await Effect.runPromise(svc.discoverDiagramEntities({ includedEntityIds: anchors, maxHops: 1 }))
    const ids = new Set<string>()
    for (const group of discovery.suggested_entities) for (const item of group.items) ids.add(item.artifact_id)
    return ids
  } catch {
    return new Set()
  }
}

/** Resolve the session's spine-anchor ids to (id, name, type) — anchors may be found entities,
 * not only wizard-created ones, so names/types come from the display-item lookup. Failures drop
 * the anchor silently: chain suggestions are a bonus, never a blocker. */
async function resolveChainAnchors(excludeId: string): Promise<ChainAnchor[]> {
  const ids = (props.proximityAnchors ?? []).filter((id) => id !== excludeId)
  const anchors: ChainAnchor[] = []
  for (const id of ids) {
    try {
      const item = await Effect.runPromise(svc.getEntityDisplayItem(id))
      anchors.push({ id: item.artifact_id, name: item.name, type: item.artifact_type })
    } catch { /* dropped */ }
  }
  return anchors
}

async function loadSuggestionsFor(entity: ActiveEntity) {
  const typeGuidance = entityTypesForDomain(props.guidance, props.domain).find((t) => t.name === entity.type)
    ?? props.guidance?.entity_types?.find((t) => t.name === entity.type)
  if (!typeGuidance) return
  suggestionsLoading.value = true
  suggestionsError.value = null
  try {
    const source = { id: entity.id, name: entity.name, domain: props.domain }
    const pairs = legalConnectionPairs(typeGuidance.permitted_connections)
    const anchors = await resolveChainAnchors(entity.id)

    // Chain first: the session's own spine outranks anything similarity-scored (WU-B4.2).
    const chain = buildChainSuggestions(source, pairs, anchors, 4, props.chainPreference ?? [])
    for (const suggestion of chain) props.session.queueSuggestion(suggestion)

    const targetTypes = [...new Set(pairs.map((p) => p.targetType))]
    const candidatesByTargetType = new Map<string, EntityDisplayInfo[]>()
    for (const targetType of targetTypes) {
      const result = await Effect.runPromise(
        svc.searchEntityDisplay({ query: '', limit: 20, entityTypes: [targetType] }),
      )
      candidatesByTargetType.set(targetType, result.items.filter((item) => item.artifact_id !== entity.id))
    }
    const proximity = await proximityNeighborIds(entity.id)
    // Anchors are full-strength proximity candidates too — the alphabetical 20-item search page
    // must never be able to drop the entity created a minute ago.
    for (const anchor of anchors) {
      proximity.add(anchor.id)
      const pool = candidatesByTargetType.get(anchor.type)
      if (pool && !pool.some((item) => item.artifact_id === anchor.id)) {
        try {
          pool.push(await Effect.runPromise(svc.getEntityDisplayItem(anchor.id)))
        } catch { /* dropped */ }
      }
    }
    const suggestions = buildWizardSuggestions(source, pairs, candidatesByTargetType, 5, proximity)
    for (const suggestion of suggestions) props.session.queueSuggestion(suggestion)
  } catch (error: unknown) {
    suggestionsError.value = readErrorMessage(error)
  } finally {
    suggestionsLoading.value = false
  }
}

const onEntityCreated = (result: { artifactId: string; name: string }) => {
  const entity: ActiveEntity = { id: result.artifactId, name: result.name, type: props.entityType, wasCreated: true }
  activeEntity.value = entity
  props.session.recordCreated({
    artifactId: entity.id, artifactType: entity.type, domain: props.domain, name: entity.name,
  })
  void loadSuggestionsFor(entity)
}

const onEntityFound = (entity: EntityDisplayInfo) => {
  const found: ActiveEntity = { id: entity.artifact_id, name: entity.name, type: entity.artifact_type, wasCreated: false }
  activeEntity.value = found
  void loadSuggestionsFor(found)
}

const undoActiveEntity = () => {
  if (!activeEntity.value?.wasCreated) return
  busy.value = true
  void Effect.runPromise(svc.deleteEntity(activeEntity.value.id))
    .then(() => {
      if (activeEntity.value) props.session.undoCreated(activeEntity.value.id)
      activeEntity.value = null
      busy.value = false
    })
    .catch((error: unknown) => {
      commitError.value = readErrorMessage(error)
      busy.value = false
    })
}

const acceptSuggestion = (suggestion: WizardSuggestion) =>
  suggestionCommit.accept(suggestion, (id) => props.session.dismissSuggestion(id))

const dismissSuggestion = (id: string) => props.session.dismissSuggestion(id)
const laterSuggestion = (id: string) => props.session.deferToReviewLater(id)

watch(() => props.entityType, resetActiveEntity)
defineExpose({ resetActiveEntity })
</script>

<template>
  <div class="entity-stage">
    <WizardEntityForm
      v-if="!activeEntity"
      :entity-type="entityType"
      :name-placeholder="nameHint"
      @created="onEntityCreated"
      @cancel="emit('done', null)"
      @use-existing="onEntityFound"
    />

    <div
      v-if="activeEntity"
      class="active-entity"
    >
      <p class="active-entity-label">
        {{ activeEntity.wasCreated ? 'Created' : 'Found' }}: <strong>{{ activeEntity.name }}</strong>
        <button
          v-if="activeEntity.wasCreated"
          type="button"
          class="btn-link btn-link--danger"
          :disabled="anyBusy"
          @click="undoActiveEntity"
        >
          Undo
        </button>
      </p>

      <div
        v-if="anyError"
        class="state-msg state-msg--error"
      >
        {{ anyError }}
      </div>

      <h3 class="suggestions-title">
        Connections
      </h3>
      <p
        v-if="suggestionsLoading"
        class="state-msg"
      >
        Looking for likely connections…
      </p>
      <p
        v-else-if="suggestionsError"
        class="state-msg state-msg--error"
      >
        {{ suggestionsError }}
      </p>
      <WizardConnectionSuggestions
        v-else
        :suggestions="activeSuggestions"
        :busy="anyBusy"
        :guidance="guidance"
        @accept="acceptSuggestion"
        @dismiss="dismissSuggestion"
        @later="laterSuggestion"
      />

      <div class="stage-actions">
        <button
          v-if="allowAnother"
          type="button"
          class="btn-link"
          @click="anotherEntity"
        >
          + Add another {{ entityType }}
        </button>
        <button
          type="button"
          class="btn-link"
          @click="emit('done', activeEntity)"
        >
          {{ doneLabel ?? 'Done' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.entity-stage { display: flex; flex-direction: column; gap: 14px; }
.active-entity { display: flex; flex-direction: column; gap: 10px; border-top: 1px solid #f3f4f6; padding-top: 12px; }
.active-entity-label { font-size: 13px; color: #374151; }
.suggestions-title { font-size: 13px; font-weight: 600; margin: 0; color: #374151; }
.btn-link { align-self: flex-start; background: none; border: none; color: #2563eb; cursor: pointer; padding: 0; font-size: 12px; text-decoration: underline; }
.btn-link--danger { color: #dc2626; margin-left: 8px; }
.stage-actions { display: flex; gap: 16px; }
.state-msg { font-size: 12px; color: #6b7280; }
.state-msg--error { color: #dc2626; }
</style>
