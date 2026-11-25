<script setup lang="ts">
/**
 * A button that writes, offered as the permission answer allows its operation (`useCan`): refused, it is
 * disabled and its title is the reason. Everything else — its class, test id, click — is the caller's.
 */
import { computed, useAttrs } from 'vue'
import { useCan } from '../composables/usePermissions'

defineOptions({ inheritAttrs: false })
const props = defineProps<{
  /** The named operation the button does (`operation_catalog`). */
  operation: string
  /** Disabled for the caller's own reason, whatever the answer. */
  disabled?: boolean
}>()
const attrs = useAttrs()
const may = useCan(() => props.operation)
const ownTitle = computed(() => (typeof attrs.title === 'string' ? attrs.title : undefined))
</script>

<template>
  <button
    type="button"
    v-bind="attrs"
    :disabled="disabled || !may.allowed"
    :title="may.allowed ? ownTitle : may.reason"
  >
    <slot />
  </button>
</template>
