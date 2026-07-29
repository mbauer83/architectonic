<script setup lang="ts">
/**
 * D11 banner for signal-styled ephemeral renders: computed classification,
 * basis snapshots, generation timestamp — or the unavailable note with default
 * styling. The export button routes through the stamped-export endpoint (the
 * only sanctioned way styled output leaves the browser).
 */
import type { SignalBanner } from '../../domain/schemas/viewpoints'

defineProps<{ banner: SignalBanner }>()
const emit = defineEmits<{ export: [] }>()
</script>

<template>
  <div
    class="signal-banner"
    :class="{ 'signal-banner--unavailable': !banner.available }"
  >
    <template v-if="banner.available">
      <strong>{{ banner.classification ?? 'no classified contributions' }}</strong>
      — signal-styled, ephemeral render (basis:
      <span
        v-for="snapshot in banner.basis_snapshots"
        :key="snapshot.anchor_entity_id"
        class="signal-basis"
      >{{ snapshot.snapshot_id }}</span>
      <span v-if="banner.basis_snapshots.length === 0">no active snapshot</span>
      · generated {{ banner.generated_at }})
    </template>
    <template v-else>
      signals unavailable — default styling ({{ banner.note }})
    </template>
    <button
      type="button"
      class="export-btn"
      title="Download with the classification banner stamped in"
      @click="emit('export')"
    >
      Export stamped SVG
    </button>
  </div>
</template>

<style scoped>
.signal-banner {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  font-size: 12px; padding: 6px 12px; margin-bottom: 8px; border-radius: 6px;
  background: #1e293b; color: #f8fafc;
}
.signal-banner--unavailable { background: #fef3c7; color: #92400e; border: 1px solid #f59e0b; }
.signal-basis { font-family: monospace; margin-right: 4px; }
.export-btn {
  margin-left: auto; padding: 2px 10px; border: 1px solid #cbd5e1; border-radius: 4px;
  background: white; color: #1e293b; font-size: 11px; cursor: pointer;
}
.export-btn:hover { background: #f1f5f9; }
</style>
