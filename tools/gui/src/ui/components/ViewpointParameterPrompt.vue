<script setup lang="ts">
/**
 * Parameter-prompt dialog: shown before the first execution of a definition that
 * declares at least one required parameter with no default. Typed inputs per declared
 * `value_type` — no free-text escape hatch for anything but `string`/`slug`; `entity-id`
 * reuses the existing entity picker rather than a raw id text field.
 */
import { ref, watch } from 'vue'
import type { QueryParameterNode } from '../../domain/viewpointBindings'
import {
  initialParameterDraft,
  missingRequiredParameters,
  type ParameterDraft,
  type ParameterDraftValue,
} from '../lib/viewpointExecutionParameters'
import ViewpointParameterControl from './ViewpointParameterControl.vue'

const props = defineProps<{ parameters: readonly QueryParameterNode[] }>()
const emit = defineEmits<{ submit: [draft: ParameterDraft]; cancel: [] }>()

const draft = ref<ParameterDraft>(initialParameterDraft(props.parameters))
watch(() => props.parameters, (parameters) => { draft.value = initialParameterDraft(parameters) })

const setValue = (name: string, value: ParameterDraftValue) => { draft.value = { ...draft.value, [name]: value } }
const missing = () => missingRequiredParameters(props.parameters, draft.value)
const onSubmit = () => { if (missing().length === 0) emit('submit', draft.value) }
</script>

<template>
  <div class="prompt-backdrop">
    <div
      class="prompt-panel"
      role="dialog"
      aria-label="Viewpoint parameters"
    >
      <h2>This viewpoint takes parameters</h2>
      <div
        v-for="parameter in parameters"
        :key="parameter.name"
        class="param-field"
      >
        <label :for="`vp-param-${parameter.name}`">
          {{ parameter.name }}<span v-if="parameter.required"> (required)</span>
        </label>
        <p
          v-if="parameter.description"
          class="param-desc"
        >
          {{ parameter.description }}
        </p>

        <ViewpointParameterControl
          :parameter="parameter"
          :value="draft[parameter.name] ?? ''"
          @update="(value) => setValue(parameter.name, value)"
        />
      </div>

      <p
        v-if="missing().length > 0"
        class="missing-hint"
      >
        Still needed: {{ missing().map((p) => p.name).join(', ') }}.
      </p>

      <div class="prompt-actions">
        <button
          type="button"
          @click="emit('cancel')"
        >
          Cancel
        </button>
        <button
          type="button"
          class="primary-btn"
          :disabled="missing().length > 0"
          @click="onSubmit"
        >
          Run
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.prompt-backdrop { position: fixed; inset: 0; background: rgba(17, 24, 39, .4); display: flex; align-items: center; justify-content: center; z-index: 50; }
.prompt-panel { background: #fff; border-radius: 10px; padding: 20px 24px; min-width: 340px; max-width: 480px; box-shadow: 0 10px 30px rgba(0,0,0,.2); }
.prompt-panel h2 { font-size: 15px; margin: 0 0 12px; }
.param-field { margin: 10px 0; display: flex; flex-direction: column; gap: 4px; }
.param-field label { font-size: 12.5px; font-weight: 600; color: #374151; }
.param-desc { font-size: 11.5px; color: #6b7280; margin: 0; }
.param-field input { padding: 6px 8px; border-radius: 6px; border: 1px solid #d1d5db; font-size: 13px; font-family: inherit; }
.selected-hint { font-size: 11.5px; color: #4338ca; }
.selected-id { font-size: 10.5px; color: #9ca3af; margin-left: 4px; font-family: monospace; }
.missing-hint { font-size: 12px; color: #92400e; background: #fef3c7; padding: 6px 10px; border-radius: 6px; }
.prompt-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
/* Shape here, colour on the variants: `.prompt-actions button` outranks a bare `.primary-btn`,
   so a white background declared in the shared rule beat the accent one and left the confirm
   button's white label on white. Nothing in this block may set the colour of both. */
.prompt-actions button { padding: 6px 14px; border-radius: 7px; font-size: 13px; cursor: pointer; }
.prompt-actions button:not(.primary-btn) { border: 1px solid #d1d5db; background: #fff; color: #374151; }
.prompt-actions .primary-btn { background: #6366f1; color: #fff; border: none; font-weight: 600; }
.prompt-actions .primary-btn:hover:not(:disabled) { background: #4f46e5; }
.prompt-actions .primary-btn:disabled { opacity: .5; cursor: not-allowed; }
</style>
