<script setup lang="ts">
/**
 * Starting a stress analysis (06·0): a name and a question, then two steps — the scope, and the naive
 * architecture, the first candidate architecture — while the canvas previews the scope. *Start the
 * naive architecture* creates the naive as a draft candidate and the analysis document naming it, then
 * opens the workspace on the naive architecture.
 *
 * Two writes, the candidate first: when the document is refused, the candidate it would have named
 * is said by id rather than left unmentioned.
 */
import { computed, inject, onMounted, ref, shallowRef } from 'vue'
import { useRouter } from 'vue-router'
import { Effect } from 'effect'
import type { DiagramSummary, ViewpointDefinitionEnvelope } from '../../domain'
import type { CandidateSummary } from '../../domain/schemas/candidates'
import { modelServiceKey } from '../keys'
import { formatEffectError } from '../lib/errors'
import { stressAnalysisWorkspaceRoute } from '../router/artifactRoutes'
import { LARGE_SCOPE, useAnalysisScope } from '../composables/useAnalysisScope'
import WorkspaceCanvas from '../components/stressWorkspace/WorkspaceCanvas.vue'
import type { Marks } from '../../domain/stressAnalysis/workspaceMarks'
import { framedMarks } from '../../domain/stressAnalysis/workspaceMarks'

type Origin = 'model' | 'existing' | 'empty'

const svc = inject(modelServiceKey)!
const router = useRouter()
const scope = useAnalysisScope(svc)

const title = ref('')
const question = ref('')
const origin = ref<Origin>('model')
const fromCandidate = ref('')
const naiveName = ref('Naive architecture')
const diagrams = shallowRef<readonly DiagramSummary[]>([])
const viewpoints = shallowRef<readonly ViewpointDefinitionEnvelope[]>([])
const candidates = shallowRef<readonly CandidateSummary[]>([])
const starting = ref(false)
const error = ref<string | null>(null)

const marks = computed((): Marks => framedMarks(scope.pressed.value, 'In the scope'))
const canStart = computed(() => title.value.trim() !== '' && naiveName.value.trim() !== ''
  && (origin.value !== 'existing' || fromCandidate.value !== '') && !starting.value)

/** The naive architecture's record: its scope (none when empty), and what it stacks on. */
const naiveRecord = (): Record<string, unknown> => ({
  name: naiveName.value.trim(),
  ...(origin.value === 'empty' ? {} : { scope: [...scope.ids.value] }),
  ...(origin.value === 'existing' ? { parent: fromCandidate.value } : {}),
})

