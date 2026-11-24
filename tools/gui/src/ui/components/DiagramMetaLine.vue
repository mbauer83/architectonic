<script setup lang="ts">
/** The line under a diagram's title: its kind, status, version and id, and while editing, that nothing is saved yet. */
import type { DiagramDetail } from '../../domain'

defineProps<{ detail: DiagramDetail; editing: boolean }>()
</script>

<template>
  <div class="meta">
    <span class="type-badge">{{ detail.diagram_type.replace('archimate-', '') }}</span>
    <span
      class="status-badge"
      :class="`status--${detail.status}`"
    >{{ detail.status }}</span>
    <span class="mono faded">v{{ detail.version }} · {{ detail.artifact_id }}</span>
    <span
      v-if="editing"
      class="editing-note"
      data-testid="editing-note"
    >Editing — nothing is saved until you press Save · <em>Done</em> or <kbd>Esc</kbd> leaves</span>
  </div>
</template>

<style scoped>
.meta { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; font-size: 12px; }
.faded { color: var(--faint); } .mono { font-family: monospace; }
.type-badge {
  padding: 2px 8px; border-radius: 4px; font-size: 11px; background: var(--type-soft); color: var(--type-text);
  font-weight: 500;
}
.editing-note { color: var(--accent-strong); font-weight: 600; }
.editing-note kbd {
  font: 10px ui-monospace, monospace; padding: 0 4px; border: 1px solid var(--border-strong);
  border-bottom-width: 2px; border-radius: 3px; background: var(--surface);
}
</style>
