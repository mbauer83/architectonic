<script setup lang="ts">
/**
 * One candidate architecture, read on its own: its operations against the base chosen in *against*
 * (by default what it stacks on), the "model moved" band when the model moved under them, and the
 * candidate drawn on a diagram the reader chooses — marked with what it changes, or sketched with the
 * diagram editor. The same components a stress analysis reads its candidates with; nothing here knows
 * of analyses. A candidate is drawn on the diagram its stack names, else on a view generated from its
 * scope; another can be chosen (`?diagram=`), which is presentation: a candidate records operations on
 * the model, not on any one picture of it. *Compare with…* opens a comparison holding this candidate,
 * on the same diagram, for others to be added to.
 */
import { computed, inject, onMounted, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Effect } from 'effect'
import type { DiagramSummary } from '../../domain'
import { stableEntityId } from '../../domain/artifactId'
import type { Marks } from '../../domain/candidates/canvasMarks'
import { diffMarks, framedMarks } from '../../domain/candidates/canvasMarks'
import { modelServiceKey, toastKey } from '../keys'
import { candidateCompareRoute, candidateDetailRoute, candidateListRoute } from '../router/artifactRoutes'
import { useCandidates } from '../composables/useCandidates'
import { useComposedDrawing } from '../composables/useComposedDrawing'
import { useCandidateApply } from '../composables/useCandidateApply'
import ApplyCandidate from '../components/candidates/ApplyCandidate.vue'
import CandidateResiduality from '../components/candidates/CandidateResiduality.vue'
import CandidateOperations from '../components/candidates/CandidateOperations.vue'
import CandidateCanvas from '../components/candidates/CandidateCanvas.vue'
import MarkedCanvas from '../components/candidates/MarkedCanvas.vue'
import ModelMovedBanner from '../components/candidates/ModelMovedBanner.vue'

const svc = inject(modelServiceKey)!
const toast = inject(toastKey, () => undefined)
const route = useRoute()
const router = useRouter()
const candidateId = computed(() => String(route.params.artifactId))
/** The diagram the reader chose to draw on instead of the one the candidate names; empty for that one. */
const chosenDiagram = computed(() => (typeof route.query.diagram === 'string' ? route.query.diagram : ''))
const candidates = useCandidates(svc, { scopeDiagram: () => chosenDiagram.value })
/** The picture with the candidate drawn as it composes, as its sketch draws it. */
const drawing = useComposedDrawing(svc, () => candidates.comparison.value)
/** The stored diagram the candidate is drawn on; empty where it is drawn as a generated view, or not at all. */
const diagramId = computed(() => chosenDiagram.value || candidates.comparison.value?.drawing?.artifact_id || '')

const diagrams = shallowRef<readonly DiagramSummary[]>([])
const summary = computed(() => candidates.all.value.find((one) => one.id === candidateId.value) ?? null)
const loaded = ref(false)
const drawOn = (id: string) => {
  void router.replace({ query: id ? { diagram: id } : {} })
}

/** The element a row of the operations table is about, framed on the picture. */
const framed = ref<string | null>(null)
const marks = computed((): Marks => new Map([
  ...diffMarks(candidates.comparison.value?.diff ?? []),
  ...(framed.value ? framedMarks([framed.value], 'The row selected on the left') : new Map()),
]))
/** A name the comparison does not give: the id as it is. */
const nameOf = (id: string): string => id

const sketching = ref(false)
const sketch = () => {
  sketching.value = diagramId.value !== ''
}
const recorded = async () => {
  await candidates.compareWith(candidates.against.value)
}
const doneSketching = async () => {
  sketching.value = false
  await recorded()
}

const rebasing = ref(false)
const rebase = async () => {
  rebasing.value = true
  if (await candidates.rebase(candidateId.value)) {
    toast(`Re-based ${summary.value?.name ?? candidateId.value} on the model as it stands now.`)
  }
  rebasing.value = false
}

const apply = useCandidateApply(svc, () => { void applied() })
const applicable = computed(() => summary.value?.state === 'draft' || summary.value?.state === 'candidate')
const applied = async () => {
  toast(`Applied ${summary.value?.name ?? candidateId.value} to the model; it is integrated.`)
  await candidates.load()
  await candidates.compareWith(candidates.against.value)
}

const stacking = ref(false)
const stackName = ref('')
const stackOn = async () => {
  const id = await candidates.stackOn(candidateId.value, stackName.value.trim())
  if (!id) return
  stacking.value = false
  stackName.value = ''
  await router.push({ path: candidateDetailRoute(id), query: route.query })
}

const remove = async () => {
  const label = summary.value?.name ?? candidateId.value
  if (!window.confirm(`Delete the candidate architecture ${label}? Its operations are lost.`)) return
  if (await candidates.remove(candidateId.value)) {
    toast(`Deleted ${label}.`)
    await router.push(candidateListRoute())
  }
}

const read = async () => {
  sketching.value = false
  framed.value = null
  apply.close()
  await candidates.select(candidateId.value)
}
watch(candidateId, read)
watch(chosenDiagram, async () => {
  sketching.value = false
  await candidates.compareWith(candidates.against.value)
})
onMounted(async () => {
  const [listed] = await Promise.all([
    Effect.runPromise(svc.listDiagrams()).catch(() => null),
    candidates.load(),
  ])
  diagrams.value = (listed?.items ?? []).filter((one) => one.diagram_type.startsWith('archimate'))
  await read()
  loaded.value = true
})
</script>

