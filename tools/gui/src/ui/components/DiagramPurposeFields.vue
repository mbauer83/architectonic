<script setup lang="ts">
/** Who this diagram is for and what it answers, edited as two lists. Empty lists show the viewpoint's. */
import type { PurposeEntry } from '../../domain/purposeLines'
import PurposeEntryListEditor from './PurposeEntryListEditor.vue'

defineProps<{
  stakeholders: readonly PurposeEntry[]
  concerns: readonly PurposeEntry[]
  names: Readonly<Record<string, string>>
}>()
const emit = defineEmits<{
  'update:stakeholders': [value: PurposeEntry[]]
  'update:concerns': [value: PurposeEntry[]]
}>()
</script>

<template>
  <section
    class="purpose-fields"
    data-testid="diagram-purpose-fields"
  >
    <h4>Purpose</h4>
    <PurposeEntryListEditor
      :model-value="stakeholders"
      label="For"
      prose-hint="a stakeholder, in words"
      :names="names"
      @update:model-value="emit('update:stakeholders', $event)"
    />
    <PurposeEntryListEditor
      :model-value="concerns"
      label="Answers"
      prose-hint="a question this view answers"
      :names="names"
      @update:model-value="emit('update:concerns', $event)"
    />
    <p class="hint">
      Leave a list empty to show the applied viewpoint's.
    </p>
  </section>
</template>

<style scoped>
.purpose-fields { margin: 12px 0; }
.purpose-fields h4 { margin: 0 0 6px; font-size: 13px; }
.hint { font-size: 11px; color: var(--faint); margin: 0; }
</style>