const start = async () => {
  starting.value = true
  error.value = null
  let naive: string | null = null
  try {
    const created = await Effect.runPromise(svc.createCandidate(naiveRecord()))
    naive = String(created.record.id)
    const diagram = origin.value === 'empty' ? '' : scope.diagramId.value
    const written = await Effect.runPromise(svc.createDocument({
      doc_type: 'stress-analysis', title: title.value.trim(), dry_run: false,
      extra_frontmatter: {
        'naive-candidate': naive,
        ...(question.value.trim() ? { question: question.value.trim() } : {}),
        ...(diagram ? { 'scope-diagram': diagram } : {}),
      },
    }))
    await router.push({ path: stressAnalysisWorkspaceRoute(written.artifact_id), query: { tab: 'naive' } })
  } catch (failure) {
    error.value = naive
      ? `The naive architecture ${naive} was created, but the analysis document was not: ${formatEffectError(failure)}`
      : formatEffectError(failure)
  } finally {
    starting.value = false
  }
}

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
  <div class="stress-ws page">
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
          Two steps, in any order. Nothing is created until you press <i>Start the naive architecture</i>.
        </p>
        <label class="fld">Name <input
          v-model="title"
          data-testid="analysis-name"
          placeholder="Stress analysis — …"
        ></label>
        <label class="fld">Question <input
          v-model="question"
          placeholder="Does … hold when …?"
        ></label>
        <div class="step">
          <h3><span class="num">1</span> Scope — what the analysis looks at</h3>
          <div
            class="seg"
            role="tablist"
          >
            <button
              v-for="one in (['diagram', 'viewpoint', 'search'] as const)"
              :key="one"
              type="button"
              role="tab"
              class="tab"
              :aria-selected="scope.source.value === one"
              @click="scope.source.value = one"
            >
              {{ { diagram: 'Diagram selection', viewpoint: 'Viewpoint', search: 'Search' }[one] }}
            </button>
          </div>
          <label class="fld">Diagram
            <select
              v-model="scope.diagramId.value"
              data-testid="scope-diagram"
            >
              <option value="">no diagram</option>
              <option
                v-for="one in diagrams"
                :key="one.artifact_id"
                :value="one.artifact_id"
              >{{ one.name }}</option>
            </select>
          </label>
          <div
            v-if="scope.source.value === 'diagram'"
            class="row"
          >
            <label><input
              v-model="scope.wholeDiagram.value"
              type="radio"
              :value="true"
            > the whole diagram</label>
            <label><input
              v-model="scope.wholeDiagram.value"
              type="radio"
              :value="false"
            > only the elements I press on the canvas</label>
          </div>
          <label
            v-else-if="scope.source.value === 'viewpoint'"
            class="fld"
          >Viewpoint
            <select @change="scope.runViewpoint(($event.target as HTMLSelectElement).value)">
              <option value="">choose…</option>
              <option
                v-for="one in viewpoints"
                :key="one.slug"
                :value="one.slug"
              >{{ one.name }}</option>
            </select>
          </label>
          <form
            v-else
            class="row"
            @submit.prevent="scope.search"
          >
            <input
              v-model="scope.query.value"
              placeholder="Search the model"
              aria-label="Search the model"
            >
            <button
              type="submit"
              class="btn btn-sm"
            >
              Search
            </button>
            <div class="search-hits">
              <label
                v-for="hit in scope.hits.value"
                :key="hit.artifact_id"
              ><input
                type="checkbox"
                :checked="scope.ticked.value.has(hit.artifact_id)"
                @change="scope.tick(hit.artifact_id)"
              > {{ hit.name }} <small>{{ hit.artifact_type }}</small></label>
            </div>
          </form>
          <p
            class="scope-sum"
            data-testid="scope-count"
          >
            <b>{{ scope.ids.value.length }} elements</b> in scope
            <span
              v-if="scope.ids.value.length > LARGE_SCOPE"
              class="warnline"
            >A scope above {{ LARGE_SCOPE }} elements is large: stressors will be hard to walk.</span>
          </p>
        </div>
        <div class="step">
          <h3><span class="num">2</span> The naive architecture — the first candidate</h3>
          <p class="lead">
            The architecture as it stands before any stressor. It is a <b>candidate architecture</b> of its
            own: every adaptation stacks on it, and nothing in it reaches the model before Commit.
          </p>
          <label class="origin"><input
            v-model="origin"
            type="radio"
            value="model"
          ><span><b>From the current model, within the scope</b> <small>recommended</small>
            <small>
              Read live from the model; it starts with no operations, and what you change becomes them.
            </small></span></label>
          <label class="origin"><input
            v-model="origin"
            type="radio"
            value="existing"
          ><span><b>From an existing candidate architecture</b>
            <small>Stacks on it: its operations are read first and stay its own.</small>
            <select
              v-if="origin === 'existing'"
              v-model="fromCandidate"
            ><option value="">choose…</option><option
              v-for="one in candidates"
              :key="one.id"
              :value="one.id"
            >{{ one.name }} ({{ one.state }})</option></select></span></label>
          <label class="origin"><input
            v-model="origin"
            type="radio"
            value="empty"
          ><span><b>Empty</b> <small>A blank canvas: no elements, no boxes.</small></span></label>
          <label class="fld">Its name <input v-model="naiveName"></label>
        </div>
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
        <WorkspaceCanvas
          :diagram-id="scope.diagramId.value"
          :drawing="origin === 'empty' ? null : scope.drawing.value"
          :marks="marks"
          :dimmed="scope.outside.value"
          :hint="scope.wholeDiagram.value
            ? 'The scope · what is outside it steps back'
            : 'Press elements to put them in the scope'"
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
.fld input, .fld select {
  display: block;
  width: 100%;
  margin-top: 3px;
  font: inherit;
  font-size: 13px;
  text-transform: none;
  padding: 5px 8px;
}
.step { border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; margin: 10px 0; }
.step h3 { font-size: 13px; margin: 0 0 6px; display: flex; gap: 8px; align-items: center; }
.num {
  display: inline-grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  font-size: 11px;
}
.seg { display: inline-flex; border: 1px solid var(--border); border-radius: 6px; margin-bottom: 4px; }
.seg .tab { flex: none; padding: 4px 10px; }
.row { display: flex; gap: 8px 14px; align-items: center; flex-wrap: wrap; margin: 6px 0; }
.scope-sum { background: var(--soft); border-radius: 6px; padding: 6px 8px; margin: 8px 0 0; }
.search-hits {
  flex-basis: 100%;
  max-height: 140px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 4px;
}
.search-hits label { display: flex; gap: 6px; padding: 2px 6px; }
.search-hits small { color: var(--muted); }
.origin {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 7px 9px;
  margin-top: 6px;
  cursor: pointer;
}
.origin:has(input:checked) {
  border-color: var(--accent);
  background: var(--accent-soft);
  box-shadow: inset 3px 0 0 var(--accent);
}
.origin small { display: block; color: var(--muted); font-size: 11.5px; }
.origin select { margin-top: 4px; font-size: 12px; }
.err { color: #b91c1c; }
</style>
<style src="../components/stressWorkspace/workspace.css"></style>