<template>
  <div class="workbench page">
    <div class="page-hdr">
      <RouterLink
        class="back"
        :to="candidateListRoute()"
      >
        ← Candidate architectures
      </RouterLink>
      <h1>{{ summary?.name ?? candidateId }}</h1>
      <button
        v-if="summary && !stacking"
        type="button"
        class="btn btn-sm"
        data-testid="stack-candidate"
        @click="stacking = true"
      >
        New candidate on top…
      </button>
      <RouterLink
        v-if="summary"
        class="btn btn-sm"
        data-testid="compare-with"
        :to="candidateCompareRoute([candidateId], diagramId)"
      >
        Compare with…
      </RouterLink>
      <button
        v-if="summary && applicable"
        type="button"
        class="btn btn-sm"
        data-testid="apply-to-model"
        :disabled="apply.busy.value"
        @click="apply.open(candidateId)"
      >
        Apply to the model…
      </button>
      <button
        v-if="summary"
        type="button"
        class="btn btn-sm"
        data-testid="delete-candidate"
        @click="remove"
      >
        Delete
      </button>
    </div>
    <form
      v-if="stacking"
      class="stack-form"
      @submit.prevent="stackOn"
    >
      <label>Name <input
        v-model="stackName"
        required
        autofocus
      ></label>
      <button
        type="submit"
        class="btn btn-sm btn-primary"
        :disabled="!stackName.trim()"
      >
        Stack on {{ summary?.name }}
      </button>
      <button
        type="button"
        class="btn btn-sm"
        @click="stacking = false"
      >
        Cancel
      </button>
    </form>
    <div class="meta">
      <span class="badge">candidate architecture</span>
      <label>Drawn on
        <select
          :value="diagramId"
          data-testid="draw-on"
          @change="drawOn(($event.target as HTMLSelectElement).value)"
        >
          <option value="">a view generated from its scope</option>
          <option
            v-for="one in diagrams"
            :key="one.artifact_id"
            :value="one.artifact_id"
          >{{ one.name }}</option>
        </select>
      </label>
    </div>
    <CandidateResiduality
      v-if="summary"
      :candidate-id="summary.id"
    />
    <p
      v-if="loaded && !summary"
      class="err"
      role="alert"
    >
      No candidate architecture {{ candidateId }}.
    </p>
    <p
      v-else-if="candidates.error.value && !candidates.comparison.value"
      class="err"
      role="alert"
    >
      {{ candidates.error.value }}
    </p>
    <ApplyCandidate
      v-if="summary && apply.preview.value?.candidate === summary.id"
      :apply="apply"
      :name="summary.name"
    />
    <p
      v-else-if="apply.error.value"
      class="err"
      role="alert"
    >
      {{ apply.error.value }}
    </p>
    <ModelMovedBanner
      v-if="summary && candidates.comparison.value?.candidate === summary.id"
      :name="summary.name"
      :standing="candidates.comparison.value.standing"
      :busy="rebasing"
      @rebase="rebase"
    />
    <div
      v-if="summary"
      class="ws"
    >
      <section
        class="pane card"
        aria-label="Operations"
      >
        <CandidateOperations
          :candidates="candidates"
          role="candidate architecture"
          :name-of="nameOf"
          :framed="framed"
          @frame="framed = $event && stableEntityId($event)"
          @sketch="sketch"
        />
        <p
          v-if="!diagramId && summary.state === 'draft'"
          class="hint"
        >
          Choose a diagram to draw this candidate on, and to sketch it there.
        </p>
      </section>
      <section aria-label="Canvas">
        <CandidateCanvas
          v-if="sketching && diagramId"
          :key="`${summary.id} ${diagramId}`"
          :candidate-id="summary.id"
          :name="summary.name"
          role="Candidate architecture"
          :diagram-id="diagramId"
          :changed="diffMarks(candidates.comparison.value?.diff ?? [])"
          @recorded="recorded"
          @done="doneSketching"
        />
        <MarkedCanvas
          v-else
          :diagram-id="diagramId"
          :drawing="drawing"
          :marks="marks"
          hint="Select a row to frame its element, or an element to find its rows · Scroll to zoom · Drag to pan"
          empty-text="No diagram to draw: choose one above."
          @pick="framed = framed === $event ? null : $event"
        />
        <p class="legend">
          + added · ~ changed — a field differs · − removed, drawn as a faded dashed ghost
        </p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.page { padding: 16px 24px; }
.page-hdr { display: flex; gap: 10px; align-items: center; }
.page-hdr h1 { flex: 1; font-size: 20px; margin: 0; }
.back { color: var(--muted); text-decoration: none; font-size: 13px; }
.page-hdr a.btn { text-decoration: none; }
.meta { display: flex; gap: 10px; align-items: center; margin: 8px 0 8px; font-size: 12px; color: var(--muted); }
.meta select { font: inherit; margin-left: 4px; max-width: 320px; }
.badge { background: var(--accent-soft); color: var(--accent-strong); border-radius: 3px; padding: 2px 8px; }
.stack-form { display: flex; gap: 8px; align-items: center; margin: 8px 0; font-size: 12.5px; }
.stack-form input { font: inherit; margin-left: 4px; }
.err { color: var(--danger-strong); font-size: 12.5px; }
.hint { color: var(--muted); font-size: 12px; padding: 6px 10px; margin: 0; }
.ws { display: grid; grid-template-columns: minmax(440px, 46%) minmax(0, 1fr); gap: 12px; align-items: start; }
.pane { min-width: 0; }
.legend { font-size: 11.5px; color: var(--text-2); margin: 4px 2px; }
@media (max-width: 1100px) { .ws { grid-template-columns: minmax(0, 1fr); } }
</style>
<style src="../components/candidates/workbench.css"></style>
