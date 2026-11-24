<script setup lang="ts">
/**
 * The stress-analysis workspace (sketch 06; owner decisions of 2026-11-22): the analysis's tables in
 * tabs on the left — Naive architecture · Stressors · End states · Adaptations · Integration — and on
 * the right the naive architecture's scope diagram, marked with what the open tab is about. Not a
 * wizard: any tab, any order.
 */
import { computed, inject, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { modelServiceKey, toastKey } from '../keys'
import { stableEntityId } from '../../domain/artifactId'
import type { WorkspaceTab } from '../../domain/stressAnalysis/analysisProgress'
import { cell } from '../../domain/stressAnalysis/analysisRows'
import type { Marks } from '../../domain/stressAnalysis/workspaceMarks'
import { diffMarks, framedMarks, hitMarks } from '../../domain/stressAnalysis/workspaceMarks'
import { documentDetailRoute } from '../router/artifactRoutes'
import { useStressAnalysis } from '../composables/useStressAnalysis'
import { useAnalysisEdits } from '../composables/useAnalysisEdits'
import { useCandidates } from '../composables/useCandidates'
import WorkspaceCanvas from '../components/stressWorkspace/WorkspaceCanvas.vue'
import WhatIsLeft from '../components/stressWorkspace/WhatIsLeft.vue'
import StressorsTab from '../components/stressWorkspace/StressorsTab.vue'
import EndStatesTab from '../components/stressWorkspace/EndStatesTab.vue'
import AdaptationsTab from '../components/stressWorkspace/AdaptationsTab.vue'
import IntegrationTab from '../components/stressWorkspace/IntegrationTab.vue'
import CandidateOperations from '../components/stressWorkspace/CandidateOperations.vue'
import CandidateCanvas from '../components/stressWorkspace/CandidateCanvas.vue'

const svc = inject(modelServiceKey)!
const toast = inject(toastKey, () => undefined)
const route = useRoute()
const router = useRouter()
const documentId = computed(() => String(route.params.artifactId))
const analysis = useStressAnalysis(svc, () => documentId.value)
const edits = useAnalysisEdits(analysis, toast)
const candidates = useCandidates(svc, () => analysis.naiveId.value, () => analysis.scopeDiagram.value)

const TABS: readonly WorkspaceTab[] = ['naive', 'stressors', 'end-states', 'adaptations', 'integration']
const tab = computed<WorkspaceTab>({
  get: () => TABS.find((one) => one === route.query.tab) ?? 'stressors',
  set: (next) => { void router.replace({ query: { tab: next } }) },
})
const tabs = computed(() => [
  { id: 'naive' as const, label: 'Naive architecture', count: `${analysis.naive.value?.diff.length ?? 0} ops` },
  { id: 'stressors' as const, label: 'Stressors', count: String(analysis.stressors.value.length) },
  { id: 'end-states' as const, label: 'End states', count: String(analysis.endStates.value.length) },
  {
    id: 'adaptations' as const, label: 'Adaptations',
    count: String(Math.max(candidates.inAnalysis.value.length - 1, 0)),
  },
  { id: 'integration' as const, label: 'Integration', count: '' },
])

const selected = ref<string | null>(null)
const endStateFocus = ref<string | null>(null)
const framed = ref<string | null>(null)
/** The candidate being sketched on the canvas, if any. */
const sketching = ref<string | null>(null)
const sketched = computed(() => candidates.all.value.find((one) => one.id === sketching.value) ?? null)
/** A change recorded in the sketched candidate: its table, and the naive architecture's names, follow. */
const recorded = async () => {
  await candidates.compareWith(candidates.against.value)
  if (sketching.value === analysis.naiveId.value) await analysis.reload()
}
const doneSketching = async () => {
  sketching.value = null
  await recorded()
}

/** The naive architecture's own id for an element the canvas names by its stable id. */
const fullIdOf = (stableId: string): string =>
  analysis.naive.value?.view.entities.find((one) => stableEntityId(one.id) === stableId)?.id ?? stableId

const hitsOf = (stressors: readonly string[]): ReadonlyMap<string, readonly string[]> =>
  new Map(stressors.map((id) => [id, analysis.hitsOf(id)]))
const readsCandidate = computed(() => tab.value === 'naive' || tab.value === 'adaptations')
const marks = computed((): Marks => {
  const around = framed.value ? framedMarks([framed.value], 'The row or hint selected on the left') : new Map()
  if (readsCandidate.value) return new Map([...diffMarks(candidates.comparison.value?.diff ?? []), ...around])
  if (tab.value === 'stressors' && selected.value) return new Map([...hitMarks(hitsOf([selected.value])), ...around])
  if (tab.value === 'end-states' && endStateFocus.value) {
    const under = analysis.stressors.value.filter((row) => cell(row, 'end_state') === endStateFocus.value)
    return hitMarks(hitsOf(under.map((row) => row.row_id)))
  }
  return around
})
const drawing = computed(() => (readsCandidate.value ? candidates.comparison.value?.drawing : null)
  ?? analysis.naive.value?.drawing ?? null)
const hint = computed(() => tab.value === 'stressors' && selected.value
  ? `Press an element to tick or untick it for ${selected.value} · Scroll to zoom · Drag to pan`
  : 'Select a row or an element · Scroll to zoom · Drag to pan')

/** A press on the picture: ticks or unticks it for the stressor in focus, otherwise frames it. */
const pick = (stableId: string) => {
  const stressor = selected.value
  if (tab.value !== 'stressors' || !stressor) {
    framed.value = framed.value === stableId ? null : stableId
    return
  }
  const tick = analysis.ticks.value.find(
    (one) => one.stressor === stressor && stableEntityId(one.component) === stableId,
  )
  void (tick ? edits.untick(tick) : edits.tick(stressor, fullIdOf(stableId)))
}

const openRow = (target: WorkspaceTab, row: string) => {
  tab.value = target
  if (target === 'end-states') {
    endStateFocus.value = analysis.endStates.value.some((one) => one.row_id === row) ? row : null
  }
  else selected.value = row
}

watch([tab, () => analysis.naiveId.value, () => candidates.all.value], async ([now, naive]) => {
  framed.value = null
  if (now === 'naive' && naive) await candidates.select(naive)
  const first = candidates.inAnalysis.value.find((one) => one.id !== naive)
  if (now === 'adaptations' && first && (!candidates.selected.value || candidates.selected.value === naive)) {
    await candidates.select(first.id)
  }
})
onMounted(async () => {
  await analysis.reload()
  await candidates.load()
})
</script>

<template>
  <div class="stress-ws page">
    <div class="page-hdr">
      <RouterLink
        class="back"
        :to="documentDetailRoute(documentId)"
      >
        ← Document
      </RouterLink>
      <h1>{{ analysis.document.value?.title ?? 'Stress analysis' }}</h1>
      <WhatIsLeft
        :progress="analysis.progress.value"
        @open="openRow"
      />
    </div>
    <div class="meta">
      <span class="badge">stress analysis</span>
      <span class="status">{{ analysis.document.value?.status }}</span>
      <span
        v-if="analysis.naive.value"
        class="mono"
      >scope: {{ analysis.naive.value.drawing?.name ?? 'explicit elements' }}
        ({{ analysis.naive.value.view.entities.length }} elements)</span>
    </div>
    <p
      v-if="analysis.question.value"
      class="question"
    >
      Question: {{ analysis.question.value }}
    </p>
    <p
      v-if="analysis.error.value"
      class="err"
      role="alert"
    >
      {{ analysis.error.value }}
    </p>
    <div class="ws">
      <section
        class="pane card"
        aria-label="Analysis tables"
      >
        <div
          class="tabs"
          role="tablist"
        >
          <button
            v-for="one in tabs"
            :key="one.id"
            type="button"
            role="tab"
            class="tab"
            :aria-selected="tab === one.id"
            :data-tab="one.id"
            @click="tab = one.id"
          >
            {{ one.label }}<small>{{ one.count }}</small>
          </button>
        </div>
        <CandidateOperations
          v-if="tab === 'naive' && candidates.selected.value === analysis.naiveId.value"
          :candidates="candidates"
          :naive-id="analysis.naiveId.value"
          :name-of="analysis.nameOf"
          @frame="framed = $event && stableEntityId($event)"
          @sketch="sketching = $event"
        />
        <StressorsTab
          v-else-if="tab === 'stressors'"
          :analysis="analysis"
          :edits="edits"
          :selected="selected"
          @select="selected = $event"
          @show="framed = stableEntityId($event)"
          @open-row="openRow"
        />
        <EndStatesTab
          v-else-if="tab === 'end-states'"
          :stressors="analysis.stressors.value"
          :end-states="analysis.endStates.value"
          :ticks="analysis.ticks.value"
          :focus="endStateFocus"
          :selected-row="selected"
          :name-of="analysis.nameOf"
          @focus="endStateFocus = $event"
          @move="edits.setEndState"
          @create-and-move="edits.createEndStateFor"
          @untick="edits.untick"
          @tick="edits.tick"
          @note="edits.note"
        />
        <AdaptationsTab
          v-else-if="tab === 'adaptations'"
          :analysis="analysis"
          :candidates="candidates"
          @frame="framed = $event && stableEntityId($event)"
          @sketch="sketching = $event"
        />
        <IntegrationTab
          v-else-if="tab === 'integration'"
          :candidates="candidates"
          :name-of="analysis.nameOf"
        />
      </section>
      <section aria-label="Canvas">
        <CandidateCanvas
          v-if="sketched && analysis.scopeDiagram.value"
          :key="sketched.id"
          :candidate-id="sketched.id"
          :name="sketched.name"
          :role="sketched.id === analysis.naiveId.value ? 'Naive architecture' : 'Adaptation'"
          :diagram-id="analysis.scopeDiagram.value"
          :changed="diffMarks(candidates.comparison.value?.diff ?? [])"
          @recorded="recorded"
          @done="doneSketching"
        />
        <WorkspaceCanvas
          v-else
          :diagram-id="analysis.scopeDiagram.value"
          :drawing="drawing"
          :marks="marks"
          :hint="hint"
          @pick="pick"
        />
        <p
          v-if="readsCandidate"
          class="legend"
        >
          + added · ~ changed — a field differs · − removed, drawn as a faded dashed ghost · select a row
          to frame it here
        </p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.page { padding: 16px 24px; }
.page-hdr { display: flex; gap: 14px; align-items: center; }
.page-hdr h1 { flex: 1; font-size: 20px; margin: 0; }
.back { color: var(--muted); text-decoration: none; font-size: 13px; }
.meta { display: flex; gap: 10px; align-items: center; margin: 8px 0 2px; font-size: 12px; color: var(--muted); }
.badge { background: var(--accent-soft); color: var(--accent-strong); border-radius: 3px; padding: 2px 8px; }
.mono { font-family: ui-monospace, monospace; }
.question { color: var(--muted); font-size: 12.5px; margin: 2px 0 10px; }
.err { color: var(--danger-strong); font-size: 12.5px; }
.ws { display: grid; grid-template-columns: minmax(440px, 46%) minmax(0, 1fr); gap: 12px; align-items: start; }
.pane { min-width: 0; }
.legend { font-size: 11.5px; color: var(--text-2); margin: 4px 2px; }
@media (max-width: 1100px) { .ws { grid-template-columns: minmax(0, 1fr); } }
</style>
<style src="../components/stressWorkspace/workspace.css"></style>
