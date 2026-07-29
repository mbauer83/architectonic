<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{ diagramId: string; diagramName: string }>()
const open = ref(false)

const download = (format: 'png' | 'svg') => {
  open.value = false
  window.location.href = `/api/diagram-download?id=${encodeURIComponent(props.diagramId)}&format=${format}`
}
</script>

<template>
  <div class="dl-wrap">
    <button
      class="dl-btn"
      title="Download"
      @click.stop.prevent="open = !open"
    >
      ↓
    </button>
    <div
      v-if="open"
      class="dl-overlay"
      @click.stop="open = false"
    />
    <div
      v-if="open"
      class="dl-dropdown"
    >
      <button
        class="dl-opt"
        @click.stop="download('svg')"
      >
        SVG
      </button>
      <button
        class="dl-opt"
        @click.stop="download('png')"
      >
        PNG
      </button>
    </div>
  </div>
</template>

<style scoped>
.dl-wrap { position: relative; display: inline-block; }
.dl-btn {
  padding: 3px 8px; border-radius: 4px; border: 1px solid #d1d5db;
  background: white; font-size: 12px; cursor: pointer; color: #6b7280; line-height: 1.4;
}
.dl-btn:hover { background: #f9fafb; color: #374151; }
.dl-overlay { position: fixed; inset: 0; z-index: 10; }
.dl-dropdown {
  position: absolute; right: 0; top: calc(100% + 4px); z-index: 11;
  background: white; border: 1px solid #e5e7eb; border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0,0,0,.1); min-width: 90px; overflow: hidden;
}
.dl-opt {
  display: block; width: 100%; text-align: left; padding: 7px 12px;
  background: none; border: none; font-size: 13px; cursor: pointer; color: #374151;
}
.dl-opt:hover { background: #f9fafb; }
</style>
