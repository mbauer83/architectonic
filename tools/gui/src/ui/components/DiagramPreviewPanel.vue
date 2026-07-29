<script setup lang="ts">
/** Diagram-edit view's preview-result row: loading/error/warnings, the rendered preview
 * image (pan/zoomable), and a toggle for the raw PUML source. Pure display over a
 * `useMutation` result. */
import { ref } from 'vue'
import type { DiagramPreviewResult } from '../../domain'
import PreviewViewport from './PreviewViewport.vue'

defineProps<{
  running: boolean
  errorMessage: string | null
  result: DiagramPreviewResult | null
}>()

const showPuml = ref(false)
</script>

<template>
  <div
    v-if="running || errorMessage || result"
    class="preview-row"
  >
    <div
      v-if="running"
      class="state-msg"
    >
      Rendering preview…
    </div>
    <div
      v-if="errorMessage"
      class="state-err"
    >
      {{ errorMessage }}
    </div>
    <template v-if="result">
      <div
        v-for="w in result.warnings"
        :key="w"
        class="warn-msg"
      >
        {{ w }}
      </div>
      <PreviewViewport
        v-if="result.image"
        :reset-signal="result"
      >
        <img
          :src="result.image"
          class="preview-img"
          alt="Preview"
          draggable="false"
        >
      </PreviewViewport>
      <div
        v-else
        class="state-msg"
      >
        No image rendered.
      </div>
      <button
        class="toggle-src"
        @click="showPuml = !showPuml"
      >
        {{ showPuml ? 'Hide' : 'Show' }} PUML
      </button>
      <pre
        v-if="showPuml"
        class="puml-src"
      >{{ result.puml }}</pre>
    </template>
  </div>
</template>

<style scoped>
.preview-row { margin-top: 16px; }
.state-msg { font-size: 13px; color: #6b7280; }
.state-err { font-size: 13px; color: #dc2626; margin-top: 6px; }
.warn-msg { font-size: 12px; color: #b45309; margin-bottom: 4px; }
.preview-img { max-width: none; display: block; }
.toggle-src { margin-top: 10px; font-size: 12px; color: #2563eb; background: none; border: none; cursor: pointer; padding: 0; }
.puml-src { font-size: 11px; font-family: monospace; white-space: pre-wrap; margin-top: 8px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px; max-height: 400px; overflow-y: auto; }
</style>
