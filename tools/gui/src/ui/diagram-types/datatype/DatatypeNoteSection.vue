<script setup lang="ts">
defineProps<{ note?: string }>()
const emit = defineEmits<{ update: [note: string | undefined] }>()
</script>

<template>
  <div class="note-section">
    <template v-if="note !== undefined">
      <div class="note-header">
        <span>Note</span>
        <button
          type="button"
          @click="emit('update', undefined)"
        >
          × Remove note
        </button>
      </div>
      <textarea
        rows="2"
        placeholder="Note text…"
        :value="note"
        @input="emit('update', ($event.target as HTMLTextAreaElement).value)"
      />
    </template>
    <button
      v-else
      class="add-note"
      type="button"
      @click="emit('update', '')"
    >
      + Note
    </button>
  </div>
</template>

<style scoped>
.note-section { display: flex; flex-direction: column; gap: 4px; }
.note-header { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--muted); }
.note-header button, .add-note { font-size: 11px; color: var(--warn-text); background: none; border: 1px dashed var(--warn-border); border-radius: 4px; padding: 2px 7px; cursor: pointer; }
.note-header button { color: var(--faint); border-style: solid; }
textarea { width: 100%; resize: vertical; font: inherit; font-size: 12px; padding: 4px 6px; border: 1px solid var(--warn-border); border-radius: 4px; background: var(--warn-soft); box-sizing: border-box; }
</style>
