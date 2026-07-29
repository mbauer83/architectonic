<script setup lang="ts">
/** GRC wizard's "Controls" step: add-control form + control list, each linkable to the
 * risks it treats. */
import { inject, ref } from 'vue'
import { grcWizardDataKey } from '../composables/useGrcWizardData'

const data = inject(grcWizardDataKey)!

const newControl = ref('')

const addControl = async () => {
  const id = await data.createNode('assurance-constraint', newControl.value)
  if (id) { newControl.value = ''; await data.loadNodes() }
}
</script>

<template>
  <section class="step-body">
    <div class="add-row">
      <input
        v-model="newControl"
        class="add-input"
        placeholder="New control / assurance constraint"
        @keyup.enter="addControl"
      >
      <button
        class="add-btn"
        type="button"
        :disabled="data.busy"
        @click="addControl"
      >
        + Add
      </button>
    </div>
    <p
      v-if="data.controls.length === 0"
      class="empty"
    >
      No controls yet. A control is the assurance constraint that treats a risk.
    </p>
    <ul
      v-else
      class="node-list"
    >
      <li
        v-for="control in data.controls"
        :key="control.node_id"
        class="link-row"
      >
        <span class="node-name">{{ control.name }}</span>
        <span class="link-chips">
          <span
            v-for="r in data.treatedByRisks(control)"
            :key="r.node_id"
            class="chip"
          >treats: {{ r.name }}</span>
        </span>
        <select
          v-if="data.unlinkedRisksFor(control).length"
          class="relation-select"
          :disabled="data.busy"
          @change="data.linkSource(($event.target as HTMLSelectElement).value, control.node_id, 'treated-by')"
        >
          <option value="">
            treated-by risk…
          </option>
          <option
            v-for="r in data.unlinkedRisksFor(control)"
            :key="r.node_id"
            :value="r.node_id"
          >
            {{ r.name }}
          </option>
        </select>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.step-body { display: flex; flex-direction: column; gap: 12px; }
.add-row { display: flex; gap: 8px; flex-wrap: wrap; }
.add-input { flex: 1; min-width: 200px; font-size: 13px; padding: 7px 10px; border: 1px solid #cbd5e1; border-radius: 6px; }
.add-btn {
  font-size: 13px; padding: 7px 14px; border: none; border-radius: 6px;
  background: #2563eb; color: #fff; font-weight: 600; cursor: pointer;
}
.add-btn:disabled { opacity: 0.5; cursor: default; }
.empty { color: #94a3b8; font-size: 13px; }
.node-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.node-name { font-size: 13px; font-weight: 500; }
.link-row { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border: 1px solid #e2e8f0; border-radius: 6px; flex-wrap: wrap; }
.link-chips { display: flex; gap: 6px; flex-wrap: wrap; flex: 1; }
.chip { font-size: 11px; background: #eef2ff; color: #3730a3; padding: 2px 8px; border-radius: 10px; }
.relation-select { font-size: 12px; padding: 4px 8px; border: 1px solid #cbd5e1; border-radius: 5px; }
</style>
