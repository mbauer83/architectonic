<script setup lang="ts">
import type { LayoutMode } from '../composables/useForceGraph'
import {
  EXPLORATION_LAYOUT_OPTIONS, type ExplorationLayoutOverride,
} from '../views/GraphExploreView.helpers'
import { SPACING_PRESETS, type SpacingPreset } from '../composables/graphSpacingPresets'

export type { SpacingPreset }

export interface LayoutModeOption { value: LayoutMode; label: string }

/** The graph explorer's layout/spacing button groups: free-exploration layout modes,
 * viewpoint-execution layout overrides, and force-layout spacing presets. Spacing stays
 * visible whenever the force layout is active — it must never vanish after a render.
 *
 * The two viewpoint-execution props are optional because they are only read when
 * `viewpointActive`. A graph surface with no viewpoint concept at all — the assurance
 * explorer — would otherwise have to invent values for questions it cannot be asked. */
withDefaults(defineProps<{
  viewpointActive: boolean
  layoutMode: LayoutMode
  layoutOverride?: ExplorationLayoutOverride
  /** Which spacing rung is in force, by its label — the rungs now differ in more than one number,
   *  so no single one of them identifies the choice. */
  activeSpacing: string
  /** Radial layout is anchor-centric — without an anchored execution it has no center
   * and would fling every node off-viewport, so the option is disabled with a reason. */
  radialAvailable?: boolean
  /** Which layout modes this surface offers. A surface that always has an anchor — the
   *  assurance explorer rings its nodes by hop distance — can offer radial as well. */
  layoutModes?: readonly LayoutModeOption[]
}>(), {
  layoutOverride: 'auto',
  radialAvailable: false,
  // Inline rather than a named const: a `defineProps` default is hoisted out of setup(), so
  // it cannot reference a local binding. Radial is absent because it is anchor-centric, and
  // free exploration has no anchor to ring around.
  layoutModes: () => [
    { value: 'force', label: 'Force' },
    { value: 'cluster', label: 'Cluster' },
  ],
})
const emit = defineEmits<{
  'switch-layout': [mode: LayoutMode]
  'set-exploration-layout': [value: ExplorationLayoutOverride]
  'apply-preset': [preset: SpacingPreset]
}>()
</script>

<template>
  <div
    v-if="!viewpointActive"
    class="spacing-controls"
  >
    <span class="spacing-label">Layout:</span>
    <button
      v-for="m in layoutModes"
      :key="m.value"
      class="spacing-btn"
      :class="{ 'spacing-btn--active': layoutMode === m.value }"
      @click="emit('switch-layout', m.value)"
    >
      {{ m.label }}
    </button>
  </div>
  <div
    v-else
    class="spacing-controls"
  >
    <span class="spacing-label">Layout:</span>
    <button
      v-for="o in EXPLORATION_LAYOUT_OPTIONS"
      :key="o.value"
      class="spacing-btn"
      :class="{ 'spacing-btn--active': layoutOverride === o.value }"
      :disabled="o.value === 'radial' && !radialAvailable"
      :title="o.value === 'radial' && !radialAvailable
        ? 'Radial layout needs an anchored execution — it arranges nodes in rings around the anchor'
        : undefined"
      @click="emit('set-exploration-layout', o.value)"
    >
      {{ o.label }}
    </button>
  </div>
  <!-- Every layout, not only force. Each rung states its own units for all three — a ring
       increment, a cluster cell's air, the force pair — so asking for more room means something
       whichever arrangement is on screen. It used to render only under force, which is why the
       control simply vanished in the two layouts that now answer to it. -->
  <div class="spacing-controls">
    <span class="spacing-label">Spacing:</span>
    <button
      v-for="p in SPACING_PRESETS"
      :key="p.label"
      class="spacing-btn"
      :class="{ 'spacing-btn--active': p.label === activeSpacing }"
      @click="emit('apply-preset', p)"
    >
      {{ p.label }}
    </button>
  </div>
</template>

<style scoped>
/* `flex-shrink: 0` because the row that holds these is a wrapping flex container: without it a
   group is compressed below the width of its own buttons and the text overflows the box it is
   drawn in, which reads as the neighbouring label sitting on top of the control beside it. Wrapping
   is the intended answer to a narrow row; squashing is not. */
.spacing-controls {
  display: inline-flex; align-items: center; gap: 4px; margin-left: 12px; flex-shrink: 0;
}
.spacing-label { font-size: 11.5px; color: #6b7280; }
.spacing-btn {
  font-size: 11.5px; padding: 3px 10px; border: 1px solid #d1d5db; border-radius: 5px;
  background: white; cursor: pointer; color: #374151;
}
/* Hover is excluded on the selected button and given its own darker shade there. A bare
   `:hover` rule outranks the single-class active rule, so hovering the selected button
   restored the pale hover background while the active rule's white text stayed — the
   label disappeared for as long as the pointer rested on it. */
.spacing-btn:hover:not(:disabled):not(.spacing-btn--active) { background: #f3f4f6; }
.spacing-btn:disabled { color: #c4c8cf; cursor: not-allowed; }
.spacing-btn--active { background: #2563eb; color: white; border-color: #2563eb; }
.spacing-btn--active:hover:not(:disabled) { background: #1d4ed8; }
</style>
