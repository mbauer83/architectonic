<script setup lang="ts">
/**
 * The stress-analysis workspace (sketch 06; owner decisions of 2026-11-22): the analysis's tables in
 * tabs on the left — Naive architecture · Stressors · End states · Adaptations · Integration — and on
 * the right the naive architecture as it is drawn, marked with what the open tab is about. Not a
 * wizard: any tab, any order. Below the tabs the test set, apart from them; while an architecture is
 * judged against it, the canvas shows that architecture. Opened from the start page, it sketches the
 * naive architecture straight away, with a note saying once what it is; done sketching it, the
 * stressors come next.
 */
import { computed, inject, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { modelServiceKey, toastKey } from '../keys'
import { stableEntityId } from '../../domain/artifactId'
import type { WorkspaceTab } from '../../domain/stressAnalysis/analysisProgress'
import { cell } from '../../domain/stressAnalysis/analysisRows'
import type { Marks } from '../../domain/candidates/canvasMarks'
import { diffMarks, framedMarks } from '../../domain/candidates/canvasMarks'
import { hitMarks } from '../../domain/stressAnalysis/workspaceMarks'
import { documentDetailRoute } from '../router/artifactRoutes'
import { useStressAnalysis } from '../composables/useStressAnalysis'
import { useAnalysisEdits } from '../composables/useAnalysisEdits'
import { useCandidates } from '../composables/useCandidates'
import { useTestSet } from '../composables/useTestSet'
import MarkedCanvas from '../components/candidates/MarkedCanvas.vue'
import WhatIsLeft from '../components/stressWorkspace/WhatIsLeft.vue'
import StressorsTab from '../components/stressWorkspace/StressorsTab.vue'
import EndStatesTab from '../components/stressWorkspace/EndStatesTab.vue'
import AdaptationsTab from '../components/stressWorkspace/AdaptationsTab.vue'
import IntegrationTab from '../components/stressWorkspace/IntegrationTab.vue'
import TestSetSection from '../components/stressWorkspace/TestSetSection.vue'
import CandidateOperations from '../components/candidates/CandidateOperations.vue'
import CandidateCanvas from '../components/candidates/CandidateCanvas.vue'
import ModelMovedBanner from '../components/candidates/ModelMovedBanner.vue'
import NaiveIntroNote from '../components/stressWorkspace/NaiveIntroNote.vue'
import AnalysisMeta from '../components/stressWorkspace/AnalysisMeta.vue'

const svc = inject(modelServiceKey)!
const toast = inject(toastKey, () => undefined)
const route = useRoute()
const router = useRouter()
const documentId = computed(() => String(route.params.artifactId))
const analysis = useStressAnalysis(svc, () => documentId.value)
const edits = useAnalysisEdits(analysis, toast)
const candidates = useCandidates(svc, { root: () => analysis.naiveId.value, scopeDiagram: () => '' })
const testSet = useTestSet(svc, analysis, () => documentId.value, toast)
/** The test stressor in focus in the judge walk. */
const judged = ref<string | null>(null)
/** The candidate being judged against the test set, read against the naive architecture; none for the naive. */
const judgedCandidate = computed(() => {
  const judging = testSet.judging.value
  return judging && judging !== 'naive' && candidates.comparison.value?.candidate === judging ? judging : null
})
watch(() => testSet.judging.value, async (judging) => {
  if (judging && judging !== 'naive') await candidates.select(judging, analysis.naiveId.value)
  if (!judging) judged.value = null
})

const TABS: readonly WorkspaceTab[] = ['naive', 'stressors', 'end-states', 'adaptations', 'integration']
const tab = computed<WorkspaceTab>({
  get: () => TABS.find((one) => one === route.query.tab) ?? 'stressors',
  set: (next) => { void router.replace({ query: { tab: next } }) },
})
/** The naive architecture as listed: what its operation count reads, kept current with every recording. */
const opsCount = (count: number): string => `${count} ${count === 1 ? 'op' : 'ops'}`
const naiveSummary = computed(() => candidates.all.value.find((one) => one.id === analysis.naiveId.value) ?? null)
const tabs = computed(() => [
  { id: 'naive' as const, label: 'Naive architecture', count: opsCount(naiveSummary.value?.operations ?? 0) },
  { id: 'stressors' as const, label: 'Stressors', count: String(analysis.stressors.value.length) },
  { id: 'end-states' as const, label: 'End states', count: String(analysis.endStates.value.length) },
  {
    id: 'adaptations' as const, label: 'Adaptations',
    count: String(Math.max(candidates.inStack.value.length - 1, 0)),
  },
  { id: 'integration' as const, label: 'Integration', count: '' },
])

const selected = ref<string | null>(null)
const endStateFocus = ref<string | null>(null)
const framed = ref<string | null>(null)
/** The candidate being sketched on the canvas, if any. */
const sketching = ref<string | null>(null)
const sketched = computed(() => candidates.all.value.find((one) => one.id === sketching.value) ?? null)
/** A change recorded in the sketched candidate: its table, its count and the naive architecture's names follow. */
const recorded = async () => {
  await Promise.all([candidates.compareWith(candidates.against.value), candidates.load()])
  if (sketching.value === analysis.naiveId.value) await analysis.reload()
}
/** The candidate read on the left, which the "model moved" band speaks about. */
const read = computed(() => candidates.all.value.find((one) => one.id === candidates.selected.value) ?? null)
const rebasing = ref(false)
const rebase = async () => {
  const id = read.value?.id
  if (!id) return
  rebasing.value = true
  if (await candidates.rebase(id)) toast(`Re-based ${read.value?.name ?? id} on the model as it stands now.`)
  rebasing.value = false
  if (id === analysis.naiveId.value) await analysis.reload()
}
/** The note that says once what the naive architecture is, as it is first sketched. */
const introducing = ref(route.query.sketch === 'naive')
/** Done sketching: the naive architecture points on to the stressors written against it. */
const doneSketching = async () => {
  const wasNaive = sketching.value === analysis.naiveId.value
  sketching.value = null
  introducing.value = false
  if (wasNaive) tab.value = 'stressors'
  await recorded()
}

/** The naive architecture's own id for an element the canvas names by its stable id. */
const fullIdOf = (stableId: string): string =>
  analysis.naive.value?.view.entities.find((one) => stableEntityId(one.id) === stableId)?.id ?? stableId

const hitsOf = (stressors: readonly string[]): ReadonlyMap<string, readonly string[]> =>
  new Map(stressors.map((id) => [id, analysis.hitsOf(id)]))
/** Whether the canvas reads the selected candidate's comparison: on a candidate tab, or judging a candidate. */
const readsCandidate = computed(() => (testSet.judging.value
  ? judgedCandidate.value !== null
  : tab.value === 'naive' || tab.value === 'adaptations'))
const marks = computed((): Marks => {
  const around = framed.value ? framedMarks([framed.value], 'The row or hint selected on the left') : new Map()
  if (readsCandidate.value) return new Map([...diffMarks(candidates.comparison.value?.diff ?? []), ...around])
  if (testSet.judging.value) return around
  if (tab.value === 'stressors' && selected.value) return new Map([...hitMarks(hitsOf([selected.value])), ...around])
  if (tab.value === 'end-states' && endStateFocus.value) {
    const under = analysis.stressors.value.filter((row) => cell(row, 'end_state') === endStateFocus.value)
    return hitMarks(hitsOf(under.map((row) => row.row_id)))
  }
  return around
})
const drawing = computed(() => (readsCandidate.value ? candidates.comparison.value?.drawing : null)
  ?? analysis.naive.value?.drawing ?? null)
const hint = computed(() => {
  if (testSet.judging.value) {
    return judgedCandidate.value
      ? 'The candidate being judged, marked with what it changes from the naive · Scroll to zoom'
      : 'The naive architecture, being judged · Scroll to zoom · Drag to pan'
  }
  return tab.value === 'stressors' && selected.value
    ? `Press an element to tick or untick it for ${selected.value} · Scroll to zoom · Drag to pan`
    : 'Select a row or an element · Scroll to zoom · Drag to pan'
})

/** A press on the picture: ticks or unticks it for the stressor in focus, otherwise frames it. */
const pick = (stableId: string) => {
  const stressor = selected.value
  if (tab.value !== 'stressors' || !stressor || testSet.judging.value) {
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
  const first = candidates.inStack.value.find((one) => one.id !== naive)
  if (now === 'adaptations' && first && (!candidates.selected.value || candidates.selected.value === naive)) {
    await candidates.select(first.id)
  }
})
onMounted(async () => {
  await analysis.reload()
  await candidates.load()
  // The band says whether the model moved under the naive architecture on every tab, not only its own.
  if (!candidates.selected.value && analysis.naiveId.value) await candidates.select(analysis.naiveId.value)
  // Started a moment ago: the naive architecture opens for sketching, where it is drawn on a stored diagram.
  if (introducing.value && analysis.drawnOn.value) sketching.value = analysis.naiveId.value
})
</script>

<template>
  <div class="workbench page">
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
    <AnalysisMeta :analysis="analysis" />
    <p
      v-if="analysis.error.value"
      class="err"
      role="alert"
    >
      {{ analysis.error.value }}
    </p>
    <ModelMovedBanner
      v-if="read && candidates.comparison.value?.candidate === read.id"
      :name="read.name"
      :standing="candidates.comparison.value.standing"
      :busy="rebasing"
      @rebase="rebase"
    />
    <div class="ws">
      <div class="left">
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
            role="naive architecture · the initial candidate"
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
        <TestSetSection
          :analysis="analysis"
          :candidates="candidates"
          :test-set="testSet"
          :selected="judged"
          @select="judged = $event"
        />
      </div>
      <section aria-label="Canvas">
        <NaiveIntroNote
          v-if="introducing && sketched?.id === analysis.naiveId.value"
          @dismiss="introducing = false"
        />
        <CandidateCanvas
          v-if="sketched && analysis.drawnOn.value"
          :key="sketched.id"
          :candidate-id="sketched.id"
          :name="sketched.name"
          :role="sketched.id === analysis.naiveId.value ? 'Naive architecture' : 'Adaptation'"
          :done-label="sketched.id === analysis.naiveId.value ? 'Done sketching · on to Stressors' : 'Done sketching'"
          :diagram-id="analysis.drawnOn.value"
          :changed="diffMarks(candidates.comparison.value?.diff ?? [])"
          @recorded="recorded"
          @done="doneSketching"
        />
        <MarkedCanvas
          v-else
          :diagram-id="analysis.drawnOn.value"
          :drawing="drawing"
          :marks="marks"
          :hint="hint"
          empty-text="Nothing to draw: the naive architecture is empty."
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
.err { color: var(--danger-strong); font-size: 12.5px; }
.ws { display: grid; grid-template-columns: minmax(440px, 46%) minmax(0, 1fr); gap: 12px; align-items: start; }
.left, .pane { min-width: 0; }
/* The picture stays in view while the test set below the tables is walked. */
.ws > section[aria-label="Canvas"] { position: sticky; top: 8px; }
.legend { font-size: 11.5px; color: var(--text-2); margin: 4px 2px; }
@media (max-width: 1100px) { .ws { grid-template-columns: minmax(0, 1fr); } }
</style>
<style src="../components/candidates/workbench.css"></style>
