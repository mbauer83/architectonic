<script setup lang="ts">
/**
 * Writing a stressor: one free-text line, kept with `Enter`. Nothing else is asked. Under it the
 * perspectives line, a thinking aid only; a perspective chosen there puts its kind on the stressor,
 * shown beside the line and taken off with ×.
 *
 * The line is never closed while an earlier one is being written: each kept line is handed on at once
 * and the analysis writes them one after another (`useStressAnalysis`), so lines kept in quick
 * succession are all written, in the order they were kept.
 */
import { computed, inject, ref } from 'vue'
import type { StressPerspective } from '../../../domain/schemas/stressEvaluation'
import { modelServiceKey } from '../../keys'
import { usePerspectives } from '../../composables/usePerspectives'
import PerspectivesLine from './PerspectivesLine.vue'

const props = defineProps<{
  /** The perspectives no stressor of this set is written from, by id, as the server reads them. */
  unwritten: readonly string[]
  placeholder: string
}>()
const emit = defineEmits<{ write: [text: string, kind: string | undefined] }>()

const frameworks = usePerspectives(inject(modelServiceKey)!)
const text = ref('')
const chosen = ref<StressPerspective | null>(null)
const open = computed(() => new Set(props.unwritten))

const keep = () => {
  const written = text.value.trim()
  if (!written) return
  emit('write', written, chosen.value?.kind)
  text.value = ''
  chosen.value = null
}
</script>

<template>
  <div class="stressor-input">
    <div class="line">
      <input
        v-model="text"
        class="in"
        :placeholder="placeholder"
        :aria-label="placeholder"
        data-testid="stressor-input"
        @keydown.enter.prevent="keep"
      >
      <span
        v-if="chosen"
        class="kind"
        :title="chosen.question"
      >{{ chosen.kind }}<button
        type="button"
        class="drop"
        :aria-label="`Do not set kind ${chosen.kind}`"
        @click="chosen = null"
      >×</button></span>
    </div>
    <PerspectivesLine
      :frameworks="frameworks"
      :unwritten="open"
      :chosen="chosen?.id ?? null"
      @choose="chosen = $event"
    />
  </div>
</template>

<style scoped>
.line { display: flex; gap: 6px; align-items: center; padding: 8px 10px 2px; }
.in {
  flex: 1; min-width: 0; font: inherit; font-size: 12.5px; padding: 5px 8px;
  border: 1px solid var(--border-strong); border-radius: 6px; background: var(--surface); color: var(--text);
}
.in:focus { outline: 2px solid var(--accent-soft); border-color: var(--accent); }
.kind {
  font-size: 11px; color: var(--accent-strong); background: var(--accent-soft); border-radius: 3px;
  padding: 1px 2px 1px 7px; white-space: nowrap;
}
.drop { border: none; background: none; color: inherit; cursor: pointer; font: inherit; padding: 0 4px; }
</style>
