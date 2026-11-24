<script setup lang="ts">
/** GRC wizard's "Obligations" step: add-obligation form (name + the rule it comes from) +
 * obligation list, each linkable to the controls that comply with it. */
import { inject, ref } from 'vue'
import { grcWizardDataKey } from '../composables/useGrcWizardData'
import {
  OBLIGATION_PROVISION_LABEL,
  OBLIGATION_SOURCE_LABEL,
  obligationCitation,
  obligationCitationAttributes,
} from '../views/AssuranceGrcWizard.helpers'

const data = inject(grcWizardDataKey)!

const blank = () => ({ name: '', source: '', provision: '' })
const newObligation = ref(blank())

const addObligation = async () => {
  const { name, source, provision } = newObligation.value
  const id = await data.createNode('obligation', name, obligationCitationAttributes(source, provision))
  if (id) { newObligation.value = blank(); await data.loadNodes() }
}
</script>

<template>
  <section class="step-body">
    <div class="add-row">
      <input
        v-model="newObligation.name"
        class="add-input"
        placeholder="New obligation (e.g. 'ISO 27001 A.8.1')"
        @keyup.enter="addObligation"
      >
      <input
        v-model="newObligation.source"
        class="cite-input"
        :placeholder="OBLIGATION_SOURCE_LABEL"
        :aria-label="OBLIGATION_SOURCE_LABEL"
        @keyup.enter="addObligation"
      >
      <input
        v-model="newObligation.provision"
        class="cite-input"
        :placeholder="OBLIGATION_PROVISION_LABEL"
        :aria-label="OBLIGATION_PROVISION_LABEL"
        @keyup.enter="addObligation"
      >
      <button
        class="add-btn"
        type="button"
        :disabled="data.busy"
        @click="addObligation"
      >
        + Add
      </button>
    </div>
    <p
      v-if="data.obligations.length === 0"
      class="empty"
    >
      No obligations yet. An obligation is a compliance instance (clause X of standard Y).
    </p>
    <ul
      v-else
      class="node-list"
    >
      <li
        v-for="obligation in data.obligations"
        :key="obligation.node_id"
        class="link-row"
      >
        <span class="node-name">{{ obligation.name }}</span>
        <span
          v-if="obligationCitation(obligation)"
          class="citation"
        >{{ obligationCitation(obligation) }}</span>
        <span class="link-chips">
          <span
            v-for="c in data.compliantControls(obligation)"
            :key="c.node_id"
            class="chip"
          >complies: {{ c.name }}</span>
        </span>
        <select
          v-if="data.unlinkedControlsFor(obligation).length"
          class="relation-select"
          :disabled="data.busy"
          @change="data.linkSource(($event.target as HTMLSelectElement).value, obligation.node_id, 'complies-with')"
        >
          <option value="">
            complies-with control…
          </option>
          <option
            v-for="c in data.unlinkedControlsFor(obligation)"
            :key="c.node_id"
            :value="c.node_id"
          >
            {{ c.name }}
          </option>
        </select>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.step-body { display: flex; flex-direction: column; gap: 12px; }
.add-row { display: flex; gap: 8px; flex-wrap: wrap; }
.add-input { flex: 1; min-width: 200px; font-size: 13px; padding: 7px 10px; border: 1px solid var(--border-strong); border-radius: 6px; }
.cite-input {
  width: 220px; font-size: 13px; padding: 7px 10px; border: 1px solid var(--border-strong); border-radius: 6px; }
.add-btn {
  font-size: 13px; padding: 7px 14px; border: none; border-radius: 6px;
  background: var(--accent); color: var(--on-accent); font-weight: 600; cursor: pointer;
}
.add-btn:disabled { opacity: 0.5; cursor: default; }
.empty { color: var(--faint); font-size: 13px; }
.node-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.node-name { font-size: 13px; font-weight: 500; }
.citation { font-size: 12px; color: var(--text-2); }
.link-row { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border: 1px solid var(--border); border-radius: 6px; flex-wrap: wrap; }
.link-chips { display: flex; gap: 6px; flex-wrap: wrap; flex: 1; }
.chip {
  font-size: 11px; background: var(--indigo-soft); color: var(--indigo-text); padding: 2px 8px; border-radius: 10px; }
.relation-select { font-size: 12px; padding: 4px 8px; border: 1px solid var(--border-strong); border-radius: 5px; }
</style>
