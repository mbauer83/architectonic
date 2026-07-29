<script setup lang="ts">
/** GRC wizard's "Treatment" step: per-risk treatment disposition + accountable-owner
 * assignment. */
import { inject } from 'vue'
import { TREATMENT_OPTIONS, riskTreatment } from '../views/AssuranceGrcWizard.helpers'
import { grcWizardDataKey } from '../composables/useGrcWizardData'

const data = inject(grcWizardDataKey)!
</script>

<template>
  <section class="step-body">
    <p
      v-if="data.risks.length === 0"
      class="empty"
    >
      Add risks first, then set each one's treatment and accountable owner here.
    </p>
    <ul
      v-else
      class="node-list"
    >
      <li
        v-for="risk in data.risks"
        :key="risk.node_id"
        class="treat-row"
      >
        <div class="treat-head">
          <span class="node-name">{{ risk.name }}</span>
          <span
            v-if="data.treatmentGapIds.has(risk.node_id)"
            class="badge badge--gap"
          >no treatment</span>
        </div>
        <div class="treat-controls">
          <label class="treat-label">Treatment
            <select
              class="lvl-select"
              :value="riskTreatment(risk)"
              :disabled="data.busy"
              @change="data.setTreatment(risk, ($event.target as HTMLSelectElement).value)"
            >
              <option value="">
                choose…
              </option>
              <option
                v-for="t in TREATMENT_OPTIONS"
                :key="t"
                :value="t"
              >
                {{ t }}
              </option>
            </select>
          </label>
          <span
            v-if="data.hasOwner(risk)"
            class="badge badge--ok"
          >owner ✓</span>
          <span
            v-else
            class="owner-assign"
          >
            <input
              v-model="data.ownerInput[risk.node_id]"
              class="owner-input"
              placeholder="Accountable arch role id"
              aria-label="Accountable architecture role id"
              @keyup.enter="data.assignOwner(risk)"
            >
            <button
              class="add-btn add-btn--sm"
              type="button"
              :disabled="data.busy"
              @click="data.assignOwner(risk)"
            >
              Assign owner
            </button>
          </span>
        </div>
      </li>
    </ul>
    <p class="hint-note">
      Accountability points to an architecture role (assurance → architecture, one-way).
      Enter the architecture entity id of the accountable owner.
    </p>
  </section>
</template>

<style scoped>
.step-body { display: flex; flex-direction: column; gap: 12px; }
.empty { color: #94a3b8; font-size: 13px; }
.node-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.node-name { font-size: 13px; font-weight: 500; }
.lvl-select { font-size: 13px; padding: 6px 8px; border: 1px solid #cbd5e1; border-radius: 6px; }
.add-btn {
  font-size: 13px; padding: 7px 14px; border: none; border-radius: 6px;
  background: #2563eb; color: #fff; font-weight: 600; cursor: pointer;
}
.add-btn--sm { padding: 5px 10px; font-size: 12px; }
.add-btn:disabled { opacity: 0.5; cursor: default; }
.treat-row { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px; border: 1px solid #e2e8f0; border-radius: 6px; }
.treat-head { display: flex; align-items: center; gap: 10px; }
.treat-controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.treat-label { font-size: 12px; color: #475569; display: flex; align-items: center; gap: 6px; }
.badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 600; }
.badge--gap { background: #fef3c7; color: #b45309; }
.badge--ok { background: #dcfce7; color: #15803d; }
.owner-assign { display: flex; gap: 6px; align-items: center; }
.owner-input { font-size: 12px; padding: 5px 8px; border: 1px solid #cbd5e1; border-radius: 5px; min-width: 180px; }
.hint-note { font-size: 12px; color: #64748b; margin: 0; }
</style>
