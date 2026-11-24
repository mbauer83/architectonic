<script setup lang="ts">
/** Applied-viewpoint chip + stale-pin re-pin prompt + hide-instead-of-ghost toggle, shown
 * above the diagram-edit canvas when a viewpoint is applied (or was, and is now stale). */
import type { ViewpointSummary } from '../../domain'
import { findViewpointBySlug } from './ViewpointSelect.helpers'

const props = defineProps<{
  viewpoints: readonly ViewpointSummary[]
  viewpointSlug: string | null
  viewpointPinnedVersion: number | null
  stalePin: boolean
  hideInsteadOfGhost: boolean
}>()
const emit = defineEmits<{
  dismiss: []
  'repin': []
  'update:hideInsteadOfGhost': [value: boolean]
}>()

const viewpointName = () => findViewpointBySlug(props.viewpoints, props.viewpointSlug)?.name ?? props.viewpointSlug
</script>

<template>
  <div
    v-if="viewpointSlug || stalePin"
    class="viewpoint-bar"
  >
    <span
      v-if="viewpointSlug"
      class="viewpoint-chip"
    >
      🔭 {{ viewpointName() }}
      <span class="viewpoint-chip-version">v{{ viewpointPinnedVersion ?? '?' }}</span>
      <button
        class="viewpoint-chip-dismiss"
        title="Clear applied viewpoint"
        @click="emit('dismiss')"
      >
        ×
      </button>
    </span>
    <span
      v-if="stalePin"
      class="viewpoint-stale"
    >
      Pinned to an older version.
      <button
        class="viewpoint-repin-btn"
        @click="emit('repin')"
      >
        Re-pin to current version
      </button>
    </span>
    <label
      v-if="viewpointSlug"
      class="viewpoint-hide-toggle"
    >
      <input
        :checked="hideInsteadOfGhost"
        type="checkbox"
        @change="emit('update:hideInsteadOfGhost', ($event.target as HTMLInputElement).checked)"
      >
      Hide instead of ghost
    </label>
  </div>
</template>

<style scoped>
.viewpoint-bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
.viewpoint-chip { display: inline-flex; align-items: center; gap: 5px; padding: 3px 8px; border-radius: 999px; background: var(--indigo-soft); color: var(--indigo-text); font-size: 12px; font-weight: 500; }
.viewpoint-chip-version { color: var(--indigo); font-weight: 400; }
.viewpoint-chip-dismiss { background: none; border: none; cursor: pointer; color: var(--indigo); font-size: 14px; line-height: 1; padding: 0 0 0 2px; }
.viewpoint-chip-dismiss:hover { color: var(--indigo-text); }
.viewpoint-stale { font-size: 12px; color: var(--warn-text); display: inline-flex; align-items: center; gap: 6px; }
.viewpoint-repin-btn { font-size: 12px; color: var(--warn-text); background: var(--warn-soft); border: 1px solid var(--warn-border); border-radius: 5px; padding: 2px 8px; cursor: pointer; }
.viewpoint-repin-btn:hover { background: var(--warn-soft); }
.viewpoint-hide-toggle { font-size: 12px; color: var(--muted); display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
</style>
