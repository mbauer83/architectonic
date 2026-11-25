<script setup lang="ts">
/**
 * Starting a stress analysis (06·0; owner decisions of 2026-11-25): an analysis evaluates a proposed
 * architecture. One step names it — the architecture under evaluation, the naive candidate, from the
 * current model within a scope, from an existing candidate, or empty — while the canvas previews it.
 * A name (by default the architecture's, numbered where another analysis has it) and an optional context
 * are all the document asks.
 * *Start the naive architecture* creates the naive as a draft candidate and the analysis document naming
 * it, in one write the server makes whole or not at all, then opens the naive for sketching.
 */
import { computed, inject, onMounted, ref, shallowRef, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Effect } from 'effect'
import type { DiagramSummary, ViewpointDefinitionEnvelope } from '../../domain'
import type { CandidateSummary } from '../../domain/schemas/candidates'
import type { LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import { touchingScope } from '../../domain/candidates/touchingScope'
import { modelServiceKey } from '../keys'
import { formatEffectError } from '../lib/errors'
import { candidateDetailRoute, stressAnalysisWorkspaceRoute } from '../router/artifactRoutes'
import { LARGE_SCOPE, useAnalysisScope } from '../composables/useAnalysisScope'
import { useFreeDocumentTitle } from '../composables/useFreeDocumentTitle'
import { STRESS_ANALYSIS_DOC_TYPE } from '../lib/documentListLinks'
import MarkedCanvas from '../components/candidates/MarkedCanvas.vue'
import StressStartArchitecture from '../components/stressWorkspace/StressStartArchitecture.vue'
import type { Marks } from '../../domain/candidates/canvasMarks'
import { framedMarks } from '../../domain/candidates/canvasMarks'

type Origin = 'model' | 'existing' | 'empty'

const svc = inject(modelServiceKey)!
const router = useRouter()
const diagrams = shallowRef<readonly DiagramSummary[]>([])
const viewpoints = shallowRef<readonly ViewpointDefinitionEnvelope[]>([])
const candidates = shallowRef<readonly CandidateSummary[]>([])
const scope = useAnalysisScope(svc, { diagrams: () => diagrams.value, viewpoints: () => viewpoints.value })

const context = ref('')
const origin = ref<Origin>('model')
const fromCandidate = ref('')
const naiveName = ref('Naive architecture')
const starting = ref(false)
const error = ref<string | null>(null)

/** What the analysis evaluates, in words: the scope's source, the candidate it stacks on, or the naive. */
const evaluated = computed((): string => ({
  model: scope.subject.value,
  existing: candidates.value.find((one) => one.id === fromCandidate.value)?.name ?? '',
  empty: naiveName.value.trim(),
})[origin.value])
/** The name the architecture under evaluation proposes, made free of another analysis's name by the server. */
const defaultTitle = useFreeDocumentTitle(svc, STRESS_ANALYSIS_DOC_TYPE,
  () => (evaluated.value ? `Stress analysis — ${evaluated.value}` : ''))
/** The name typed, or none yet: until one is typed, the name follows the architecture under evaluation. */
const typedTitle = ref<string | null>(null)
const title = computed({
  get: () => typedTitle.value ?? defaultTitle.value,
  set: (typed: string) => { typedTitle.value = typed },
})

/** The candidate the naive stacks on, drawn as its own page draws it. */
const stackedOn = shallowRef<LayoutGeometry | null>(null)
watch(fromCandidate, async (id) => {
  stackedOn.value = null
  if (!id) return
  const read = await Effect.runPromise(svc.compareCandidate(id, 'model')).catch(() => null)
  if (fromCandidate.value === id) stackedOn.value = read?.drawing ?? null
})

const fromModel = computed(() => origin.value === 'model')
const marks = computed((): Marks => (fromModel.value ? framedMarks(scope.pressed.value, 'In the scope') : new Map()))
const drawing = computed(() => ({ model: scope.drawing.value, existing: stackedOn.value, empty: null })[origin.value])
const touching = computed(() => (fromModel.value ? touchingScope(scope.ids.value, candidates.value) : []))
const canStart = computed(() => title.value.trim() !== '' && naiveName.value.trim() !== '' && !starting.value
  && (origin.value !== 'existing' || fromCandidate.value !== '')
  && (origin.value !== 'model' || scope.ids.value.length > 0))

/** The naive architecture's record: its scope and the diagram it is drawn on, what it stacks on, or neither. */
const naiveRecord = (): Record<string, unknown> => ({
  name: naiveName.value.trim(),
  ...(fromModel.value ? { scope: [...scope.ids.value] } : {}),
  ...(fromModel.value && scope.drawnOn.value ? { diagram: scope.drawnOn.value } : {}),
  ...(origin.value === 'existing' ? { parent: fromCandidate.value } : {}),
})

const start = async () => {
  starting.value = true
  error.value = null
  try {
    const started = await Effect.runPromise(svc.startAnalysis({
      title: title.value.trim(), naive: naiveRecord(),
      ...(context.value.trim() ? { context: context.value.trim() } : {}),
    }))
    await router.push({
      path: stressAnalysisWorkspaceRoute(started.document), query: { tab: 'naive', sketch: 'naive' },
    })
  } catch (failure) {
    error.value = formatEffectError(failure)
  } finally {
    starting.value = false
  }
}

const hint = computed(() => {
  if (!fromModel.value) return 'The architecture the naive candidate stacks on'
  if (!scope.drawnOn.value) return 'A view generated from the scope: no stored diagram draws it'
  return scope.source.value === 'diagram' && !scope.wholeDiagram.value
    ? 'Press elements to put them in the scope'
    : 'The scope · what is outside it steps back'
})

onMounted(async () => {
  const [listed, defined, open] = await Promise.all([
    Effect.runPromise(svc.listDiagrams()).catch(() => null),
    Effect.runPromise(svc.listViewpointDefinitions()).catch(() => []),
    Effect.runPromise(svc.listCandidates()).catch(() => []),
  ])
  diagrams.value = (listed?.items ?? []).filter((one) => one.diagram_type.startsWith('archimate'))
  viewpoints.value = defined
  candidates.value = open
})
</script>

<template>
  <div class="workbench page">
    <div class="page-hdr">
      <RouterLink
        class="back"
        to="/documents"
      >
        ← Documents
      </RouterLink>
      <h1>New stress analysis</h1>
    </div>
    <div class="ws">
      <section
        class="pane card start"
        aria-label="Start a stress analysis"
      >
        <h2>Start a stress analysis</h2>
        <p class="lead">
          A stress analysis evaluates a proposed architecture. Nothing is created until you press
          <i>Start the naive architecture</i>.
        </p>
        <label class="fld">Name <input
          v-model="title"
          data-testid="analysis-name"
          placeholder="Stress analysis — the architecture under evaluation"
        ></label>
        <label class="fld">Context <small class="optional">optional</small>
          <textarea
            v-model="context"
            data-testid="analysis-context"
            rows="2"
            placeholder="The environment the architecture is evaluated in, and the decision the evaluation informs"
          /></label>
        <StressStartArchitecture
          v-model:origin="origin"
          v-model:from-candidate="fromCandidate"
          v-model:naive-name="naiveName"
          :scope="scope"
          :diagrams="diagrams"
          :viewpoints="viewpoints"
          :candidates="candidates"
        />
        <section
          v-if="touching.length"
          class="touching"
          data-testid="touching-candidates"
          aria-label="Open candidates touching the scope"
        >
          <h3>Open candidate architectures touching this scope</h3>
          <ul>
            <li
              v-for="one in touching"
              :key="one.candidate.id"
            >
              <RouterLink :to="candidateDetailRoute(one.candidate.id)">
                {{ one.candidate.name }}
              </RouterLink>
              <small>{{ one.candidate.state }} · reads {{ one.shared }} of these elements</small>
            </li>
          </ul>
        </section>
        <p
          v-if="fromModel"
          class="scope-sum"
          data-testid="scope-count"
        >
          <b>{{ scope.ids.value.length }} elements</b> in scope
          <span
            v-if="scope.ids.value.length > LARGE_SCOPE"
            class="warnline"
          >A scope above {{ LARGE_SCOPE }} elements is large: stressors will be hard to walk.</span>
        </p>
        <p
          v-if="error ?? scope.error.value"
          class="err"
          role="alert"
        >
          {{ error ?? scope.error.value }}
        </p>
        <button
          type="button"
          class="btn btn-primary"
          data-testid="start-naive"
          :disabled="!canStart"
          @click="start"
        >
          Start the naive architecture
        </button>
      </section>
      <section aria-label="Canvas">
        <MarkedCanvas
          :diagram-id="fromModel ? scope.drawnOn.value : ''"
          :drawing="drawing"
          :marks="marks"
          :dimmed="fromModel ? scope.outside.value : undefined"
          :hint="hint"
          :empty-text="origin === 'empty'
            ? 'Empty: a blank canvas, no elements and no boxes.'
            : scope.drawingBusy.value ? 'Drawing the scope…' : 'Choose a scope to see it here.'"
          @pick="scope.press"
        />
      </section>
    </div>
  </div>
</template>

<style scoped>
.page { padding: 16px 24px; }
.page-hdr { display: flex; gap: 14px; align-items: center; margin-bottom: 10px; }
.page-hdr h1 { font-size: 20px; margin: 0; }
.back { color: var(--muted); text-decoration: none; font-size: 13px; }
.ws { display: grid; grid-template-columns: minmax(440px, 46%) minmax(0, 1fr); gap: 12px; align-items: start; }
@media (max-width: 1100px) { .ws { grid-template-columns: minmax(0, 1fr); } }
.start { padding: 12px 14px; font-size: 12.5px; }
.start h2 { font-size: 15px; margin: 0 0 2px; }
.lead { color: var(--text-2); margin: 0 0 10px; }
.fld {
  display: block;
  margin: 6px 0;
  font-size: 11px;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 600;
}
.fld input, .fld textarea {
  display: block;
  width: 100%;
  margin-top: 3px;
  font: inherit;
  font-size: 13px;
  font-weight: 400;
  text-transform: none;
}
.fld textarea { resize: vertical; }
.optional { font-weight: 400; text-transform: none; }
.touching { border: 1px solid var(--border); border-radius: 6px; padding: 6px 9px; margin: 8px 0 0; }
.touching h3 { font-size: 12px; margin: 0 0 4px; }
.touching ul { margin: 0; padding-left: 16px; }
.touching small { color: var(--muted); margin-left: 6px; }
.scope-sum { background: var(--soft); border-radius: 6px; padding: 6px 8px; margin: 8px 0; }
.err { color: var(--danger-strong); }
</style>
<style src="../components/candidates/workbench.css"></style>
