<script setup lang="ts">
/**
 * "Query" tab of the viewpoint definition editor: entity criteria, neighbor inclusions,
 * connections displayed, a debounced live-preview count, and a full test-run (real
 * counts/warnings + a dry-run save-mode validation pass) before the user attempts to save.
 * Owns all of that state locally — it's only ever rendered/consumed here. `draft` is
 * read-only (query edits are emitted as `update:query` patches for the parent to apply to
 * its own draft ref — never mutate a prop, `vue/no-mutating-props`); `issues` is likewise
 * emitted up so the parent's shared issue-list/highlight-on-click stays in sync with both a
 * test-run and a real save attempt.
 */
import { computed, inject, ref, watch } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import { readErrorMessage } from '../lib/errors'
import type { CriteriaCatalog, ViewpointExecutionResult, ViewpointValidationIssue } from '../../domain'
import type { ViewpointDefinitionDraft } from '../../domain/viewpointDefinitionDraft'
import { definitionToMapping } from '../../domain/viewpointDefinitionSerialization'
import { queryToMapping } from '../../domain/viewpointCriteriaSerialization'
import type { ExecutableQueryNode } from '../../domain/viewpointCriteria'
import { attributeTypeTablesFromCatalog } from '../../domain/viewpointBindings'
import { HIGHLIGHTED_NODE_ID_KEY } from './CriteriaTreeBuilder.helpers'
import { createDebouncer } from '../lib/debounce'
import { firstErrorNodeId, formatPreviewCounts } from '../views/ViewpointsManagementView.helpers'
import CriteriaTreeBuilder from './CriteriaTreeBuilder.vue'
import NeighborInclusionEditor from './NeighborInclusionEditor.vue'
import TestRunMatchedEntities from './TestRunMatchedEntities.vue'
import QueryBindingsPanel from './QueryBindingsPanel.vue'
import QueryParametersPanel from './QueryParametersPanel.vue'
import QueryDerivedAttributesPanel from './QueryDerivedAttributesPanel.vue'
import ViewpointTracePatternEditor from './ViewpointTracePatternEditor.vue'

const props = defineProps<{
  draft: ViewpointDefinitionDraft
  catalog: CriteriaCatalog
  isCreating: boolean
  /** Read-only master (module/enterprise tier) open in the editor — a Test run is not a
   * write attempt, so persistence-blocking issues must not surface as error banners. */
  isReadOnly?: boolean
}>()
const emit = defineEmits<{
  'update:query': [value: ExecutableQueryNode]
  issues: [issues: readonly ViewpointValidationIssue[]]
}>()

const svc = inject(modelServiceKey)!
const highlightedNodeId = inject(HIGHLIGHTED_NODE_ID_KEY)!

const summary = ref('')
const previewResult = ref<ViewpointExecutionResult | null>(null)
const testRunResult = ref<ViewpointExecutionResult | null>(null)
const testRunning = ref(false)
const testRunError = ref<string | null>(null)

const emitQueryUpdate = (patch: Partial<ExecutableQueryNode>) => {
  if (!props.draft.query) return
  emit('update:query', { ...props.draft.query, ...patch })
}

const attributeTypes = computed(() => attributeTypeTablesFromCatalog(props.catalog))
const bindingNames = computed(() => props.draft.query?.bindings.filter((b) => b.name.length > 0).map((b) => b.name) ?? [])
const parameterNames = computed(() => props.draft.query?.parameters.filter((p) => p.name.length > 0).map((p) => p.name) ?? [])

let summaryTimer: ReturnType<typeof setTimeout> | undefined
watch(() => props.draft.query, (query) => {
  if (summaryTimer) clearTimeout(summaryTimer)
  if (!query) { summary.value = ''; return }
  summaryTimer = setTimeout(() => {
    Effect.runPromise(svc.summarizeViewpointQuery(queryToMapping(query, attributeTypes.value))).then((s) => { summary.value = s }).catch(() => {})
  }, 250)
}, { deep: true, immediate: true })

/** Debounced live-preview counts: a `limit: 0` execution of the
 * draft's ad-hoc query — cheap enough (no entity/connection records fetched) to run on
 * every settled keystroke while building criteria. */
