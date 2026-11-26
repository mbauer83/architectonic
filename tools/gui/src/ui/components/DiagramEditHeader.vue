<script setup lang="ts">
/** Diagram-edit view's top bar: back link, title/type badge, and the preview/save action
 * pair (mirrored again at the bottom of the sidebar — same emitted events drive both). */
defineProps<{
  diagramName: string | null
  diagramTypeLabel: string | null
  loading: boolean
  previewRunning: boolean
  previewDisabled: boolean
  saveRunning: boolean
  saveDisabled: boolean
  saveTitle: string
}>()
const emit = defineEmits<{ back: []; preview: []; save: [] }>()
</script>

<template>
  <div class="page-hdr">
    <button
      class="back-link"
      @click="emit('back')"
    >
      ← Back
    </button>
    <div class="hdr-info">
      <h1 class="pg-title">
        <span
          v-if="loading"
          class="faded"
        >Loading…</span>
        <span v-else-if="diagramName">{{ diagramName }}</span>
      </h1>
      <span
        v-if="diagramTypeLabel"
        class="type-badge"
      >
        {{ diagramTypeLabel }}
      </span>
    </div>
    <div class="hdr-actions">
      <button
        class="btn-preview"
        :disabled="previewDisabled"
        @click="emit('preview')"
      >
        {{ previewRunning ? 'Rendering…' : 'Preview' }}
      </button>
      <button
        class="btn-save"
        :disabled="saveDisabled"
        :title="saveTitle"
        @click="emit('save')"
      >
        {{ saveRunning ? 'Saving…' : 'Save Changes' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.page-hdr { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.hdr-actions { display: flex; gap: 8px; margin-left: auto; }
.back-link { font-size: 13px; color: var(--muted); background: none; border: none; cursor: pointer; padding: 0; flex-shrink: 0; }
.back-link:hover { color: var(--text-2); }
.hdr-info { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; }
.pg-title { font-size: 20px; font-weight: 700; margin: 0; min-width: 0; overflow-wrap: anywhere; }
.faded { color: var(--faint); font-weight: 400; }
.type-badge { padding: 2px 8px; border-radius: 4px; font-size: 11px; background: var(--type-soft); color: var(--type-text); font-weight: 500; flex-shrink: 0; }
.btn-preview { padding: 7px 12px; background: var(--soft); color: var(--accent-strong); border: 1px solid var(--accent-border); border-radius: 6px; font-size: 13px; cursor: pointer; font-weight: 500; }
.btn-preview:hover:not(:disabled) { background: var(--accent-soft); }
.btn-save { padding: 7px 12px; background: var(--accent); color: var(--on-accent); border: none; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; }
.btn-save:hover:not(:disabled) { background: var(--accent-strong); }
.btn-preview:disabled, .btn-save:disabled { opacity: .5; cursor: not-allowed; }
</style>
