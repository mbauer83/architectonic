<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AssuranceAnalysisPicker from '../components/AssuranceAnalysisPicker.vue'
import AssuranceRelationLinker from '../components/AssuranceRelationLinker.vue'
import AssuranceStpaReview from '../components/AssuranceStpaReview.vue'
import {
  STPA_STEPS,
  STPA_GUIDEWORDS,
  buildGuidewordGrid,
  summariseStpaComplete,
  stepsWithContent,
  unboundControlNodes,
  ucaName,
  type AssuranceNode,
  type AssuranceEdge,
  type StpaStep,
  type StpaGuideword,
  type StpaCompleteResponse,
} from './AssuranceStpaWizard.helpers'

const route = useRoute()
const router = useRouter()

const analysisId = ref<string | null>(
  typeof route.query['analysis_id'] === 'string' ? route.query['analysis_id'] : null,
)
const stepKey = ref<string>('losses')
const currentStep = computed<StpaStep>(
  () => STPA_STEPS.find((s) => s.key === stepKey.value) ?? STPA_STEPS[0],
)

const nodes = ref<AssuranceNode[]>([])
const edges = ref<AssuranceEdge[]>([])
const guidance = ref<{ what?: string; why?: string; standard?: string }>({})
const completeness = ref<StpaCompleteResponse | null>(null)
const error = ref<string | null>(null)
const busy = ref(false)

// Per-step add form
const newName = ref('')
const newControlAction = ref('')

const nodesByType = (t: string) => nodes.value.filter((n) => n.node_type === t)
const stepNodes = computed(() => nodesByType(currentStep.value.nodeType))
const contentSteps = computed(() => stepsWithContent(nodes.value))
const unbound = computed(() => unboundControlNodes(nodes.value))

const grid = computed(() =>
  buildGuidewordGrid(nodesByType('control-action'), nodesByType('unsafe-control-action'), edges.value),
)
const completenessSummary = computed(() =>
  completeness.value ? summariseStpaComplete(completeness.value) : null,
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

async function loadGuidance() {
  guidance.value = {}
  if (!currentStep.value.guidanceTopic) return
  const resp = await fetch(`/api/assurance/guidance/${encodeURIComponent(currentStep.value.guidanceTopic)}`)
  if (resp.ok) guidance.value = await resp.json() as { what?: string; why?: string; standard?: string }
}

async function loadCompleteness() {
  if (!analysisId.value) return
  const resp = await fetch(`/api/assurance/analyses/${encodeURIComponent(analysisId.value)}/completeness`)
  if (resp.ok) completeness.value = await resp.json() as StpaCompleteResponse
}

async function createNode(nodeType: string, name: string, extra: Record<string, string> = {}): Promise<string | null> {
  if (!name.trim() || !analysisId.value) return null
  busy.value = true
  error.value = null
  try {
    const url = `/api/assurance/analyses/${encodeURIComponent(analysisId.value)}/nodes`
    const resp = await fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_type: nodeType, name: name.trim(), ...extra }),
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

async function addStepNode() {
  const id = await createNode(currentStep.value.nodeType, newName.value)
  if (id) { newName.value = ''; await loadNodes() }
}

async function addControlAction() {
  const id = await createNode('control-action', newControlAction.value)
  if (id) { newControlAction.value = ''; await loadNodes() }
}

async function addUca(controlAction: AssuranceNode, guideword: StpaGuideword) {
  const id = await createNode('unsafe-control-action', ucaName(controlAction.name, guideword), { uca_type: guideword })
  if (id) {
    await createEdge(id, controlAction.node_id, 'concerns')
    await loadNodes()
  }
}

async function linkRelation(node: AssuranceNode, targetId: string) {
  if (!targetId || !currentStep.value.relation) return
  await createEdge(node.node_id, targetId, currentStep.value.relation.connType)
  await loadNodes()
}

function relationTargets() {
  const rel = currentStep.value.relation
  return rel ? nodesByType(rel.targetType) : []
}

function edgeExists(source: string, connType: string): boolean {
  return edges.value.some((e) => e.source_id === source && e.conn_type === connType)
}

function modelThis(node: AssuranceNode) {
  void router.push({ path: '/assurance', query: { node_id: node.node_id } })
}

async function sealBaseline() {
  busy.value = true
  try {
    await fetch('/api/assurance/baselines', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes: `STPA analysis ${analysisId.value}`, analysis_id: analysisId.value }),
    })
    await loadCompleteness()
  } finally {
    busy.value = false
  }
}

