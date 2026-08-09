<script setup lang="ts">
/**
 * The chrome around the canvas: what this scratchpad is, what state it is in, and the two controls
 * that act on the whole of it.
 *
 * Its own component because the view was past the source-length limit and this is the seam that was
 * already there — the canvas draws the document, this says what the document *is*. It holds no
 * state: undo, redo and leaving focus are events, because the history and the mode belong to the
 * view that owns the save policy.
 */
defineProps<{
  name: string
  artifactId: string
  group: string
  noteCount: number
  canUndo: boolean
  canRedo: boolean
  focused: boolean
  status: string
  failed: boolean
}>()

const emit = defineEmits<{
  (event: 'undo'): void
  (event: 'redo'): void
  (event: 'leave-focus'): void
}>()
</script>

<template>
  <header class="bar">
    <div>
      <h1
        class="title"
        data-testid="scratchpad-name"
      >
        {{ name }}
      </h1>
      <p class="sub">
        <span class="mono">{{ artifactId }}</span>
        <span class="dot">·</span>{{ noteCount }} note{{ noteCount === 1 ? '' : 's' }}
        <span class="dot">·</span><span class="mono">{{ group }}</span>
      </p>
    </div>
    <div class="actions">
      <button
        type="button"
        :disabled="!canUndo"
        data-testid="undo"
        @click="emit('undo')"
      >
        Undo
      </button>
      <button
        type="button"
        :disabled="!canRedo"
        data-testid="redo"
        @click="emit('redo')"
      >
        Redo
      </button>
      <button
        v-if="focused"
        type="button"
        data-testid="leave-focus"
        @click="emit('leave-focus')"
      >
        Leave focus
      </button>
      <span
        class="state"
        :class="{ err: failed }"
        data-testid="save-state"
      >{{ status }}</span>
    </div>
  </header>
</template>

<style scoped>
.bar { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.title { font-size: 20px; margin: 0 0 2px; }
.sub { margin: 0; font-size: 12px; color: #6b7280; }
.mono { font-family: ui-monospace, monospace; }
.dot { margin: 0 6px; color: #d1d5db; }
.actions { display: flex; align-items: center; gap: 8px; }
.actions button {
  padding: 5px 12px; border: 1px solid #d1d5db; border-radius: 6px; background: #fff;
  font-size: 13px; cursor: pointer; color: #374151;
}
.actions button:disabled { opacity: .45; cursor: default; }
.actions button:not(:disabled):hover { background: #f9fafb; }
.state { font-size: 12px; color: #6b7280; min-width: 96px; text-align: right; }
.state.err { color: #dc2626; }
</style>
