<script setup lang="ts">
/** The note that says once what the naive architecture is, as it is first sketched after the start (06·0). */
const emit = defineEmits<{ dismiss: [] }>()
</script>

<template>
  <p
    class="intro"
    role="note"
    data-testid="naive-intro"
  >
    <span>This is the <b>naive architecture</b>: the architecture under evaluation as it stands before
      any stressor, and the first candidate architecture of this analysis. Sketch it as you would a
      diagram; every change is one of its operations, listed on the left, and nothing reaches the
      model before it is applied. When it is done, the stressors are written against it.</span>
    <button
      type="button"
      class="btn btn-sm"
      @click="emit('dismiss')"
    >
      Understood
    </button>
  </p>
</template>

<style scoped>
.intro {
  display: flex; gap: 10px; align-items: flex-start; margin: 0 0 8px; padding: 8px 10px; font-size: 12.5px;
  border: 1px solid var(--accent-border); background: var(--accent-soft); border-radius: 6px; color: var(--text);
}
.intro .btn { flex: none; }
</style>
