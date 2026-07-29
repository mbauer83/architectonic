<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AssuranceAnalysisPicker from '../components/AssuranceAnalysisPicker.vue'
import {
  CAST_STEPS,
  summariseCastComplete,
  castStepBadges,
  gapNodeIds,
  linkedSourceIds,
  linkedTargetIds,
  unlinkedSources,
  type AssuranceNode,
  type AssuranceEdge,
  type Baseline,
  type CastStep,
  type CastCompleteResponse,
} from './AssuranceCastWizard.helpers'

const route = useRoute()
const router = useRouter()

const analysisId = ref<string | null>(
  typeof route.query['analysis_id'] === 'string' ? route.query['analysis_id'] : null,
)
const stepKey = ref<string>('baseline')
const currentStep = computed<CastStep>(
  () => CAST_STEPS.find((s) => s.key === stepKey.value) ?? CAST_STEPS[0],
)

const nodes = ref<AssuranceNode[]>([])
const edges = ref<AssuranceEdge[]>([])
const baselines = ref<Baseline[]>([])
const guidance = ref<{ what?: string; why?: string; how?: string }>({})
const completeness = ref<CastCompleteResponse | null>(null)
const error = ref<string | null>(null)
const busy = ref(false)

const newIncident = ref('')
const newObserved = ref('')
const newCorrective = ref('')
const newConstraint = ref('')

const incidents = computed(() => nodes.value.filter((n) => n.node_type === 'incident'))
const observed = computed(() => nodes.value.filter((n) => n.node_type === 'control-structure-node'))
const correctives = computed(() => nodes.value.filter((n) => n.node_type === 'corrective-action'))
const constraints = computed(() => nodes.value.filter((n) => n.node_type === 'assurance-constraint'))
const contentSteps = computed(() => castStepBadges(nodes.value, baselines.value.length))

const investigatesGapIds = computed(() => gapNodeIds(completeness.value, 'incident_has_investigates'))
const completenessSummary = computed(() =>
  completeness.value ? summariseCastComplete(completeness.value) : null,
)

async function loadNodes() {
  if (!analysisId.value) { nodes.value = []; edges.value = []; return }
  const aid = encodeURIComponent(analysisId.value)
  const [nResp, eResp] = await Promise.all([
    fetch(`/api/assurance/nodes?analysis_id=${aid}`),
    fetch('/api/assurance/edges'),
  ])
  if (nResp.status === 423) { error.value = 'The assurance store is locked.'; return }
  const nBody = await nResp.json() as { nodes: AssuranceNode[] }
  nodes.value = nBody.nodes
  const ids = new Set(nodes.value.map((n) => n.node_id))
  const eBody = await eResp.json() as { edges: AssuranceEdge[] }
  edges.value = eBody.edges.filter((e) => ids.has(e.source_id) && ids.has(e.target_id))
}

async function loadBaselines() {
  const resp = await fetch('/api/assurance/baselines')
  if (!resp.ok) { baselines.value = []; return }
  const body = await resp.json() as { baselines: (Baseline & { analysis_id?: string })[] }
  baselines.value = body.baselines.filter((b) => b.analysis_id === analysisId.value)
}

async function loadGuidance() {
  guidance.value = {}
  if (!currentStep.value.guidanceTopic) return
  const resp = await fetch(`/api/assurance/guidance?topic=${currentStep.value.guidanceTopic}`)
  if (resp.ok) guidance.value = await resp.json() as { what?: string; why?: string; how?: string }
}

async function loadCompleteness() {
  if (!analysisId.value) return
  const resp = await fetch(`/api/assurance/cast-complete?analysis_id=${encodeURIComponent(analysisId.value)}`)
  if (resp.ok) completeness.value = await resp.json() as CastCompleteResponse
}

