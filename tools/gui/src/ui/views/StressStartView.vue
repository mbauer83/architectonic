<script setup lang="ts">
/**
 * Starting a stress analysis (06·0; owner decisions of 2026-11-25): an analysis evaluates its naive
 * architecture, and the naive architecture is defined on a canvas, not chosen here. So the start asks only
 * what the document needs — a name (by default the architecture's, numbered where another analysis has it),
 * an optional context, and what the architecture under evaluation is called.
 *
 * *Start and sketch the naive architecture* creates the naive as an empty draft candidate and the analysis
 * document naming it, in one write the server makes whole or not at all, then opens it on its canvas: there
 * the author puts the model's elements on it, creates new ones and records changes — every one of them a
 * candidate operation, none reaching the model before Apply. A diagram or an existing candidate to start from
 * is offered on the canvas itself.
 */
import { computed, inject, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import { formatEffectError } from '../lib/errors'
import { stressAnalysisWorkspaceRoute } from '../router/artifactRoutes'
import { useFreeDocumentTitle } from '../composables/useFreeDocumentTitle'
import { STRESS_ANALYSIS_DOC_TYPE } from '../lib/documentListLinks'
import PermittedButton from '../components/PermittedButton.vue'

const svc = inject(modelServiceKey)!
const router = useRouter()

const context = ref('')
const naiveName = ref('Naive architecture')
const starting = ref(false)
const error = ref<string | null>(null)

/** The name the architecture under evaluation proposes, made free of another analysis's name by the server. */
const defaultTitle = useFreeDocumentTitle(svc, STRESS_ANALYSIS_DOC_TYPE,
  () => (naiveName.value.trim() ? `Stress analysis — ${naiveName.value.trim()}` : ''))
/** The name typed, or none yet: until one is typed, the name follows the architecture under evaluation. */
const typedTitle = ref<string | null>(null)
const title = computed({
  get: () => typedTitle.value ?? defaultTitle.value,
  set: (typed: string) => { typedTitle.value = typed },
})
const canStart = computed(() => title.value.trim() !== '' && naiveName.value.trim() !== '' && !starting.value)

const start = async () => {
  starting.value = true
  error.value = null
  try {
    const started = await Effect.runPromise(svc.startAnalysis({
      title: title.value.trim(), naive: { name: naiveName.value.trim() },
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
    <section
      class="card start"
      aria-label="Start a stress analysis"
    >
      <h2>Start a stress analysis</h2>
      <p class="lead">
        A stress analysis evaluates an architecture: its naive architecture, which you define next on a
        canvas — by placing elements of the model, creating new ones and recording changes. Nothing reaches the
        model before you apply it.
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
      <label class="fld">The architecture under evaluation <input
        v-model="naiveName"
        data-testid="naive-name"
        placeholder="Naive architecture"
      ></label>
      <p
        v-if="error"
        class="err"
        role="alert"
      >
        {{ error }}
      </p>
      <PermittedButton
        operation="documents_start_stress_analysis"
        class="btn btn-primary"
        data-testid="start-naive"
        :disabled="!canStart"
        @click="start"
      >
        Start and sketch the naive architecture
      </PermittedButton>
    </section>
  </div>
</template>

<style scoped>
.page { padding: 16px 24px; }
.page-hdr { display: flex; gap: 14px; align-items: center; margin-bottom: 10px; }
.page-hdr h1 { font-size: 20px; margin: 0; }
.back { color: var(--muted); text-decoration: none; font-size: 13px; }
.start { padding: 12px 14px; font-size: 12.5px; max-width: 640px; }
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
.err { color: var(--danger-strong); }
</style>
<style src="../components/candidates/workbench.css"></style>
