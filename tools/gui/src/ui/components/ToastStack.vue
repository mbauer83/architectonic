<script setup lang="ts">
import type { ToastAction } from '../keys'

interface Toast {
  id: number
  message: string
  type: 'info' | 'warn' | 'error'
  action?: ToastAction
}

defineProps<{
  toasts: Toast[]
}>()
const emit = defineEmits<{ close: [id: number] }>()

/** A toast's action runs once and closes it. */
const act = (toast: Toast) => {
  toast.action?.run()
  emit('close', toast.id)
}
</script>

<template>
  <div class="toast-stack">
    <div
      v-for="toast in toasts"
      :key="toast.id"
      class="toast"
      :class="`toast--${toast.type}`"
      role="status"
    >
      {{ toast.message }}
      <button
        v-if="toast.action"
        type="button"
        class="toast-action"
        @click="act(toast)"
      >
        {{ toast.action.label }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.toast-stack {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: 12px;
  pointer-events: none;
}

.toast {
  padding: 12px 16px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.5;
  max-width: 360px;
  pointer-events: auto;
  animation: slideIn 0.3s ease-out;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.toast--info {
  background: #f1f5f9;
  color: #334155;
  border-left: 3px solid #3b82f6;
}

.toast--warn {
  background: #fef3c7;
  color: #92400e;
  border-left: 3px solid #f59e0b;
}

.toast--error {
  background: #fee2e2;
  color: #991b1b;
  border-left: 3px solid #ef4444;
}

.toast-action {
  margin-left: 10px;
  border: 1px solid currentColor;
  background: transparent;
  color: inherit;
  border-radius: 4px;
  padding: 1px 8px;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}

/* A reader who asked for less motion still sees the toast arrive, without the travel. */
@media (prefers-reduced-motion: reduce) {
  .toast { animation: none; }
}
@keyframes slideIn {
  from {
    transform: translateX(400px);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}
</style>