async function createNode(nodeType: string, name: string): Promise<string | null> {
  if (!name.trim() || !analysisId.value) return null
  busy.value = true
  error.value = null
  try {
    const resp = await fetch('/api/assurance/nodes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_type: nodeType, name: name.trim(), analysis_id: analysisId.value }),
    })
    const body = await resp.json().catch(() => ({})) as Record<string, unknown>
    if (!resp.ok || typeof body['node_id'] !== 'string') {
      error.value = typeof body['error'] === 'string' ? body['error'] : `HTTP ${resp.status}`
      return null
    }
    return body['node_id']
  } catch (e) {
    error.value = String(e)
    return null
  } finally {
    busy.value = false
  }
}

async function createEdge(source: string, target: string, connType: string) {
  await fetch('/api/assurance/edges', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_id: source, target_id: target, conn_type: connType }),
  })
}

async function sealCurrentState() {
  if (!analysisId.value) return
  busy.value = true
  try {
    await fetch('/api/assurance/baselines/seal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes: `CAST baseline ${analysisId.value}`, analysis_id: analysisId.value }),
    })
    await loadBaselines()
    await loadCompleteness()
  } finally {
    busy.value = false
  }
}

async function addIncident() {
  const id = await createNode('incident', newIncident.value)
  if (id) { newIncident.value = ''; await loadNodes() }
}

async function addObserved() {
  const id = await createNode('control-structure-node', newObserved.value)
  if (id) { newObserved.value = ''; await loadNodes() }
}

async function addCorrective() {
  const id = await createNode('corrective-action', newCorrective.value)
  if (id) { newCorrective.value = ''; await loadNodes() }
}

async function addConstraint() {
  const id = await createNode('assurance-constraint', newConstraint.value)
  if (id) { newConstraint.value = ''; await loadNodes() }
}

async function linkEdge(source: string, target: string, connType: string) {
  if (!source || !target) return
  busy.value = true
  try {
    await createEdge(source, target, connType)
    await loadNodes()
    await loadCompleteness()
  } finally {
    busy.value = false
  }
}

function investigatedByIncidents(observedNode: AssuranceNode): AssuranceNode[] {
  const linked = linkedSourceIds(edges.value, observedNode.node_id, 'investigates')
  return incidents.value.filter((i) => linked.has(i.node_id))
}
const unlinkedIncidentsFor = (observedNode: AssuranceNode) =>
  unlinkedSources(incidents.value, edges.value, observedNode.node_id, 'investigates')

function derivedConstraints(corrective: AssuranceNode): AssuranceNode[] {
  const linked = linkedTargetIds(edges.value, corrective.node_id, 'derives')
  return constraints.value.filter((c) => linked.has(c.node_id))
}
function unlinkedConstraintsFor(corrective: AssuranceNode): AssuranceNode[] {
  const linked = linkedTargetIds(edges.value, corrective.node_id, 'derives')
  return constraints.value.filter((c) => !linked.has(c.node_id))
}

async function sealBaseline() {
  busy.value = true
  try {
    await fetch('/api/assurance/baselines/seal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes: `CAST analysis ${analysisId.value}`, analysis_id: analysisId.value }),
    })
    await loadBaselines()
    await loadCompleteness()
  } finally {
    busy.value = false
  }
}

function goToStep(key: string) {
  stepKey.value = key
}

watch(analysisId, (val) => {
  void router.replace({ path: '/assurance/cast', query: val ? { analysis_id: val } : {} })
  void loadNodes()
  void loadBaselines()
  void loadCompleteness()
})
watch(stepKey, () => {
  void loadGuidance()
  if (stepKey.value === 'incident' || stepKey.value === 'review') void loadCompleteness()
  if (stepKey.value === 'baseline') void loadBaselines()
})

onMounted(() => {
  void loadNodes()
  void loadBaselines()
  void loadGuidance()
  void loadCompleteness()
})
</script>

