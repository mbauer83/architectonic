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
.note-header { display: flex; align-items: center; gap: 6px; font-size: 11px; color: #6b7280; }
.note-header button, .add-note { font-size: 11px; color: #92400e; background: none; border: 1px dashed #fde68a; border-radius: 4px; padding: 2px 7px; cursor: pointer; }
.note-header button { color: #9ca3af; border-style: solid; }
textarea { width: 100%; resize: vertical; font: inherit; font-size: 12px; padding: 4px 6px; border: 1px solid #fde68a; border-radius: 4px; background: #fffbeb; box-sizing: border-box; }
</style>