function goToStep(key: string) {
  stepKey.value = key
}

watch(analysisId, (val) => {
  void router.replace({ path: '/assurance/stpa', query: val ? { analysis_id: val } : {} })
  void loadNodes()
})
watch(stepKey, () => {
  void loadGuidance()
  if (stepKey.value === 'review') void loadCompleteness()
})

onMounted(() => {
  void loadNodes()
  void loadGuidance()
})
</script>

<template>
  <div class="wiz">
    <div class="wiz-header">
      <h1 class="wiz-title">
        STPA wizard
      </h1>
      <AssuranceAnalysisPicker v-model="analysisId" />
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
      Select or create an STPA analysis above to begin. Every node you author
      belongs to that analysis.
    </p>

    <template v-else>
      <!-- Stepper -->
      <nav class="stepper">
        <button
          v-for="(s, i) in STPA_STEPS"
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
          v-if="guidance.standard"
          class="guidance-std"
        >
          {{ guidance.standard }}
        </p>
      </div>

      <!-- UCA guideword grid -->
      <section
        v-if="currentStep.key === 'ucas'"
        class="step-body"
      >
        <div class="add-row">
          <input
            v-model="newControlAction"
            class="add-input"
            placeholder="New control action (e.g. 'Apply brakes')"
            @keyup.enter="addControlAction"
          >
          <button
            class="add-btn"
            type="button"
            :disabled="busy"
            @click="addControlAction"
          >
            + Control action
          </button>
        </div>
        <p
          v-if="grid.length === 0"
          class="empty"
        >
          Add a control action to build the guideword grid.
        </p>
        <table
          v-else
          class="grid"
        >
          <thead>
            <tr>
              <th>Control action</th>
              <th
                v-for="gw in STPA_GUIDEWORDS"
                :key="gw"
              >
                {{ gw }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in grid"
              :key="row.controlAction.node_id"
            >
              <td class="grid-ca">
                {{ row.controlAction.name }}
              </td>
              <td
                v-for="cell in row.cells"
                :key="cell.guideword"
              >
                <span
                  v-if="cell.existing"
                  class="cell-set"
                  title="UCA exists"
                >✓</span>
                <button
                  v-else
                  class="cell-add"
                  type="button"
                  :disabled="busy"
                  @click="addUca(row.controlAction, cell.guideword)"
                >
                  +
                </button>
              </td>
            </tr>
          </tbody>
        </table>

        <!-- Effects: each unsafe control action leads to the hazard it brings about. -->
        <div
          v-if="currentStep.relation && stepNodes.length"
          class="effects"
        >
          <h2 class="effects-title">
            Effects
          </h2>
          <ul class="node-list">
            <li
              v-for="node in stepNodes"
              :key="node.node_id"
              class="node-row"
            >
              <span class="node-name">{{ node.name }}</span>
              <AssuranceRelationLinker
                :conn-type="currentStep.relation.connType"
                :target-label="currentStep.relation.targetLabel"
                :linked="edgeExists(node.node_id, currentStep.relation.connType)"
                :targets="relationTargets()"
                :disabled="busy"
                @link="(targetId) => linkRelation(node, targetId)"
              />
            </li>
          </ul>
        </div>
      </section>

      <!-- Review -->
      <AssuranceStpaReview
        v-else-if="currentStep.key === 'review'"
        :summary="completenessSummary"
        :busy="busy"
        @recheck="loadCompleteness"
        @seal="sealBaseline"
      />

      <!-- Generic node step (losses / hazards / control structure / constraints) -->
      <section
        v-else
        class="step-body"
      >
        <div class="add-row">
          <input
            v-model="newName"
            class="add-input"
            :placeholder="`New ${currentStep.label.toLowerCase().replace(/s$/, '')}`"
            @keyup.enter="addStepNode"
          >
          <button
            class="add-btn"
            type="button"
            :disabled="busy"
            @click="addStepNode"
          >
            + Add
          </button>
        </div>

        <p
          v-if="stepNodes.length === 0"
          class="empty"
        >
          No {{ currentStep.label.toLowerCase() }} yet.
        </p>
        <ul
          v-else
          class="node-list"
        >
          <li
            v-for="node in stepNodes"
            :key="node.node_id"
            class="node-row"
          >
            <span class="node-name">{{ node.name }}</span>

            <!-- Relation linker (e.g. hazard leads-to loss) -->
            <AssuranceRelationLinker
              v-if="currentStep.relation"
              :conn-type="currentStep.relation.connType"
              :target-label="currentStep.relation.targetLabel"
              :linked="edgeExists(node.node_id, currentStep.relation.connType)"
              :targets="relationTargets()"
              :disabled="busy"
              @link="(targetId) => linkRelation(node, targetId)"
            />

            <!-- model-this for unbound control-structure nodes -->
            <button
              v-if="node.node_type === 'control-structure-node' && node.binding_status === 'unbound-pending'"
              class="model-this-btn"
              type="button"
              title="This node is not bound to an architecture element"
              @click="modelThis(node)"
            >
              ⚠ model &amp; bind
            </button>
          </li>
        </ul>

        <p
          v-if="currentStep.key === 'control-structure' && unbound.length"
          class="unbound-note"
        >
          {{ unbound.length }} control node{{ unbound.length === 1 ? '' : 's' }} not yet bound to
          architecture. Use “model &amp; bind” to close the gap.
        </p>
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
.guidance-std { font-size: 12px; color: #0369a1; font-style: italic; margin: 0; }
.step-body { display: flex; flex-direction: column; gap: 12px; }
.add-row { display: flex; gap: 8px; }
.add-input { flex: 1; font-size: 13px; padding: 7px 10px; border: 1px solid #cbd5e1; border-radius: 6px; }
.add-btn {
  font-size: 13px; padding: 7px 14px; border: none; border-radius: 6px;
  background: #2563eb; color: #fff; font-weight: 600; cursor: pointer;
}
.add-btn:disabled { opacity: 0.5; cursor: default; }
.empty { color: #94a3b8; font-size: 13px; }
.node-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.node-row { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border: 1px solid #e2e8f0; border-radius: 6px; }
.node-name { flex: 1; font-size: 13px; font-weight: 500; }
.effects { margin-top: 16px; display: flex; flex-direction: column; gap: 8px; }
.effects-title { font-size: 14px; font-weight: 600; margin: 0; color: #334155; }
.model-this-btn {
  font-size: 12px; padding: 4px 10px; border: 1px solid #fcd34d; border-radius: 5px;
  background: #fffbeb; color: #b45309; cursor: pointer;
}
.unbound-note { font-size: 12px; color: #b45309; }
.grid { border-collapse: collapse; font-size: 12px; }
.grid th, .grid td { border: 1px solid #e2e8f0; padding: 6px 10px; text-align: center; }
.grid th { background: #f8fafc; font-weight: 600; }
.grid-ca { text-align: left; font-weight: 500; }
.cell-set { color: #15803d; font-weight: 700; }
.cell-add {
  width: 22px; height: 22px; border: 1px dashed #93c5fd; border-radius: 4px;
  background: #eff6ff; color: #1d4ed8; cursor: pointer; line-height: 1;
}
</style>
