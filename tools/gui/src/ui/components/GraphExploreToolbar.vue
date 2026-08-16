<script setup lang="ts">
/**
 * The graph explorer's controls: which viewpoint is on screen, what is filtered out of the
 * picture, how to take a copy of it, and how it is laid out.
 *
 * Lifted out of `GraphExploreView.vue` rather than written beside it — the view had grown past
 * the file-length policy and this was the self-contained half. It is the dock as well as the
 * controls, because where the controls sit is part of what they are: in the page's header row
 * normally, floating over the canvas once that owns the screen, where the page header is not
 * painted at all. Collapsed to a glyph while floating — the controls are wanted occasionally and
 * the graph is wanted continuously — and the disclosure is this component's own state, since
 * nothing outside it can be asked whether a toolbar is open.
 *
 * The filter and layout groups are passed through as whole prop objects rather than restated
 * field by field: their contracts belong to `GraphFilterPanel` and `GraphLayoutToolbar`, and a
 * second spelling here would be one more place to change when either gains a control.
 */
import { ref } from 'vue'
import type { ViewpointSummary } from '../../domain'
import type { ExplorationLayoutOverride } from '../views/GraphExploreView.helpers'
import type { LayoutMode } from '../composables/useForceGraph'
import type { SpacingPreset } from '../composables/graphSpacingPresets'
import DownloadMenu from './DownloadMenu.vue'
import FullscreenDock from './FullscreenDock.vue'
import GraphFilterPanel from './GraphFilterPanel.vue'
import GraphLayoutToolbar from './GraphLayoutToolbar.vue'
import ViewpointSelect from './ViewpointSelect.vue'

defineProps<{
  fullscreenHost: HTMLElement | null
  isFullscreen: boolean
  /** Absent on the ad-hoc surface: an inline execution has no saved viewpoint to pick. */
  showViewpointPicker: boolean
  selectedViewpointSlug: string | null
  viewpoints: readonly ViewpointSummary[]
  filter: InstanceType<typeof GraphFilterPanel>['$props']
  layout: InstanceType<typeof GraphLayoutToolbar>['$props']
}>()

defineEmits<{
  'select-viewpoint': [viewpoint: ViewpointSummary | null]
  'toggle-facet': [level: string, value: string]
  'reset-facets': []
  snapshot: [format: 'png' | 'svg']
  'switch-layout': [mode: LayoutMode]
  'set-exploration-layout': [value: ExplorationLayoutOverride]
  'apply-preset': [preset: SpacingPreset]
}>()

const open = ref(false)
</script>

<template>
  <FullscreenDock
    :fullscreen-host="fullscreenHost"
    :is-fullscreen="isFullscreen"
    revealed
  >
    <div
      class="graph-toolbar"
      :class="{ 'graph-toolbar--floating': isFullscreen }"
    >
      <button
        v-if="isFullscreen"
        type="button"
        class="toolbar-disclosure"
        :aria-expanded="open"
        aria-controls="graph-toolbar-body"
        :title="open ? 'Hide controls' : 'Show controls'"
        :aria-label="open ? 'Hide controls' : 'Show controls'"
        @click="open = !open"
      >
        {{ open ? '×' : '☰' }}
      </button>
      <div
        v-show="!isFullscreen || open"
        id="graph-toolbar-body"
        class="toolbar-body"
      >
        <div
          v-if="showViewpointPicker"
          class="spacing-controls"
        >
          <span class="spacing-label">Viewpoint:</span>
          <ViewpointSelect
            :model-value="selectedViewpointSlug"
            :viewpoints="viewpoints"
            @select="$emit('select-viewpoint', $event)"
          />
        </div>
        <GraphFilterPanel
          v-bind="filter"
          @toggle="(level, value) => $emit('toggle-facet', level, value)"
          @reset="$emit('reset-facets')"
        />
        <!-- The same affordance a diagram offers, answered differently: there is no
             persisted artifact here, so the bytes are the current view serialised. -->
        <DownloadMenu @select="$emit('snapshot', $event)" />
        <GraphLayoutToolbar
          v-bind="layout"
          @switch-layout="$emit('switch-layout', $event)"
          @set-exploration-layout="$emit('set-exploration-layout', $event)"
          @apply-preset="$emit('apply-preset', $event)"
        />
      </div>
    </div>
  </FullscreenDock>
</template>

<style scoped>
/* Embedded, the wrapper and its body are transparent: the three control groups are laid out by the
   page's own header row, exactly as they were before there was anything to dock. `display: contents`
   is what says "I am here for the dock, not for the layout".
   Floating, it stops being three items in someone else's row and becomes one box of its own. */
.graph-toolbar, .toolbar-body { display: contents; }
.graph-toolbar--floating { display: flex; }
.toolbar-disclosure {
  width: 28px; height: 28px; display: inline-flex; align-items: center; justify-content: center;
  background: rgb(255 255 255 / 92%); border: 1px solid #d1d5db; border-radius: 6px;
  font-size: 15px; line-height: 1; cursor: pointer; color: #374151; flex-shrink: 0;
}
.toolbar-disclosure:hover { background: #fff; }

.spacing-controls { display: flex; align-items: center; gap: 4px; }
.spacing-label { font-size: 11px; color: #6b7280; margin-right: 4px; }
</style>