const debouncePreview = createDebouncer(400)
watch(() => props.draft.query, (query) => {
  if (!query) { previewResult.value = null; return }
  debouncePreview(() => {
    Effect.runPromise(svc.executeViewpoint({ query: queryToMapping(query, attributeTypes.value), limit: 0 }))
      .then((result) => { previewResult.value = result })
      .catch(() => { previewResult.value = null })
  })
}, { deep: true, immediate: true })

/** Full test-run: the real counts + warnings the query would return today (default
 * limit — the actual execution bound, not the tight preview limit), plus a `dry_run`
 * save-mode validation pass so a definition that would fail to persist is caught, and
 * highlighted at its offending node, before the user attempts to save. */
const testRun = async () => {
  testRunning.value = true
  testRunError.value = null
  testRunResult.value = null
  try {
    if (props.draft.query) {
      testRunResult.value = await Effect.runPromise(
        svc.executeViewpoint({ query: queryToMapping(props.draft.query, attributeTypes.value) }),
      )
    }
    const body = { definition: definitionToMapping(props.draft, attributeTypes.value), dry_run: true }
    const call = props.isCreating ? svc.createViewpointDefinition(body) : svc.editViewpointDefinition(body)
    const result = await Effect.runPromise(call)
    // A read-only master legitimately fails the persist gate — that is not feedback
    // about the query being tested, so it never becomes a banner here (it would
    // contradict the adjacent "adjust it freely, then Save as…" guidance).
    const issues = props.isReadOnly
      ? result.issues.filter((issue) => issue.code !== 'read-only-definition')
      : result.issues
    emit('issues', issues)
    highlightedNodeId.value = firstErrorNodeId(issues, props.draft)
  } catch (reason) {
    testRunError.value = readErrorMessage(reason)
  } finally {
    testRunning.value = false
  }
}

</script>