<template>
  <div class="wiz">
    <div class="wiz-header">
      <h1 class="wiz-title">
        CAST wizard
      </h1>
      <AssuranceAnalysisPicker
        v-model="analysisId"
        default-method="CAST"
      />
    </div>

    <div
      v-if="error"
      class="wiz-error"
    >
      {{ error }}
    </div>

    <p
      v-if="!analysisId"
      class="wiz-hint"
    >
      Select or create a CAST analysis above to begin. CAST reconstructs the control
      structure as-existed at an incident; every node belongs to that analysis.
    </p>

    <template v-else>
      <!-- Stepper -->
      <nav class="stepper">
        <button
          v-for="(s, i) in CAST_STEPS"
          :key="s.key"
          class="step-tab"
          :class="{ 'step-tab--active': s.key === stepKey, 'step-tab--done': contentSteps.has(s.key) }"
          type="button"
          @click="goToStep(s.key)"
        >
          <span class="step-num">{{ i + 1 }}</span>
          {{ s.label }}
        </button>
      </nav>

      <!-- Guidance -->
      <div
        v-if="guidance.what"
        class="guidance"
      >
        <p class="guidance-what">
          {{ guidance.what }}
        </p>
        <p
          v-if="guidance.why"
          class="guidance-why"
        >
          {{ guidance.why }}
        </p>
        <p
          v-if="guidance.how"
          class="guidance-how"
        >
          {{ guidance.how }}
        </p>
      </div>

      <!-- Baseline -->
      <section
        v-if="currentStep.key === 'baseline'"
        class="step-body"
      >
        <p class="gate-note">
          CAST requires a sealed baseline to pin the model state as-existed at the incident
          (§10 reproducibility gate). Seal one before — or while — investigating.
        </p>
        <button
          class="add-btn"
          type="button"
          :disabled="busy"
          @click="sealCurrentState"
        >
          🔒 Seal current state as baseline
        </button>
        <p
          v-if="baselines.length === 0"
          class="empty"
        >
          No sealed baseline for this analysis yet.
        </p>
        <ul
          v-else
          class="node-list"
        >
          <li
            v-for="b in baselines"
            :key="b.baseline_id"
            class="node-row"
          >
            <span class="node-name">{{ b.notes || b.baseline_id }}</span>
            <span class="muted">{{ b.created_at }}</span>
          </li>
        </ul>
      </section>

      <!-- Incident -->
      <section
        v-else-if="currentStep.key === 'incident'"
        class="step-body"
      >
        <div class="add-row">
          <input
            v-model="newIncident"
            class="add-input"
            placeholder="New incident / accident (e.g. 'Unintended acceleration, 2026-05')"
            @keyup.enter="addIncident"
          >
          <button
            class="add-btn"
            type="button"
            :disabled="busy"
            @click="addIncident"
          >
            + Add
          </button>
        </div>
        <p
          v-if="incidents.length === 0"
          class="empty"
        >
          No incidents yet. An incident is the loss event CAST investigates.
        </p>
        <ul
          v-else
          class="node-list"
        >
          <li
            v-for="incident in incidents"
            :key="incident.node_id"
            class="node-row"
          >
            <span class="node-name">{{ incident.name }}</span>
            <span
              v-if="investigatesGapIds.has(incident.node_id)"
              class="badge badge--gap"
            >no investigates link</span>
            <span
              v-else
              class="badge badge--ok"
            >investigated ✓</span>
          </li>
        </ul>
      </section>

      <!-- Investigate -->
      <section
        v-else-if="currentStep.key === 'investigate'"
        class="step-body"
      >
        <div class="add-row">
          <input
            v-model="newObserved"
            class="add-input"
            placeholder="Observed factor (control-structure node as-existed)"
            @keyup.enter="addObserved"
          >
          <button
            class="add-btn"
            type="button"
            :disabled="busy"
            @click="addObserved"
          >
            + Add
          </button>
        </div>
        <p
          v-if="observed.length === 0"
          class="empty"
        >
          Add the observed control-structure factors, then link each to the incident(s)
          it explains.
        </p>
        <ul
          v-else
          class="node-list"
        >
          <li
            v-for="obs in observed"
            :key="obs.node_id"
            class="link-row"
          >
            <span class="node-name">{{ obs.name }}</span>
            <span class="link-chips">
              <span
                v-for="i in investigatedByIncidents(obs)"
                :key="i.node_id"
                class="chip"
              >investigates: {{ i.name }}</span>
            </span>
            <select
              v-if="unlinkedIncidentsFor(obs).length"
              class="relation-select"
              :disabled="busy"
              @change="linkEdge(($event.target as HTMLSelectElement).value, obs.node_id, 'investigates')"
            >
              <option value="">
                investigated by incident…
              </option>
              <option
                v-for="i in unlinkedIncidentsFor(obs)"
                :key="i.node_id"
                :value="i.node_id"
              >
                {{ i.name }}
              </option>
            </select>
          </li>
        </ul>
      </section>

      <!-- Corrective Actions -->
      <section
        v-else-if="currentStep.key === 'corrective'"
        class="step-body"
      >
        <div class="add-row">
          <input
            v-model="newCorrective"
            class="add-input"
            placeholder="New corrective action"
            @keyup.enter="addCorrective"
          >
          <button
            class="add-btn"
            type="button"
            :disabled="busy"
            @click="addCorrective"
          >
            + Action
          </button>
        </div>
        <div class="add-row">
          <input
            v-model="newConstraint"
            class="add-input"
            placeholder="New corrective constraint"
            @keyup.enter="addConstraint"
          >
          <button
            class="add-btn"
            type="button"
            :disabled="busy"
            @click="addConstraint"
          >
            + Constraint
          </button>
        </div>
        <p
          v-if="correctives.length === 0"
          class="empty"
        >
          No corrective actions yet. Each must derive ≥1 corrective constraint.
        </p>
        <ul
          v-else
          class="node-list"
        >
          <li
            v-for="ca in correctives"
            :key="ca.node_id"
            class="link-row"
          >
            <span class="node-name">{{ ca.name }}</span>
            <span class="link-chips">
              <span
                v-for="c in derivedConstraints(ca)"
                :key="c.node_id"
                class="chip"
              >derives: {{ c.name }}</span>
            </span>
            <select
              v-if="unlinkedConstraintsFor(ca).length"
              class="relation-select"
              :disabled="busy"
              @change="linkEdge(ca.node_id, ($event.target as HTMLSelectElement).value, 'derives')"
            >
              <option value="">
                derives constraint…
              </option>
              <option
                v-for="c in unlinkedConstraintsFor(ca)"
                :key="c.node_id"
                :value="c.node_id"
              >
                {{ c.name }}
              </option>
            </select>
          </li>
        </ul>
      </section>

      <!-- Review -->
      <section
        v-else
        class="step-body"
      >
        <button
          class="add-btn"
          type="button"
          :disabled="busy"
          @click="loadCompleteness"
        >
          ↺ Re-check completeness
        </button>
        <div
          v-if="completenessSummary"
          class="review"
        >
          <p
            class="review-status"
            :class="completenessSummary.passed ? 'review-status--ok' : 'review-status--gap'"
          >
            {{ completenessSummary.passed ? 'All CAST coverage checks passed.' : 'Coverage gaps remain:' }}
          </p>
          <ul
            v-if="!completenessSummary.passed"
            class="gap-list"
          >
            <li
              v-for="f in completenessSummary.failed"
              :key="f.key"
            >
              {{ f.key }} — {{ f.gapCount }} gap{{ f.gapCount === 1 ? '' : 's' }}
            </li>
          </ul>
          <button
            class="seal-btn"
            type="button"
            :disabled="busy || !completenessSummary.passed"
            @click="sealBaseline"
          >
            Seal baseline
          </button>
          <p
            v-if="!completenessSummary.passed"
            class="seal-note"
          >
            Resolve the gaps above (seal a baseline, link incidents to observed factors, and
            derive corrective constraints) before sealing.
          </p>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.wiz { padding: 20px 24px; max-width: 900px; }
