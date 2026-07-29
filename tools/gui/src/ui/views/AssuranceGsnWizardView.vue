<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import DOMPurify from 'dompurify'
import AssuranceAnalysisPicker from '../components/AssuranceAnalysisPicker.vue'
import {
  GSN_STEPS,
  completenessFailures,
  publicationBody,
  sourceBindings,
  type CompletenessResponse,
  type GsnDraftResponse,
} from './AssuranceGsnWizard.helpers'

const route = useRoute()
const router = useRouter()
const analysisId = ref<string | null>(
  typeof route.query['analysis_id'] === 'string' ? route.query['analysis_id'] : null,
)
const stepKey = ref('draft')
const draft = ref<GsnDraftResponse | null>(null)
const svg = ref<string | null>(null)
const completeness = ref<CompletenessResponse | null>(null)
const publishedDiagramId = ref<string | null>(null)
const guidance = ref<Record<string, string>>({})
const busy = ref(false)
const error = ref<string | null>(null)

const sanitizedSvg = computed(() =>
  svg.value
    ? DOMPurify.sanitize(svg.value, { USE_PROFILES: { svg: true, svgFilters: true } })
    : null,
)
const failures = computed(() => completenessFailures(completeness.value))
const bindings = computed(() => draft.value ? sourceBindings(draft.value.diagram_entities) : [])

async function requestJson(url: string, init?: RequestInit) {
  const response = await fetch(url, init)
  const body = await response.json().catch(() => ({})) as Record<string, unknown>
  if (!response.ok) throw new Error(typeof body['error'] === 'string' ? body['error'] : `HTTP ${response.status}`)
  return body
}

async function loadGuidance() {
  const topic = stepKey.value === 'completeness' ? 'assurance-case-completeness' : 'assurance-case-gsn'
  guidance.value = await requestJson(`/api/assurance/guidance?topic=${topic}`) as Record<string, string>
}

async function buildDraft() {
  if (!analysisId.value) return
  busy.value = true
  error.value = null
  try {
    draft.value = await requestJson(
      `/api/assurance/gsn/draft?analysis_id=${encodeURIComponent(analysisId.value)}`,
    ) as unknown as GsnDraftResponse
    stepKey.value = 'destination'
  } catch (reason) {
    error.value = String(reason)
  } finally {
    busy.value = false
  }
}

async function loadPreview() {
  if (!analysisId.value) return
  busy.value = true
  error.value = null
  try {
    const body = await requestJson(
      `/api/assurance/gsn/rendered?analysis_id=${encodeURIComponent(analysisId.value)}`,
    )
    svg.value = typeof body['svg'] === 'string' ? body['svg'] : null
    draft.value = body as unknown as GsnDraftResponse
    stepKey.value = 'preview'
  } catch (reason) {
    error.value = String(reason)
  } finally {
    busy.value = false
  }
}

async function publish() {
  if (!analysisId.value || !draft.value?.publishable) return
  busy.value = true
  error.value = null
  try {
    const created = await requestJson('/api/diagram', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        diagram_type: 'gsn',
        name: `Assurance case — ${analysisId.value}`,
        entity_ids: [],
        connection_ids: [],
        diagram_entities: draft.value.diagram_entities,
        keywords: ['assurance case', 'GSN'],
        tlp: draft.value.effective_tlp,
        status: 'draft',
        dry_run: false,
      }),
    })
    const diagramId = typeof created['artifact_id'] === 'string' ? created['artifact_id'] : ''
    if (!diagramId) throw new Error('Diagram publication returned no artifact id')
    await requestJson('/api/assurance/gsn/publications', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(publicationBody(analysisId.value, diagramId, draft.value.diagram_entities)),
    })
    publishedDiagramId.value = diagramId
    stepKey.value = 'bindings'
  } catch (reason) {
    error.value = String(reason)
  } finally {
    busy.value = false
  }
}

async function checkCompleteness() {
  if (!analysisId.value) return
  busy.value = true
  try {
    completeness.value = await requestJson(
      `/api/assurance/gsn/completeness?analysis_id=${encodeURIComponent(analysisId.value)}`,
    ) as unknown as CompletenessResponse
    stepKey.value = 'completeness'
  } catch (reason) {
    error.value = String(reason)
  } finally {
    busy.value = false
  }
}

watch(analysisId, (value) => {
  draft.value = null
  svg.value = null
  completeness.value = null
  publishedDiagramId.value = null
  stepKey.value = 'draft'
  void router.replace({ path: '/assurance/gsn', query: value ? { analysis_id: value } : {} })
})
watch(stepKey, () => { void loadGuidance() }, { immediate: true })
</script>