<template>
  <p
    v-if="!draft.query"
    class="empty-state"
  >
    Scope-only viewpoint — executes via its concept scope. Add a query to refine.
  </p>
  <div v-else>
    <QueryParametersPanel
      :model-value="draft.query.parameters"
      :catalog="catalog"
      @update:model-value="emitQueryUpdate({ parameters: $event })"
    />

    <QueryBindingsPanel
      :model-value="draft.query.bindings"
      :catalog="catalog"
      :parameter-names="parameterNames"
      @update:model-value="emitQueryUpdate({ bindings: $event })"
    />

    <h3>Show entities where…</h3>
    <CriteriaTreeBuilder
      :model-value="draft.query.entityCriteria"
      group-kind="entity"
      :catalog="catalog"
      :binding-names="bindingNames"
      :parameter-names="parameterNames"
      is-root
      @update:model-value="emitQueryUpdate({ entityCriteria: $event })"
    />

    <QueryDerivedAttributesPanel
      :model-value="draft.query.derived"
      :catalog="catalog"
      :binding-names="bindingNames"
      :parameter-names="parameterNames"
      @update:model-value="emitQueryUpdate({ derived: $event })"
    />

    <ViewpointTracePatternEditor
      :model-value="draft.query.tracePatterns"
      :catalog="catalog"
      @update:model-value="emitQueryUpdate({ tracePatterns: $event })"
    />

    <NeighborInclusionEditor
      :model-value="draft.query.includeConnected"
      :catalog="catalog"
      :binding-names="bindingNames"
      :parameter-names="parameterNames"
      @update:model-value="emitQueryUpdate({ includeConnected: $event })"
    />

    <h3>Connections displayed</h3>
    <div class="conn-controls">
      <label class="check">
        <input
          :checked="draft.query.connections.enabled"
          type="checkbox"
          @change="emitQueryUpdate({ connections: { ...draft.query.connections, enabled: ($event.target as HTMLInputElement).checked } })"
        > enabled
      </label>
      <select
        class="inp conn-traversal-select"
        :value="draft.query.connections.traversal"
        @change="emitQueryUpdate({ connections: { ...draft.query.connections, traversal: ($event.target as HTMLSelectElement).value as ExecutableQueryNode['connections']['traversal'] } })"
      >
        <option value="direct">
          direct only
        </option>
        <option value="derived">
          derived only — indirect, composed across intermediate elements
        </option>
        <option value="both">
          direct and derived
        </option>
      </select>
      <template v-if="draft.query.connections.traversal !== 'direct'">
        <label class="check">
          <input
            class="include-potential-checkbox"
            :checked="draft.query.connections.includePotential"
            type="checkbox"
            @change="emitQueryUpdate({ connections: { ...draft.query.connections, includePotential: ($event.target as HTMLInputElement).checked } })"
          > include potential (lower-confidence) relationships
        </label>
        <label class="num-field">
          max hops
          <input
            :value="draft.query.connections.maxHops ?? ''"
            type="number"
            min="2"
            placeholder="default"
            class="inp hops-input"
            @change="emitQueryUpdate({ connections: { ...draft.query.connections, maxHops: ($event.target as HTMLInputElement).value ? Number(($event.target as HTMLInputElement).value) : null } } )"
          >
        </label>
      </template>
    </div>
    <CriteriaTreeBuilder
      :model-value="draft.query.connections.criteria"
      group-kind="connection"
      :catalog="catalog"
      :binding-names="bindingNames"
      :parameter-names="parameterNames"
      is-root
      @update:model-value="emitQueryUpdate({ connections: { ...draft.query.connections, criteria: $event } })"
    />

    <div class="summary-panel">
      {{ summary }}
      <span
        v-if="formatPreviewCounts(previewResult)"
        class="preview-counts"
      >— {{ formatPreviewCounts(previewResult) }}</span>
    </div>

    <div class="test-run-row">
      <button
        type="button"
        class="btn"
        :disabled="testRunning"
        @click="testRun"
      >
        {{ testRunning ? 'Running…' : 'Test run' }}
      </button>
      <span
        v-if="testRunError"
        class="error"
      >{{ testRunError }}</span>
      <template v-else-if="testRunResult">
        <span class="test-run-counts">
          Entities: {{ testRunResult.returned_entity_count }} / {{ testRunResult.total_entity_count }} ·
          Connections: {{ testRunResult.returned_connection_count }} / {{ testRunResult.total_connection_count }}
        </span>
        <span
          v-for="warning in testRunResult.warnings"
          :key="warning"
          class="test-run-warning"
        >{{ warning }}</span>
      </template>
    </div>
    <TestRunMatchedEntities
      v-if="testRunResult && !testRunError"
      :entities="testRunResult.entities"
      :total-count="testRunResult.total_entity_count"
    />
  </div>
</template>

<style scoped>
.empty-state { font-size: 13px; color: #6b7280; background: #f9fafb; border: 1px dashed #d1d5db; border-radius: 8px; padding: 14px 16px; }
.error { color: #991b1b; background: #fee2e2; padding: 8px 12px; border-radius: 6px; }
.inp { padding: 5px 8px; border-radius: 6px; border: 1px solid #d1d5db; font-size: 12.5px; font-family: inherit; background: #fff; box-sizing: border-box; }
select.inp { cursor: pointer; max-width: 100%; }
.check { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; color: #374151; cursor: pointer; }
.check input { margin: 0; cursor: pointer; }
.num-field { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; color: #6b7280; font-weight: 600; }
.conn-controls { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; margin: 8px 0; }
.summary-panel { margin-top: 12px; padding: 10px 14px; border-radius: 8px; background: #eef2ff; color: #4338ca; font-size: 13px; }
.preview-counts { margin-left: 6px; font-weight: 600; }
.test-run-row { display: flex; align-items: center; gap: 10px; margin-top: 8px; flex-wrap: wrap; }
.test-run-counts { font-size: 12.5px; color: #374151; }
.test-run-warning { font-size: 12px; color: #92400e; background: #fef3c7; padding: 2px 8px; border-radius: 4px; }
.btn { appearance: none; border: 1px solid #d1d5db; background: #fff; color: #374151; border-radius: 6px; padding: 5px 12px; font-size: 12.5px; font-weight: 600; cursor: pointer; }
.btn:hover:not(:disabled) { border-color: #6366f1; color: #4338ca; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.hops-input { width: 72px; }
</style>
