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
  padding: 5px 14px; border-radius: 6px; border: 1px solid var(--border-strong); background: var(--surface);
  font-size: 13px;
  cursor: pointer; color: var(--text-2); margin-bottom: 8px;
}
.toggle-btn:hover { background: var(--hover); }
.puml-src {
  background: var(--code-bg); color: var(--code-text); padding: 16px; border-radius: 8px; font-size: 12px;
  line-height: 1.5;
  overflow-x: auto; white-space: pre;
}
</style>
