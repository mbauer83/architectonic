<script setup lang="ts">
/**
 * Everything a diagram window shows over its picture (D13, L10): the overview, the names written at
 * screen size while the picture's text is too small, and the controls with their keys. One component, so
 * every viewer of a rendered diagram — a stored diagram, a viewpoint's view, an assurance projection —
 * has the same window rather than a copy of some of it.
 *
 * It knows the window (`useFittedPanZoom`) and nothing of what the picture draws: the viewer says which
 * elements are marked and named.
 */
import type { useFittedPanZoom } from '../composables/useFittedPanZoom'
import type { OverviewMark } from '../lib/diagramOverview'
import DiagramOverview from './DiagramOverview.vue'
import DiagramScreenNames from './DiagramScreenNames.vue'
import DiagramViewportControls from './DiagramViewportControls.vue'

withDefaults(defineProps<{
  window: ReturnType<typeof useFittedPanZoom>
  /** The element the picture's `<svg>` is mounted in. */
  picture: HTMLElement | null
  /** What the overview marks: the selection, and the reading where there is one. */
  marks?: readonly OverviewMark[]
  /** The reading's elements, named alone while there is a reading. */
  reading?: readonly OverviewMark[]
  /** Every element the picture draws, named while there is no reading. */
  boxes?: readonly OverviewMark[]
  /** Enter edit mode, which `E` asks for; absent where it cannot be asked. */
  edit?: (() => void) | null
  isFullscreen?: boolean
  canFullscreen?: boolean
  hint: string
}>(), { marks: () => [], reading: () => [], boxes: () => [], edit: null, isFullscreen: false, canFullscreen: false })

defineEmits<{ 'toggle-fullscreen': [] }>()
</script>

<template>
  <DiagramOverview
    :picture="picture"
    :window-extent="window.windowExtent"
    :scale="window.scale.value"
    :show-view="window.showView"
    :marks="marks"
  />
  <DiagramScreenNames
    :marks="reading"
    :boxes="boxes"
    :picture="picture"
    :scale="window.scale.value"
    :to-window="window.toWindow"
  />
  <DiagramViewportControls
    :zoom="window"
    :edit="edit"
    :is-transformed="window.isTransformed.value"
    :is-fullscreen="isFullscreen"
    :can-fullscreen="canFullscreen"
    :hint="hint"
    @reset="window.resetView"
    @toggle-fullscreen="$emit('toggle-fullscreen')"
  />
</template>