.wiz-header { display: flex; flex-direction: column; gap: 12px; margin-bottom: 16px; }
.wiz-title { font-size: 20px; font-weight: 700; margin: 0; }
.wiz-error { padding: 10px 14px; background: #fef2f2; color: #b91c1c; border-radius: 6px; margin-bottom: 12px; font-size: 13px; }
.wiz-hint { color: #64748b; font-size: 14px; }
.stepper { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; }
.step-tab {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 12px; border: 1px solid #e2e8f0; border-radius: 6px;
  background: #fff; color: #475569; font-size: 13px; cursor: pointer;
}
.step-tab--active { background: #2563eb; color: #fff; border-color: #2563eb; }
.step-tab--done:not(.step-tab--active) { border-color: #86efac; }
.step-num {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; border-radius: 50%; background: #e2e8f0; color: #475569; font-size: 11px;
}
.step-tab--active .step-num { background: rgba(255,255,255,0.3); color: #fff; }
.guidance { background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; }
.guidance-what { font-size: 14px; font-weight: 600; color: #075985; margin: 0 0 4px; }
.guidance-why { font-size: 13px; color: #0c4a6e; margin: 0 0 4px; }
.guidance-how { font-size: 12px; color: #0369a1; margin: 0; }
.step-body { display: flex; flex-direction: column; gap: 12px; }
.gate-note { font-size: 13px; color: #7c2d12; background: #fff7ed; border: 1px solid #fed7aa; border-radius: 8px; padding: 10px 14px; margin: 0; }
.add-row { display: flex; gap: 8px; flex-wrap: wrap; }
.add-input { flex: 1; min-width: 200px; font-size: 13px; padding: 7px 10px; border: 1px solid #cbd5e1; border-radius: 6px; }
.add-btn {
  font-size: 13px; padding: 7px 14px; border: none; border-radius: 6px;
  background: #2563eb; color: #fff; font-weight: 600; cursor: pointer;
}
.add-btn:disabled { opacity: 0.5; cursor: default; }
.empty { color: #94a3b8; font-size: 13px; }
.muted { color: #94a3b8; font-size: 12px; }
.node-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.node-row { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border: 1px solid #e2e8f0; border-radius: 6px; }
.node-name { font-size: 13px; font-weight: 500; }
.badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 600; }
.badge--gap { background: #fef3c7; color: #b45309; }
.badge--ok { background: #dcfce7; color: #15803d; }
.link-row { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border: 1px solid #e2e8f0; border-radius: 6px; flex-wrap: wrap; }
.link-chips { display: flex; gap: 6px; flex-wrap: wrap; flex: 1; }
.chip { font-size: 11px; background: #eef2ff; color: #3730a3; padding: 2px 8px; border-radius: 10px; }
.relation-select { font-size: 12px; padding: 4px 8px; border: 1px solid #cbd5e1; border-radius: 5px; }
.review { display: flex; flex-direction: column; gap: 10px; margin-top: 4px; }
.review-status { font-size: 14px; font-weight: 600; margin: 0; }
.review-status--ok { color: #15803d; }
.review-status--gap { color: #b45309; }
.gap-list { margin: 0; padding-left: 20px; font-size: 13px; color: #475569; }
.seal-btn {
  align-self: flex-start; font-size: 13px; padding: 8px 18px; border: none; border-radius: 6px;
  background: #15803d; color: #fff; font-weight: 600; cursor: pointer;
}
.seal-btn:disabled { opacity: 0.5; cursor: default; }
.seal-note { font-size: 12px; color: #94a3b8; margin: 0; }
</style>