<template>
  <div class="wizard">
    <header class="wizard-header">
      <div>
        <h1>Assurance-case / GSN wizard</h1>
        <p>Draft from one analysis, enforce the TLP destination, publish or preview, bind, then check.</p>
      </div>
      <AssuranceAnalysisPicker
        v-model="analysisId"
        default-method="STPA"
      />
    </header>

    <p
      v-if="error"
      class="error"
    >
      {{ error }}
    </p>
    <p
      v-if="!analysisId"
      class="hint"
    >
      Select an analysis to begin.
    </p>

    <template v-else>
      <nav class="steps">
        <button
          v-for="(step, index) in GSN_STEPS"
          :key="step.key"
          type="button"
          :class="{ active: step.key === stepKey }"
          @click="stepKey = step.key"
        >
          {{ index + 1 }}. {{ step.label }}
        </button>
      </nav>

      <section
        v-if="guidance.what"
        class="guidance"
      >
        <strong>{{ guidance.step }}</strong>
        <p>{{ guidance.what }}</p>
      </section>

      <section
        v-if="stepKey === 'draft'"
        class="panel"
      >
        <h2>Generate the argument</h2>
        <p>The draft is derived from losses, hazards, UCA-derived constraints, and evidence in this analysis.</p>
        <button
          type="button"
          :disabled="busy"
          @click="buildDraft"
        >
          Generate GSN draft
        </button>
      </section>

      <section
        v-else-if="stepKey === 'destination'"
        class="panel"
      >
        <h2>Classification-gated destination</h2>
        <p>Effective classification: <strong>{{ draft?.effective_tlp }}</strong></p>
        <p
          v-if="draft?.publishable"
          class="ok"
        >
          Cleared: publication to the architecture repository is permitted.
        </p>
        <p
          v-else
          class="warning"
        >
          Confidential: preview remains store-resident and no repository source is written.
        </p>
        <button
          type="button"
          :disabled="busy"
          @click="loadPreview"
        >
          Render protected preview
        </button>
      </section>

      <section
        v-else-if="stepKey === 'preview'"
        class="panel"
      >
        <h2>{{ draft?.publishable ? 'Preview and publish' : 'Confidential preview' }}</h2>
        <!-- eslint-disable vue/no-v-html -->
        <div
          v-if="sanitizedSvg"
          class="svg"
          v-html="sanitizedSvg"
        />
        <!-- eslint-enable vue/no-v-html -->
        <button
          v-if="draft?.publishable"
          type="button"
          :disabled="busy"
          @click="publish"
        >
          Publish GSN diagram
        </button>
        <button
          type="button"
          :disabled="busy"
          @click="checkCompleteness"
        >
          Check completeness
        </button>
      </section>

      <section
        v-else-if="stepKey === 'bindings'"
        class="panel"
      >
        <h2>Source bindings</h2>
        <p>{{ bindings.length }} assurance-source bindings recorded.</p>
        <RouterLink
          v-if="publishedDiagramId"
          :to="{ path: '/diagram', query: { id: publishedDiagramId } }"
        >
          Open published GSN diagram →
        </RouterLink>
        <button
          type="button"
          :disabled="busy"
          @click="checkCompleteness"
        >
          Check completeness
        </button>
      </section>

      <section
        v-else
        class="panel"
      >
        <h2>Argument completeness</h2>
        <p
          v-if="completeness?.passed"
          class="ok"
        >
          All completeness checks pass.
        </p>
        <ul v-else>
          <li
            v-for="failure in failures"
            :key="failure.key"
          >
            {{ failure.key }}: {{ failure.gapCount }} gap(s)
          </li>
        </ul>
        <button
          type="button"
          :disabled="busy"
          @click="checkCompleteness"
        >
          Run again
        </button>
      </section>
    </template>
  </div>
</template>

<style scoped>
.wizard { max-width: 1100px; margin: 0 auto; padding: 28px 24px; }
.wizard-header { display: flex; justify-content: space-between; gap: 24px; align-items: start; }
h1 { margin: 0; font-size: 24px; } h2 { margin-top: 0; font-size: 18px; }
.wizard-header p, .hint { color: #64748b; }
.steps { display: flex; flex-wrap: wrap; gap: 6px; margin: 20px 0; }
.steps button { border: 1px solid #cbd5e1; background: #fff; padding: 7px 10px; border-radius: 6px; }
.steps button.active { border-color: #2563eb; background: #eff6ff; color: #1d4ed8; }
.panel, .guidance { border: 1px solid #e2e8f0; border-radius: 8px; padding: 18px; margin-bottom: 14px; }
.guidance { background: #f8fafc; font-size: 13px; }
.panel button { margin: 8px 8px 0 0; padding: 8px 12px; }
.svg { overflow: auto; background: #fff; border: 1px solid #e2e8f0; padding: 12px; margin: 12px 0; }
.svg :deep(svg) { max-width: 100%; height: auto; }
.ok { color: #166534; } .warning { color: #92400e; } .error { color: #b91c1c; }
</style>
