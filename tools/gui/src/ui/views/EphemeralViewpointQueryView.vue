<script setup lang="ts">
/**
 * Query model — compose and execute an UNSAVED viewpoint (query + any presentation) in one
 * flow, persisting nothing (§5). A reduced editor (Query + Presentation tabs, reusing the same
 * builder/editor components as the saved-definition editor) drives an ephemeral execution that
 * reuses the same evaluator, projection, and result renderers via the four result views'
 * `adHoc` input. Available in read-only mode; only "Save as viewpoint…" is write-gated.
 */
import { computed, inject, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import { useWriteBlock } from '../composables/useWriteBlock'
import type { CriteriaCatalog, ViewpointDefinitionEnvelope, ViewpointValidationIssue } from '../../domain'
import { isEmptyQuery, mkDefinitionDraft } from '../../domain/viewpointDefinitionDraft'
import type { ViewpointDefinitionDraft } from '../../domain/viewpointDefinitionDraft'
import { definitionFromMapping } from '../../domain/viewpointDefinitionSerialization'
import { queryToMapping } from '../../domain/viewpointCriteriaSerialization'
import { mkPresentation } from '../../domain/viewpointPresentation'
import { attributeTypeTablesFromCatalog } from '../../domain/viewpointBindings'
import { buildEphemeralRequest } from '../lib/ephemeralViewpointRequest'
import { stageEphemeralViewpointDraft } from '../lib/ephemeralViewpointDraft'
import type { AdHocExecution } from '../lib/adHocExecution'
import {
  needsParameterPrompt,
  type ParameterDraft,
  parametersToWireValues,
} from '../lib/viewpointExecutionParameters'
import ViewpointParameterPrompt from '../components/ViewpointParameterPrompt.vue'
import ViewpointQueryTab from '../components/ViewpointQueryTab.vue'
import ViewpointPresentationTab from '../components/ViewpointPresentationTab.vue'
import GraphExploreView from './GraphExploreView.vue'
import ViewpointMatrixView from './ViewpointMatrixView.vue'
import ViewpointDiagramView from './ViewpointDiagramView.vue'
import ViewpointTablePage from '../components/ViewpointTablePage.vue'

const svc = inject(modelServiceKey)!
const route = useRoute()
const router = useRouter()
const writeBlocked = useWriteBlock()

// §5.1a "View as… (unsaved)": /viewpoints/query?slug=X re-presents a SAVED viewpoint with a
// different presentation. Run issues { slug, presentation } (not a query), so the stored
// definition's scope/query/derivation drive the population and are never mutated.
const overrideSlug = computed(() => (route.query.slug as string | undefined) ?? null)

const makeInitialDraft = (): ViewpointDefinitionDraft => {
  const draft = mkDefinitionDraft()
  // Start state: an empty match-all query with the exploration presentation.
  draft.presentation = mkPresentation('exploration')
  return draft
}

const catalog = ref<CriteriaCatalog | null>(null)
const draft = ref<ViewpointDefinitionDraft>(makeInitialDraft())
const issues = ref<readonly ViewpointValidationIssue[]>([])
const activeTab = ref<'query' | 'presentation'>('query')

const loadSavedDefinition = async (slug: string) => {
  const defs = await Effect.runPromise(svc.listViewpointDefinitions())
    .catch(() => [] as readonly ViewpointDefinitionEnvelope[])
  const envelope = defs.find((d) => d.slug === slug)
  if (!envelope) return
  draft.value = definitionFromMapping(envelope)
  activeTab.value = 'presentation'
}

onMounted(() => {
  void Effect.runPromise(svc.getCriteriaCatalog())
    .then((c) => { catalog.value = c })
    .catch(() => { catalog.value = null })
  if (overrideSlug.value) void loadSavedDefinition(overrideSlug.value)
})

const declaredDerivedNames = computed(
  () => draft.value.query?.derived.filter((d) => d.name.length > 0).map((d) => d.name) ?? [],
)

// ── debounced summary + count preview (the same summary the saved editor and MCP show) ──
const summary = ref('')
const previewCount = ref<number | null>(null)
let previewTimer: ReturnType<typeof setTimeout> | null = null
const saveAsHint =
  'Transfer this query + presentation into the saved-viewpoint editor (nothing is saved until you complete it there)'

const refreshPreview = () => {
  if (!draft.value.query || !catalog.value) { summary.value = ''; previewCount.value = null; return }
  const q = queryToMapping(draft.value.query, attributeTypeTablesFromCatalog(catalog.value))
  void Effect.runPromise(svc.summarizeViewpointQuery(q))
    .then((s) => { summary.value = s }).catch(() => { summary.value = '' })
  void Effect.runPromise(svc.executeViewpoint({ query: q, limit: 0 }))
    .then((r) => { previewCount.value = r.total_entity_count })
    .catch(() => { previewCount.value = null })
}
watch(() => draft.value.query, () => {
  if (previewTimer) clearTimeout(previewTimer)
  previewTimer = setTimeout(refreshPreview, 300)
}, { deep: true })

// ── run / result (draft vs last-executed; editing after a run marks the result stale) ──
const runId = ref(0)
const executed = ref<AdHocExecution | null>(null)
const resultStale = ref(false)

// A query (inline, or the saved definition loaded in override mode) may declare parameters;
// its declarations are the prompt signature in both modes (§5.3). The prompt gates Run when a
// required, undefaulted parameter is present, so the query never executes against a
// backend parameter-missing error — the values are supplied up front and recorded in provenance.
const parameterSignature = computed(() => draft.value.query?.parameters ?? [])
const promptVisible = ref(false)

const executeWith = (parameters: Record<string, unknown>) => {
  if (!draft.value.query || !catalog.value) return
  const request = buildEphemeralRequest(
    draft.value.query, draft.value.presentation, catalog.value, overrideSlug.value, parameters,
  )
  // Snapshot: the result reflects this exact spec (parameters included) until the next Run.
  executed.value = { request, presentation: draft.value.presentation }
  runId.value += 1
  resultStale.value = false
}

const run = () => {
  if (!draft.value.query || !catalog.value) return
  if (needsParameterPrompt(parameterSignature.value)) { promptVisible.value = true; return }
  executeWith({})
}

const onParametersSubmit = (parameterDraft: ParameterDraft) => {
  promptVisible.value = false
  executeWith(parametersToWireValues(parameterSignature.value, parameterDraft))
}
const onParametersCancel = () => { promptVisible.value = false }

watch([() => draft.value.query, () => draft.value.presentation], () => {
  if (executed.value !== null) resultStale.value = true
}, { deep: true })

const executedRepresentation = computed(() => executed.value?.presentation?.representation ?? 'exploration')
const resultComponent = computed(() => {
  if (executedRepresentation.value === 'table') return ViewpointTablePage
  if (executedRepresentation.value === 'matrix') return ViewpointMatrixView
  return executedRepresentation.value === 'diagram' ? ViewpointDiagramView : GraphExploreView
})
// ViewpointTablePage is a component with a required (here unused) `slug`; the views need only adHoc.
// (The result block only renders when `executed` is set; `?? undefined` satisfies the prop type.)
const resultProps = computed(() => {
  const adHoc = executed.value ?? undefined
  return executedRepresentation.value === 'table' ? { slug: '', adHoc } : { adHoc }
})

const clear = () => {
  const hasContent = executed.value !== null || (draft.value.query !== null && !isEmptyQuery(draft.value.query))
  if (hasContent && !window.confirm('Clear the current query, presentation, and result?')) return
  draft.value = makeInitialDraft()
  issues.value = []
  executed.value = null
  resultStale.value = false
  summary.value = ''
  previewCount.value = null
}

const saveAs = () => {
  if (writeBlocked.value) return
  // Route-scoped, in-memory hand-off (no persistence): /viewpoints/new adopts the drafts.
  stageEphemeralViewpointDraft({ query: draft.value.query, presentation: draft.value.presentation })
  void router.push('/viewpoints/new')
}
</script>

<template>
  <div class="page">
    <div class="topbar">
      <div>
        <h1>{{ overrideSlug ? 'View as… (unsaved)' : 'Query model' }}</h1>
        <p
          v-if="overrideSlug"
          class="subtitle"
        >
          Re-present the saved viewpoint <strong>{{ overrideSlug }}</strong> with a different
          presentation. The stored definition is never changed — only this view is affected.
        </p>
        <p
          v-else
          class="subtitle"
        >
          Compose and run a query with any presentation — nothing is persisted. Use
          <em>Save as viewpoint…</em> to keep it as a saved definition.
        </p>
      </div>
      <RouterLink
        to="/viewpoints"
        class="back-link"
      >
        ← Viewpoints
      </RouterLink>
    </div>

    <div
      v-if="draft && catalog"
      class="editor"
    >
      <div class="tabs">
        <button
          type="button"
          :class="{ active: activeTab === 'query' }"
          @click="activeTab = 'query'"
        >
          Query
        </button>
        <button
          type="button"
          :class="{ active: activeTab === 'presentation' }"
          @click="activeTab = 'presentation'"
        >
          Presentation
        </button>
      </div>

      <ViewpointQueryTab
        v-if="activeTab === 'query'"
        :draft="draft"
        :catalog="catalog"
        :is-creating="true"
        :is-read-only="overrideSlug !== null"
        @update:query="draft.query = $event"
        @issues="issues = $event"
      />
      <ViewpointPresentationTab
        v-else
        v-model="draft.presentation"
        :catalog="catalog"
        :declared-derived-names="declaredDerivedNames"
      />

      <p class="preview">
        <span v-if="summary">{{ summary }}</span>
        <span
          v-if="previewCount !== null"
          class="count-chip"
        >≈ {{ previewCount }} matching</span>
      </p>

      <div class="actions">
        <button
          type="button"
          class="primary-btn"
          @click="run"
        >
          ▶ Run
        </button>
        <button
          type="button"
          class="ghost-btn"
          @click="clear"
        >
          Clear
        </button>
        <button
          v-if="!writeBlocked"
          type="button"
          class="save-as-btn"
          :title="saveAsHint"
          @click="saveAs"
        >
          Save as viewpoint…
        </button>
        <span
          v-else
          class="write-block-note"
        >Saving is unavailable in this read-only workspace — you can still run the query.</span>
      </div>
    </div>
    <p
      v-else
      class="loading"
    >
      Loading criteria catalog…
    </p>

    <div
      v-if="executed"
      class="result"
    >
      <p
        v-if="resultStale"
        class="stale-note"
      >
        The query or presentation changed — this result is stale. Press <strong>Run</strong> to refresh it.
      </p>
      <component
        :is="resultComponent"
        :key="runId"
        v-bind="resultProps"
      />
    </div>

    <ViewpointParameterPrompt
      v-if="promptVisible"
      :parameters="parameterSignature"
      @submit="onParametersSubmit"
      @cancel="onParametersCancel"
    />
  </div>
</template>

<style scoped>
.page { padding: 20px 28px; max-width: 1100px; }
.topbar { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.subtitle { color: #6b7280; font-size: 13px; margin: 2px 0 12px; max-width: 640px; }
.back-link {
  font-size: 13px; color: #4338ca; text-decoration: none;
  border: 1px solid #c7d2fe; border-radius: 6px; padding: 5px 12px; white-space: nowrap;
}
.back-link:hover { background: #eef2ff; }
.tabs { display: flex; gap: 6px; border-bottom: 1px solid #e5e7eb; margin-bottom: 14px; }
.tabs button {
  appearance: none; border: none; background: none; padding: 8px 14px;
  font-weight: 600; color: #6b7280; cursor: pointer; border-bottom: 2px solid transparent;
}
.tabs button.active { color: #4338ca; border-bottom-color: #6366f1; }
.preview { color: #4b5563; font-size: 13px; display: flex; align-items: center; gap: 10px; min-height: 20px; }
.count-chip {
  background: #eef2ff; color: #4338ca; border-radius: 999px;
  padding: 2px 10px; font-size: 12px; font-weight: 600;
}
.actions { margin-top: 16px; display: flex; align-items: center; gap: 10px; }
.primary-btn {
  background: #6366f1; color: #fff; border: none; border-radius: 7px;
  padding: 8px 18px; font-weight: 600; cursor: pointer;
}
.ghost-btn {
  background: #fff; color: #374151; border: 1px solid #d1d5db;
  border-radius: 7px; padding: 8px 16px; font-weight: 600; cursor: pointer;
}
.ghost-btn:hover { border-color: #9ca3af; }
.save-as-btn {
  background: #fff; color: #4338ca; border: 1px solid #c7d2fe;
  border-radius: 7px; padding: 8px 16px; font-weight: 600; cursor: pointer;
}
.save-as-btn:hover { background: #eef2ff; }
.write-block-note { color: #6b7280; font-size: 12.5px; }
.result { margin-top: 22px; border-top: 1px solid #e5e7eb; padding-top: 14px; }
.stale-note {
  background: #fffbeb; color: #92400e; border: 1px solid #fde68a;
  border-radius: 6px; padding: 8px 12px; font-size: 13px;
}
.loading { color: #6b7280; }
</style>
