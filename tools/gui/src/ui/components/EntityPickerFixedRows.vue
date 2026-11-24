<script setup lang="ts">
/** Read-only display of the picker's pinned filter levels (strategy A: compact chip for
 * a single value, chip row for a set) — pure display, no interaction. */
defineProps<{
  fixedDomains?: string[]
  fixedEntityTypes?: string[]
}>()
</script>

<template>
  <div
    v-if="fixedDomains?.length"
    class="ep-fixed-row"
  >
    <span class="ep-fixed-label">{{ fixedDomains.length === 1 ? 'Domain' : 'Domains' }}</span>
    <template v-if="fixedDomains.length === 1">
      <span
        class="ep-fixed-chip"
        title="Domain filter is pinned"
      >{{ fixedDomains[0] }}</span>
      <span
        class="ep-fixed-lock"
        aria-label="locked"
      >🔒</span>
    </template>
    <template v-else>
      <div class="ep-fixed-set">
        <span
          v-for="d in fixedDomains"
          :key="d"
          class="ep-fixed-chip"
        >{{ d }}</span>
      </div>
      <span
        class="ep-fixed-lock"
        aria-label="locked"
      >🔒</span>
    </template>
  </div>

  <div
    v-if="fixedEntityTypes?.length"
    class="ep-fixed-row ep-fixed-row--types"
  >
    <span class="ep-fixed-label">{{ fixedEntityTypes.length === 1 ? 'Type' : 'Types' }}</span>
    <template v-if="fixedEntityTypes.length === 1">
      <span
        class="ep-fixed-chip ep-fixed-chip--type"
        title="Entity type filter is pinned"
      >{{ fixedEntityTypes[0] }}</span>
      <span
        class="ep-fixed-lock"
        aria-label="locked"
      >🔒</span>
    </template>
    <template v-else>
      <div class="ep-fixed-set">
        <span
          v-for="t in fixedEntityTypes"
          :key="t"
          class="ep-fixed-chip ep-fixed-chip--type"
        >{{ t }}</span>
      </div>
      <span
        class="ep-fixed-lock"
        aria-label="locked"
      >🔒</span>
    </template>
  </div>
</template>

<style scoped>
.ep-fixed-row { display: flex; align-items: center; gap: 6px; padding: 6px 10px; background: var(--info-soft); border-bottom: 1px solid var(--info-border); font-size: 12px; flex-wrap: wrap; }
.ep-fixed-row--types { background: var(--violet-soft); border-bottom-color: var(--violet-border); }
.ep-fixed-label { font-size: 10px; font-weight: 700; color: var(--info-text); flex-shrink: 0; text-transform: uppercase; letter-spacing: .05em; }
.ep-fixed-row--types .ep-fixed-label { color: var(--violet-text); }
.ep-fixed-chip { background: var(--info-soft); border: 1px solid var(--info-border); color: var(--info-text); border-radius: 999px; padding: 2px 9px; font-size: 11px; cursor: default; }
.ep-fixed-chip--type { background: var(--violet-soft); border-color: var(--violet-border); color: var(--violet-text); }
.ep-fixed-set { display: flex; flex-wrap: wrap; gap: 4px; }
.ep-fixed-lock { color: var(--faint); font-size: 10px; }
</style>
