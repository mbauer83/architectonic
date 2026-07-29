<script setup lang="ts">
/**
 * SVG `<marker>` definitions for every decoration an edge may carry at either end.
 *
 * Its own component so `GraphCanvas` stays within the source-length policy, and because this is
 * pure declaration: it renders nothing on its own and reads no props. Two instances per shape,
 * one oriented for each end, so an asymmetric decoration points the right way.
 */
import { EDGE_END_MARKERS, edgeMarkerId, edgeMarkerShape } from './edgeMarkers'
</script>

<template>
  <!-- The plain head an edge gets when its caller says nothing about markers at all. Kept
       distinct from `none`, which is a caller stating that an end carries no decoration. -->
  <marker
    id="arrowhead"
    markerWidth="8"
    markerHeight="6"
    refX="8"
    refY="3"
    orient="auto"
  >
    <polygon
      points="0 0, 8 3, 0 6"
      fill="#9ca3af"
    />
  </marker>
  <!-- One marker per shape per end. Source markers are reversed so an asymmetric shape
           (a triangle, an arrow) points back along the line rather than away from it. -->
  <template
    v-for="marker in EDGE_END_MARKERS"
    :key="marker"
  >
    <marker
      v-for="end in (['source', 'target'] as const)"
      :id="edgeMarkerId(marker, end)"
      :key="end"
      markerWidth="12"
      markerHeight="12"
      :refX="end === 'source' ? 12 - (edgeMarkerShape(marker)?.refX ?? 6) : edgeMarkerShape(marker)?.refX ?? 6"
      refY="6"
      markerUnits="userSpaceOnUse"
      :orient="end === 'source' ? 'auto-start-reverse' : 'auto'"
    >
      <path
        :d="edgeMarkerShape(marker)?.path"
        :fill="edgeMarkerShape(marker)?.filled ? '#9ca3af' : '#ffffff'"
        stroke="#9ca3af"
        stroke-width="1.2"
      />
    </marker>
  </template>
</template>
