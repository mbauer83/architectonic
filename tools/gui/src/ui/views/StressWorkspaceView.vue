<script setup lang="ts">
/**
 * The stress-analysis workspace (sketch 06; owner decisions of 2026-11-22): the analysis's tables in
 * tabs on the left — Naive architecture · Stressors · End states · Adaptations · Integration — and on
 * the right the naive architecture as it composes, marked with what the open tab is about
 * (`useWorkspaceCanvas`); a splitter between the two moves by drag or by ← and →. Not a wizard: any
 * tab, any order. Below the tabs the test set, apart from them; while an architecture is judged against
 * it, the canvas shows that architecture. Opened from the start page, it sketches the naive
 * architecture straight away on its own canvas — no stored diagram needed — with a note saying once what it
 * is; done sketching it, the stressors come next. *Apply…* answers with what is left, then with the
 * candidate's dry run.
 */
import { computed, inject, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { modelServiceKey, toastKey } from '../keys'
import { stableEntityId } from '../../domain/artifactId'
import type { WorkspaceTab } from '../../domain/stressAnalysis/analysisProgress'
import { cell, cellIds } from '../../domain/stressAnalysis/analysisRows'
import { INTEGRATION, NAIVE } from '../../domain/stressAnalysis/testSet'
import { diffMarks } from '../../domain/candidates/elementMarks'
import { stackLine } from '../../domain/candidates/candidateStack'
import { documentDetailRoute } from '../router/artifactRoutes'
import { useStressAnalysis } from '../composables/useStressAnalysis'
import { useAnalysisEdits } from '../composables/useAnalysisEdits'
import { useCandidates } from '../composables/useCandidates'
import { useTestSet } from '../composables/useTestSet'
import { useWorkspaceCanvas } from '../composables/useWorkspaceCanvas'
import DiagramSplitLayout from '../components/DiagramSplitLayout.vue'
import MarkedCanvas from '../components/candidates/MarkedCanvas.vue'
import WhatIsLeft from '../components/stressWorkspace/WhatIsLeft.vue'
import WorkspaceApply from '../components/stressWorkspace/WorkspaceApply.vue'
import StressorsTab from '../components/stressWorkspace/StressorsTab.vue'
import EndStatesTab from '../components/stressWorkspace/EndStatesTab.vue'
import AdaptationsTab from '../components/stressWorkspace/AdaptationsTab.vue'
import IntegrationTab from '../components/stressWorkspace/IntegrationTab.vue'
import TestSetSection from '../components/stressWorkspace/TestSetSection.vue'
import CandidateOperations from '../components/candidates/CandidateOperations.vue'
import CandidateCanvas from '../components/candidates/CandidateCanvas.vue'
import ModelMovedBanner from '../components/candidates/ModelMovedBanner.vue'
import NaiveIntroNote from '../components/stressWorkspace/NaiveIntroNote.vue'
import TouchingCandidates from '../components/stressWorkspace/TouchingCandidates.vue'
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
/** Whether *judging* names a candidate: not the naive, nor the integration of candidates integrated apart. */
const isCandidate = (judging: string | null): judging is string =>
  judging !== null && judging !== NAIVE && judging !== INTEGRATION
/** The candidate being judged against the test set, read against the naive architecture; none for the naive. */
const judgedCandidate = computed(() => {
  const judging = testSet.judging.value
  return isCandidate(judging) && candidates.comparison.value?.candidate === judging ? judging : null
})
watch(() => testSet.judging.value, async (judging) => {
  if (isCandidate(judging)) await candidates.select(judging, analysis.naiveId.value)
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
const canvas = useWorkspaceCanvas(svc, analysis, candidates, edits, {
  tab, selected, endStateFocus, framed, judging: testSet.judging, judgedCandidate,
})
/** The candidate being sketched on the canvas, if any. */
const sketching = ref<string | null>(null)
const sketched = computed(() => candidates.all.value.find((one) => one.id === sketching.value) ?? null)
/**
 * A change recorded in candidate *id* (the one sketched): its table, its count and, for the naive architecture,
 * the analysis's reading of it follow. Named rather than read off the sketch, which Done sketching has closed.
 */
const recorded = async (id = sketching.value) => {
  await Promise.all([candidates.compareWith(candidates.against.value), candidates.load()])
  if (id === analysis.naiveId.value) await analysis.reload()
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
  const done = sketching.value
  sketching.value = null
  introducing.value = false
  if (done === analysis.naiveId.value) tab.value = 'stressors'
  await recorded(done)
}
/** The adaptations answering an end state, by name. */
const answeredBy = (endState: string): readonly string[] => analysis.adaptations.value
  .filter((row) => cellIds(row, 'end_states').includes(endState))
  .map((row) => cell(row, 'candidate_architecture'))
  .map((id) => candidates.all.value.find((one) => stableEntityId(one.id) === stableEntityId(id))?.name ?? id)
const applied = async (name: string) => {
  toast(`Applied ${name} to the model.`)
  await Promise.all([candidates.load(), analysis.reload()])
}

const openRow = (target: WorkspaceTab, row: string) => {
  tab.value = target
  if (target === 'end-states') {
    endStateFocus.value = analysis.endStates.value.some((one) => one.row_id === row) ? row : null
  }
  else selected.value = row
}

watch([tab, () => analysis.naiveId.value, () => candidates.all.value], async ([now, naive]) => {
  if (now === 'naive' && naive) await candidates.select(naive)
  const first = candidates.inStack.value.find((one) => one.id !== naive)
  if (now === 'adaptations' && first && (!candidates.selected.value || candidates.selected.value === naive)) {
    await candidates.select(first.id)
  }
})
watch(tab, () => { framed.value = null })
onMounted(async () => {
  await analysis.reload()
  await candidates.load()
  // The band says whether the model moved under the naive architecture on every tab, not only its own.
  if (!candidates.selected.value && analysis.naiveId.value) await candidates.select(analysis.naiveId.value)
  // Started a moment ago: the naive architecture opens for sketching on its own canvas.
  if (introducing.value && analysis.naiveId.value) sketching.value = analysis.naiveId.value
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
      <WorkspaceApply
        :svc="svc"
        :analysis="analysis"
        :candidates="candidates"
        @open="openRow"
        @applied="applied"
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
    <DiagramSplitLayout
      class="ws"
      edge="left"
      :initial-width="640"
      :min-width="440"
      :max-width="1100"
      :max-share="0.62"
    >
      <template #sidebar>
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
              :framed="framed"
              @frame="framed = $event && stableEntityId($event)"
              @sketch="sketching = $event"
            />
            <TouchingCandidates
              v-if="tab === 'naive' && naiveSummary"
              :scope="naiveSummary.scope"
              :candidates="candidates.all.value"
              :own="candidates.inStack.value.map((one) => one.id)"
            />
            <StressorsTab
              v-if="tab === 'stressors'"
              :analysis="analysis"
              :edits="edits"
              :selected="selected"
              :ticking="canvas.ticking.value"
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
              :answered-by="answeredBy"
              @focus="endStateFocus = $event"
              @move="edits.setEndState"
              @create-and-move="edits.createEndStateFor"
              @untick="edits.untick"
              @tick="edits.tick"
              @note="edits.note"
              @no-change="edits.answerNoChange"
            />
            <AdaptationsTab
              v-else-if="tab === 'adaptations'"
              :analysis="analysis"
              :candidates="candidates"
              :framed="framed"
              @frame="framed = $event && stableEntityId($event)"
              @sketch="sketching = $event"
            />
            <IntegrationTab
              v-else-if="tab === 'integration'"
              :candidates="candidates"
              :analysis="analysis"
              @open="openRow"
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
      </template>
      <template #canvas>
        <section aria-label="Canvas">
          <CandidateCanvas
            v-if="sketched"
            :key="sketched.id"
            :candidate-id="sketched.id"
            :name="sketched.name"
            :role="sketched.id === analysis.naiveId.value ? 'Naive architecture' : 'Adaptation'"
            :stack="stackLine(sketched.id, candidates.all.value)"
            :done-label="sketched.id === analysis.naiveId.value ? 'Done sketching · on to Stressors' : 'Done sketching'"
            :changed="diffMarks(candidates.comparison.value)"
            @recorded="recorded"
            @done="doneSketching"
          >
            <template
              v-if="introducing && sketched.id === analysis.naiveId.value"
              #intro
            >
              <NaiveIntroNote @dismiss="introducing = false" />
            </template>
          </CandidateCanvas>
          <MarkedCanvas
            v-else
            :diagram-id="analysis.drawnOn.value"
            :drawing="canvas.drawing.value"
            :marks="canvas.marks.value"
            :hint="canvas.hint.value"
            :empty-text="canvas.emptyText.value"
            @pick="canvas.pick"
          />
          <p
            v-if="canvas.readsCandidate.value"
            class="legend"
          >
            + added · ~ changed — a field differs · − removed, drawn as a faded dashed ghost · select a row
            to frame it here, or an element to find its rows
          </p>
        </section>
      </template>
    </DiagramSplitLayout>
  </div>
</template>

<style scoped>
.page { padding: 16px 24px; }
.page-hdr { display: flex; gap: 14px; align-items: center; }
.page-hdr h1 { flex: 1; font-size: 20px; margin: 0; }
.back { color: var(--muted); text-decoration: none; font-size: 13px; }
.err { color: var(--danger-strong); font-size: 12.5px; }
.left, .pane { min-width: 0; }
/* The picture stays in view while the test set below the tables is walked. */
.ws section[aria-label="Canvas"] { position: sticky; top: 8px; min-width: 0; }
.legend { font-size: 11.5px; color: var(--text-2); margin: 4px 2px; }
</style>
<style src="../components/candidates/workbench.css"></style>
