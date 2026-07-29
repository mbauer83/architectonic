<script setup lang="ts">
/** GRC wizard's "Risks" step: add-risk form (name/likelihood/impact) + risk list. */
import { inject, ref } from 'vue'
import { RISK_LEVELS, riskScore } from '../views/AssuranceGrcWizard.helpers'
import { grcWizardDataKey } from '../composables/useGrcWizardData'

const data = inject(grcWizardDataKey)!

const newRisk = ref({ name: '', likelihood: 'medium', impact: 'medium' })

const addRisk = async () => {
  const id = await data.createNode('risk', newRisk.value.name, {
    likelihood: newRisk.value.likelihood, impact: newRisk.value.impact,
  })
  if (id) { newRisk.value = { name: '', likelihood: 'medium', impact: 'medium' }; await data.loadNodes() }
}
</script>

<template>
  <section class="step-body">
    <div class="add-row">
      <input
        v-model="newRisk.name"
        class="add-input"
        placeholder="New risk (e.g. 'Unauthorised data exposure')"
        @keyup.enter="addRisk"
      >
      <select
        v-model="newRisk.likelihood"
        class="lvl-select"
        aria-label="Likelihood"
      >
        <option
          v-for="lvl in RISK_LEVELS"
          :key="lvl"
          :value="lvl"
        >
          L: {{ lvl }}
        </option>
      </select>
      <select
        v-model="newRisk.impact"
        class="lvl-select"
        aria-label="Impact"
      >
        <option
          v-for="lvl in RISK_LEVELS"
          :key="lvl"
          :value="lvl"
        >
          I: {{ lvl }}
        </option>
      </select>
      <button
        class="add-btn"
        type="button"
        :disabled="data.busy"
        @click="addRisk"
      >
        + Add
      </button>
    </div>
    <p
      v-if="data.risks.length === 0"
      class="empty"
    >
      No risks yet. A risk evaluates a hazard or loss-scenario (likelihood × impact).
    </p>
    <ul
      v-else
      class="node-list"
    >
      <li
        v-for="risk in data.risks"
        :key="risk.node_id"
        class="node-row"
      >
        <span class="node-name">{{ risk.name }}</span>
        <span
          v-if="riskScore(risk)"
          class="score"
        >{{ riskScore(risk) }}</span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.step-body { display: flex; flex-direction: column; gap: 12px; }
.add-row { display: flex; gap: 8px; flex-wrap: wrap; }
.add-input { flex: 1; min-width: 200px; font-size: 13px; padding: 7px 10px; border: 1px solid #cbd5e1; border-radius: 6px; }
.lvl-select { font-size: 13px; padding: 6px 8px; border: 1px solid #cbd5e1; border-radius: 6px; }
.add-btn {
  font-size: 13px; padding: 7px 14px; border: none; border-radius: 6px;
  background: #2563eb; color: #fff; font-weight: 600; cursor: pointer;
}
.add-btn:disabled { opacity: 0.5; cursor: default; }
.empty { color: #94a3b8; font-size: 13px; }
.node-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.node-row { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border: 1px solid #e2e8f0; border-radius: 6px; }
.node-name { font-size: 13px; font-weight: 500; }
.score { font-size: 12px; color: #b45309; background: #fffbeb; padding: 2px 8px; border-radius: 10px; }
</style>
