<script setup lang="ts">
interface Toast {
  id: number
  message: string
  type: 'info' | 'warn' | 'error'
}

defineProps<{
  toasts: Toast[]
}>()
</script>

<template>
  <div class="toast-stack">
    <div
      v-for="toast in toasts"
      :key="toast.id"
      class="toast"
      :class="`toast--${toast.type}`"
    >
      {{ toast.message }}
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
