<script setup lang="ts">
/** GRC wizard's "Obligations" step: add-obligation form (name + citation scheme/code) +
 * obligation list, each linkable to the controls that comply with it. */
import { inject, ref } from 'vue'
import { grcWizardDataKey } from '../composables/useGrcWizardData'

const data = inject(grcWizardDataKey)!

const newObligation = ref({ name: '', scheme: '', code: '' })

const addObligation = async () => {
  const attrs: Record<string, string> = {}
  if (newObligation.value.scheme.trim()) attrs['scheme'] = newObligation.value.scheme.trim()
  if (newObligation.value.code.trim()) attrs['code'] = newObligation.value.code.trim()
  const id = await data.createNode('obligation', newObligation.value.name, attrs)
  if (id) { newObligation.value = { name: '', scheme: '', code: '' }; await data.loadNodes() }
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
        v-model="newObligation.scheme"
        class="cite-input"
        placeholder="scheme"
        aria-label="Citation scheme"
      >
      <input
        v-model="newObligation.code"
        class="cite-input"
        placeholder="code"
        aria-label="Citation code"
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
.add-input { flex: 1; min-width: 200px; font-size: 13px; padding: 7px 10px; border: 1px solid #cbd5e1; border-radius: 6px; }
.cite-input { width: 90px; font-size: 13px; padding: 7px 10px; border: 1px solid #cbd5e1; border-radius: 6px; }
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
