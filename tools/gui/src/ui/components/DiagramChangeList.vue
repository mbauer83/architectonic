<script setup lang="ts">
/**
 * What Save will write (sketch 01·6), in two groups headed in words rather than told apart by colour:
 * **Model** — what every diagram drawing these elements sees — and **Diagram** — what changes on this
 * diagram only, its arranging as the one line "Layout changed" (owner, 2026-11-25). A group with nothing
 * in it is not shown.
 */
import { computed } from 'vue'
import type { PendingChange } from '../../domain/layout/sessionChanges'
import { byWhatTheyChange } from '../../domain/layout/sessionSteps'

const props = defineProps<{
  changes: readonly PendingChange[]
  /** Whether Save waits on this list: a button confirms it. */
  confirming: boolean
  saving: boolean
}>()
const emit = defineEmits<{ confirm: [] }>()

const groups = computed(() => byWhatTheyChange(props.changes))
const plural = (count: number): string => `${count} change${count === 1 ? '' : 's'}`
</script>

<template>
  <div
    class="pop"
    role="dialog"
    aria-label="What Save will write"
    data-testid="change-list"
  >
    <h3>Save will write</h3>
    <template v-if="groups.model.length">
      <p
        class="group"
        data-testid="change-group-model"
      >
        <span class="tag tag--model">Model</span> {{ plural(groups.model.length) }} to the model — every diagram
        that draws these sees them
      </p>
      <ul>
        <li
          v-for="change in groups.model"
          :key="change.key"
        >
          {{ change.text }}
        </li>
      </ul>
    </template>
    <template v-if="groups.diagram.length">
      <p
        class="group"
        data-testid="change-group-diagram"
      >
        <span class="tag">Diagram</span> {{ plural(groups.diagram.length) }} to this diagram only
      </p>
      <ul>
        <li
          v-for="change in groups.diagram"
          :key="change.key"
        >
          {{ change.text }}
        </li>
      </ul>
    </template>
    <p
      v-if="groups.model.length"
      class="note"
    >
      Model and diagram are written together: if the model refuses one change, nothing is written and you are
      told why.
    </p>
    <p
      v-else
      class="note"
    >
      Only this diagram changes. The model is not touched.
    </p>
    <button
      v-if="confirming"
      type="button"
      :disabled="saving"
      @click="emit('confirm')"
    >
      Confirm and save
    </button>
  </div>
</template>

<style scoped>
.pop {
  position: absolute; right: 0; top: calc(100% + 6px); z-index: 20; width: 400px; padding: 10px 12px;
  background: var(--surface); border: 1px solid var(--border-strong); border-radius: 8px; box-shadow: var(--shadow);
  color: var(--text);
}
h3 { font-size: 13px; margin: 0 0 6px; }
.group { font-weight: 600; margin: 0 0 4px; }
.tag {
  background: var(--soft); color: var(--text-2); border-radius: 3px; padding: 1px 6px; font-size: 11px;
  margin-right: 4px;
}
.tag--model { background: var(--warn-soft); color: var(--warn-text); }
ul { margin: 0 0 6px 16px; padding: 0; }
li { margin-bottom: 3px; }
.note { margin: 4px 0 6px; color: var(--muted); font-size: 11.5px; }
</style>
