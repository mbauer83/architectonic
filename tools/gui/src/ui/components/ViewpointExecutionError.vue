<script setup lang="ts">
/**
 * A distinct, actionable error state for a failed viewpoint execution — never a phantom
 * empty result. Renders the typed `{code, path, message}` body when the failure carried
 * one (parameter/timeout/derivation-limit/cardinality errors), falling back to the flat
 * message for anything else (a network error, an unrecognized code).
 */
import { computed } from 'vue'
import type { TypedApiError } from '../lib/errors'
import { executionErrorDisplay } from '../lib/viewpointExecutionErrorText'

const props = defineProps<{ typedError: TypedApiError | null; fallbackMessage: string }>()
const emit = defineEmits<{ retry: [] }>()

const display = computed(() => (props.typedError ? executionErrorDisplay(props.typedError) : null))
</script>

<template>
  <div class="exec-error">
    <p class="exec-error-title">
      {{ display?.title ?? 'Execution failed' }}
    </p>
    <p class="exec-error-detail">
      {{ display?.detail ?? fallbackMessage }}
    </p>
    <button
      type="button"
      class="retry-btn"
      @click="emit('retry')"
    >
      ↻ Retry
    </button>
  </div>
</template>

<style scoped>
.exec-error { color: #991b1b; background: #fee2e2; padding: 10px 14px; border-radius: 8px; margin: 8px 0; }
.exec-error-title { font-weight: 700; margin: 0 0 4px; font-size: 13px; }
.exec-error-detail { margin: 0 0 8px; font-size: 12.5px; }
.retry-btn { appearance: none; border: 1px solid #991b1b; border-radius: 6px; background: #fff; color: #991b1b; font-size: 12px; padding: 3px 10px; cursor: pointer; }
.retry-btn:hover { background: #fef2f2; }
</style>
