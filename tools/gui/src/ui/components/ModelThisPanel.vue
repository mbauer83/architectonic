<script setup lang="ts">
import { ref } from 'vue'
import {
  MODELABLE_ARCH_TYPES,
  emptyModelThisForm,
  modelThisBody,
  parseBindOutcome,
  type BindOutcome,
} from './ModelThisPanel.helpers'

const props = defineProps<{ nodeId: string; nodeName: string }>()
const emit = defineEmits<{ bound: [] }>()

const form = ref(emptyModelThisForm(props.nodeName))
const outcome = ref<BindOutcome | null>(null)
const busy = ref(false)

async function modelAndBind() {
  if (!form.value.name.trim()) { outcome.value = { kind: 'error', message: 'Name is required.' }; return }
  busy.value = true
  outcome.value = null
  try {
    const resp = await fetch('/api/assurance/model-this', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(modelThisBody(props.nodeId, form.value)),
    })
    const body = await resp.json().catch(() => ({})) as Record<string, unknown>
    const result = parseBindOutcome(resp.status, body)
    outcome.value = result
    if (result.kind === 'bound') emit('bound')
  } catch (e) {
    outcome.value = { kind: 'error', message: String(e) }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="model-this">
    <p class="mt-title">
      ⚠ Modelling gap — not bound to architecture
    </p>
    <p class="mt-hint">
      This control-structure node has no architecture element. Model it now (creates the
      element and binds it), or create a task for an architecture-write session.
    </p>
    <div class="mt-form">
      <label class="mt-label">As
        <select
          v-model="form.archType"
          class="mt-select"
          aria-label="Architecture type"
        >
          <option
            v-for="t in MODELABLE_ARCH_TYPES"
            :key="t"
            :value="t"
          >
            {{ t }}
          </option>
        </select>
      </label>
      <input
        v-model="form.name"
        class="mt-input"
        placeholder="Architecture element name"
        aria-label="Architecture element name"
      >
    </div>
    <label class="mt-check">
      <input
        v-model="form.separationOfDuties"
        type="checkbox"
      >
      I don't have architecture-write access — create a task instead (separation of duties)
    </label>
    <button
      class="mt-btn"
      type="button"
      :disabled="busy"
      @click="modelAndBind"
    >
      Model &amp; bind
    </button>
    <p
      v-if="outcome"
      class="mt-outcome"
      :class="`mt-outcome--${outcome.kind}`"
    >
      {{ outcome.message }}
    </p>
  </div>
</template>

<style scoped>
.model-this { border: 1px solid #fcd34d; background: #fffbeb; border-radius: 8px; padding: 12px 14px; display: flex; flex-direction: column; gap: 8px; }
.mt-title { font-size: 13px; font-weight: 700; color: #b45309; margin: 0; }
.mt-hint { font-size: 12px; color: #92400e; margin: 0; }
.mt-form { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.mt-label { font-size: 12px; color: #475569; display: flex; align-items: center; gap: 6px; }
.mt-select { font-size: 12px; padding: 5px 8px; border: 1px solid #cbd5e1; border-radius: 5px; }
.mt-input { flex: 1; min-width: 160px; font-size: 12px; padding: 6px 8px; border: 1px solid #cbd5e1; border-radius: 5px; }
.mt-check { font-size: 12px; color: #475569; display: flex; align-items: center; gap: 6px; }
.mt-btn {
  align-self: flex-start; font-size: 12px; padding: 6px 14px; border: none; border-radius: 6px;
  background: #b45309; color: #fff; font-weight: 600; cursor: pointer;
}
.mt-btn:disabled { opacity: 0.5; cursor: default; }
.mt-outcome { font-size: 12px; margin: 0; font-weight: 600; }
.mt-outcome--bound { color: #15803d; }
.mt-outcome--task { color: #1d4ed8; }
.mt-outcome--error { color: #b91c1c; }
</style>
