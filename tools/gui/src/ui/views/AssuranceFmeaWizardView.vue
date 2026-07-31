<script setup lang="ts">
/**
 * The failure-mode wizard: onboarding for a first analysis.
 *
 * Its job is to make one component's five cells finishable in a sitting, so it shows what is
 * *left* rather than what has been done, and it lands a returning author on the first step with
 * anything outstanding. The matrix, not this, is where returning users work — a single cell never
 * requires stepping through here to reach.
 *
 * Every relation offered is one the ontology registers, and the linking affordance is the shared
 * one. Both matter: a wizard here once declared a relation that did not exist, and its step had no
 * linking UI at all, so the chain it was supposed to close could not be closed.
 */
import { computed, onMounted, ref, watch } from 'vue'
import AssuranceRelationLinker from '../components/AssuranceRelationLinker.vue'
import { failureGuidewordLabel } from '../lib/failureGuidewords'
import {
  FMEA_STEPS,
  firstIncompleteStep,
  relationSatisfied,
  remainingGuidewords,
} from './AssuranceFmeaWizard.helpers'
import type { WizardEdge, WizardNode } from './AssuranceFmeaWizard.helpers'

const stepKey = ref('component')
const nodes = ref<WizardNode[]>([])
const edges = ref<WizardEdge[]>([])
const guidance = ref<Record<string, string>>({})
const locked = ref(false)

const step = computed(() => FMEA_STEPS.find((s) => s.key === stepKey.value) ?? FMEA_STEPS[0])
const remaining = computed(() => remainingGuidewords(nodes.value))
const failureModes = computed(() => nodes.value.filter((n) => n.node_type === 'failure-mode'))

const relationTargets = computed(() => {
  const wanted = step.value.relation?.targetType
  return wanted ? nodes.value.filter((n) => n.node_type === wanted) : []
})

async function loadGuidance(topic: string) {
  if (!topic) return
  const resp = await fetch(`/api/assurance/guidance/${encodeURIComponent(topic)}`)
  if (resp.ok) guidance.value = await resp.json() as Record<string, string>
}

async function loadModel() {
  const resp = await fetch('/api/assurance/nodes')
  if (resp.status === 423) { locked.value = true; return }
  if (resp.ok) nodes.value = ((await resp.json()) as { nodes: WizardNode[] }).nodes
  const edgeResp = await fetch('/api/assurance/edges')
  if (edgeResp.ok) edges.value = ((await edgeResp.json()) as { edges: WizardEdge[] }).edges
  stepKey.value = firstIncompleteStep(nodes.value, edges.value)
}

async function createEdge(sourceId: string, targetId: string, connType: string) {
  await fetch('/api/assurance/edges', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_id: sourceId, target_id: targetId, conn_type: connType }),
  })
  await loadModel()
}

onMounted(() => { void loadModel(); void loadGuidance(step.value.guidanceTopic) })
watch(step, (s) => { void loadGuidance(s.guidanceTopic) })
</script>

<template>
  <section class="wiz">
    <h1 class="wiz-title">
      Failure-mode analysis
    </h1>

    <p
      v-if="locked"
      class="wiz-note"
    >
      The assurance store is locked.
    </p>

    <template v-else>
      <nav class="wiz-steps">
        <button
          v-for="s in FMEA_STEPS"
          :key="s.key"
          type="button"
          class="wiz-step"
          :class="{ 'wiz-step-active': s.key === stepKey }"
          @click="stepKey = s.key"
        >
          {{ s.label }}
        </button>
      </nav>

      <aside
        v-if="guidance.what"
        class="wiz-guidance"
      >
        <h2 class="wiz-guidance-title">
          {{ guidance.step }}
        </h2>
        <p>{{ guidance.what }}</p>
        <p><strong>Why.</strong> {{ guidance.why }}</p>
        <p><strong>How.</strong> {{ guidance.how }}</p>
      </aside>

      <div
        v-if="stepKey === 'failure-modes'"
        class="wiz-body"
      >
        <p v-if="remaining.length">
          Still to examine:
          <span
            v-for="slug in remaining"
            :key="slug"
            class="wiz-chip"
          >{{ failureGuidewordLabel(slug) }}</span>
        </p>
        <p v-else>
          Every guideword has been examined for this component.
        </p>
      </div>

      <div
        v-else-if="step.relation"
        class="wiz-body"
      >
        <ul class="wiz-list">
          <li
            v-for="node in failureModes"
            :key="node.node_id"
            class="wiz-item"
          >
            <span class="wiz-item-name">{{ node.name }}</span>
            <AssuranceRelationLinker
              :conn-type="step.relation.connType"
              :target-label="step.relation.targetLabel"
              :linked="relationSatisfied(node, step.relation, edges)"
              :targets="relationTargets"
              @link="(targetId: string) => createEdge(node.node_id, targetId, step.relation!.connType)"
            />
          </li>
        </ul>
      </div>

      <div
        v-else-if="stepKey === 'factors'"
        class="wiz-body"
      >
        <p>
          Severity and detectability are derived from what you linked in the previous steps.
          Occurrence is asked for only where it could change the priority — many rows need no
          numeric input at all. Record factors on the
          <RouterLink to="/assurance/fmea">
            matrix
          </RouterLink>, where each row shows what it still needs.
        </p>
      </div>

      <div
        v-else
        class="wiz-body"
      >
        <p>
          {{ failureModes.length }} failure mode(s) recorded. The
          <RouterLink to="/assurance/fmea">
            matrix
          </RouterLink>
          is where they are reviewed and rated from here on.
        </p>
      </div>
    </template>
  </section>
</template>

<style scoped>
.wiz { padding: 20px; max-width: 80ch; }
.wiz-title { font-size: 20px; margin: 0 0 12px; }
.wiz-note { font-size: 13px; color: #4b5563; }
.wiz-steps { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
.wiz-step {
  font-size: 12px;
  padding: 5px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 5px;
  background: #f8fafc;
  cursor: pointer;
}
.wiz-step-active { border-color: #2563eb; background: #eff6ff; font-weight: 600; }
.wiz-guidance {
  font-size: 13px;
  color: #374151;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 14px;
}
.wiz-guidance-title { font-size: 13px; font-weight: 600; margin: 0 0 6px; }
.wiz-guidance p { margin: 0 0 6px; }
.wiz-body { font-size: 13px; }
.wiz-chip {
  display: inline-block;
  font-size: 12px;
  background: #eef2ff;
  color: #3730a3;
  border-radius: 4px;
  padding: 2px 7px;
  margin: 0 4px;
}
.wiz-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.wiz-item { display: flex; align-items: center; gap: 10px; }
.wiz-item-name { flex: 1; }
</style>
