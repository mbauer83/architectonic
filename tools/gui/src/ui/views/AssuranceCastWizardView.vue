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
  selectionRoute } from './AssuranceCastWizard.helpers'

const route = useRoute()
const router = useRouter()

const analysisId = ref<string | null>(
  typeof route.params.analysisId === 'string' ? route.params.analysisId : null,
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
  const resp = await fetch(`/api/assurance/guidance/${encodeURIComponent(currentStep.value.guidanceTopic)}`)
  if (resp.ok) guidance.value = await resp.json() as { what?: string; why?: string; how?: string }
}

async function loadCompleteness() {
  if (!analysisId.value) return
  const resp = await fetch(`/api/assurance/analyses/${encodeURIComponent(analysisId.value)}/completeness`)
  if (resp.ok) completeness.value = await resp.json() as CastCompleteResponse
}

async function createNode(nodeType: string, name: string): Promise<string | null> {
  if (!name.trim() || !analysisId.value) return null
  busy.value = true
  error.value = null
  try {
    const url = `/api/assurance/analyses/${encodeURIComponent(analysisId.value)}/nodes`
    const resp = await fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_type: nodeType, name: name.trim() }),
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
    await fetch('/api/assurance/baselines', {
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
    await fetch('/api/assurance/baselines', {
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
  void router.replace(selectionRoute(val))
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

<style scoped src="./AssuranceCastWizardView.css"></style>
