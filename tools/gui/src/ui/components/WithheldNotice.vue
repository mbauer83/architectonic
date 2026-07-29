<script setup lang="ts">
// Advises that the view is subject to a TLP ceiling: content classified above it
// is not served. The signal that drives this notice is ceiling-based, not a count
// of actually-withheld items — by design, so a viewer can never infer whether
// higher-classified content exists (the absent/above-ceiling indistinguishability
// rule). The wording is therefore "may be hidden", never a definite claim: this is
// feature-correctness (confidentiality), not an error.
import { computed, onMounted, ref } from 'vue'

withDefaults(defineProps<{ kind?: string }>(), { kind: 'items' })

const ceiling = ref('')
const ceilingLabel = computed(() => (ceiling.value ? ` (${ceiling.value})` : ''))

onMounted(async () => {
  try {
    const resp = await fetch('/api/assurance/status')
    if (resp.ok) {
      const body = await resp.json() as { max_classification?: unknown }
      if (typeof body.max_classification === 'string') ceiling.value = body.max_classification
    }
  } catch {
    /* ceiling label is best-effort; the explanation stands without it */
  }
})
</script>

<template>
  <p class="withheld-notice">
    <span
      class="withheld-icon"
      aria-hidden="true"
    >🔒</span>
    Some {{ kind }} may be hidden: content classified above your current access
    ceiling{{ ceilingLabel }} is not shown. This is the confidentiality policy working
    as intended. To view higher-classification content, raise the assurance store's
    <code>max_classification</code> setting.
  </p>
</template>

<style scoped>
.withheld-notice {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
  color: #92400e;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 6px;
  padding: 8px 10px;
  margin: 8px 0 0;
}
.withheld-icon { flex-shrink: 0; }
.withheld-notice code {
  font-size: 11px;
  background: #fef3c7;
  padding: 1px 4px;
  border-radius: 3px;
}
</style>
