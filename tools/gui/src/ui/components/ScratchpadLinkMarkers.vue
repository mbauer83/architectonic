<script setup lang="ts">
/**
 * One SVG marker definition per end-decoration the ontology can ask for, per end.
 *
 * Its own component because there are twelve of them — six shapes, each needing a source- and a
 * target-oriented instance — and because they are a *vocabulary* rather than part of any one
 * drawing. The shapes come from `edgeMarkers`, the same definitions the graph explorer uses, so a
 * composition looks like a composition on both surfaces.
 */
import { EDGE_END_MARKERS, edgeMarkerId, edgeMarkerShape } from './edgeMarkers'
</script>

<template>
  <defs>
    <template
      v-for="marker in EDGE_END_MARKERS"
      :key="marker"
    >
      <marker
        v-for="end in (['source', 'target'] as const)"
        :id="edgeMarkerId(marker, end)"
        :key="`${marker}-${end}`"
        :ref-x="end === 'source'
          ? 12 - (edgeMarkerShape(marker)?.refX ?? 6)
          : edgeMarkerShape(marker)?.refX ?? 6"
        ref-y="6"
        marker-width="9"
        marker-height="9"
        view-box="0 0 12 12"
        orient="auto-start-reverse"
      >
        <path
          :d="edgeMarkerShape(marker)?.path"
          :fill="edgeMarkerShape(marker)?.filled ? 'context-stroke' : 'none'"
          stroke="context-stroke"
          stroke-width="1.2"
        />
      </marker>
    </template>
  </defs>
</template>
