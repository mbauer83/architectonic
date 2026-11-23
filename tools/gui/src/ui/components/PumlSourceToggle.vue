<script setup lang="ts">
/** A diagram's PlantUML source, folded away until asked for. Whether it is open is this toggle's business. */
import { ref } from 'vue'

defineProps<{ source: string }>()
const open = ref(false)
</script>

<template>
  <div class="src-row">
    <button
      type="button"
      class="toggle-btn"
      :aria-expanded="open"
      @click="open = !open"
    >
      {{ open ? 'Hide' : 'Show' }} PUML source
    </button>
    <pre
      v-if="open"
      class="puml-src"
    >{{ source }}</pre>
  </div>
</template>

<style scoped>
.src-row { margin-top: 16px; }
.toggle-btn {
  padding: 5px 14px; border-radius: 6px; border: 1px solid #d1d5db; background: white; font-size: 13px;
  cursor: pointer; color: #374151; margin-bottom: 8px;
}
.toggle-btn:hover { background: #f9fafb; }
.puml-src {
  background: #1e293b; color: #e2e8f0; padding: 16px; border-radius: 8px; font-size: 12px; line-height: 1.5;
  overflow-x: auto; white-space: pre;
}
</style>
