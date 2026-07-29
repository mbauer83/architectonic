<script setup lang="ts">
/**
 * Always-visible execution controls for a parameterised viewpoint.
 *
 * Distinct from the one-shot prompt: it stays on screen after the first run — even when every
 * parameter is defaulted — so a result can be re-cut (different scope, gaps-only, a group
 * filter) without a modal. It opens reflecting the values the current result actually ran
 * with, so a reloaded shared URL shows its own selection rather than the bare defaults.
 * Renders only when the definition declares parameters; execution + URL state stay with the
 * page (this emits the wire-shaped values and nothing else).
 */
import { ref, watch } from 'vue'

import type { QueryParameterNode } from '../../domain/viewpointBindings'
import {
  draftFromWireValues,
  missingRequiredParameters,
  type ParameterDraft,
  type ParameterDraftValue,
  parametersToWireValues,
} from '../lib/viewpointExecutionParameters'
import ViewpointParameterControl from './ViewpointParameterControl.vue'

const props = defineProps<{
  parameters: readonly QueryParameterNode[]
  boundValues: Readonly<Record<string, unknown>>
}>()
const emit = defineEmits<{ apply: [parameters: Record<string, unknown>] }>()

const draft = ref<ParameterDraft>(draftFromWireValues(props.parameters, props.boundValues))
// Re-seed when the execution the toolbar reflects changes underneath it (slug switch, a URL
// reload) — but not on every keystroke, so an in-progress edit is never clobbered.
watch(
  () => [props.parameters, props.boundValues] as const,
  () => { draft.value = draftFromWireValues(props.parameters, props.boundValues) },
)

const setValue = (name: string, value: ParameterDraftValue) => { draft.value = { ...draft.value, [name]: value } }
const missing = () => missingRequiredParameters(props.parameters, draft.value)
const apply = () => { if (missing().length === 0) emit('apply', parametersToWireValues(props.parameters, draft.value)) }
</script>

<template>
  <form
    v-if="parameters.length > 0"
    class="vp-toolbar"
    aria-label="Viewpoint parameters"
    @submit.prevent="apply"
  >
    <div
      v-for="parameter in parameters"
      :key="parameter.name"
      class="vp-toolbar-field"
    >
      <label :for="`vp-param-${parameter.name}`">
        {{ parameter.name }}<span
          v-if="parameter.required"
          class="vp-req"
        > *</span>
      </label>
      <ViewpointParameterControl
        :parameter="parameter"
        :value="draft[parameter.name] ?? ''"
        @update="(value) => setValue(parameter.name, value)"
      />
    </div>
    <button
      type="submit"
      class="vp-apply"
      :disabled="missing().length > 0"
      :title="missing().length > 0
        ? `Still needed: ${missing().map((p) => p.name).join(', ')}`
        : 'Re-run with these parameters'"
    >
      Apply
    </button>
  </form>
</template>

<style scoped>
.vp-toolbar {
  display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px 18px;
  padding: 10px 14px; margin-bottom: 12px; background: #f9fafb;
  border: 1px solid #e5e7eb; border-radius: 8px;
}
.vp-toolbar-field { display: flex; flex-direction: column; gap: 4px; }
.vp-toolbar-field label {
  font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: #6b7280;
}
.vp-req { color: #b91c1c; }
.vp-apply {
  padding: 6px 16px; border-radius: 7px; border: none; background: #6366f1; color: #fff;
  font-size: 13px; font-weight: 600; cursor: pointer;
}
.vp-apply:disabled { opacity: .5; cursor: not-allowed; }
</style>
