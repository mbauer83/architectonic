<script setup lang="ts">
/**
 * One node of the graph canvas, as drawn: shape, anchor halo, glyph, wrapped label, and the
 * badge that says it can be expanded.
 *
 * Lifted out of `GraphCanvas.vue` rather than written beside it — the canvas had grown past the
 * file-length policy and this was the self-contained half. It stays as domain-agnostic as its
 * parent: it receives a normalized node plus presentation callbacks and imports only the pure
 * geometry and colour helpers, never an architecture, assurance or viewpoint concept.
 */
import type { GraphNode } from '../composables/useForceGraph'
import { nodeLabelBox } from './graphNodeGeometry'
import {
  contrastTextColor, nodeShapePoints, wrapLabel, type NodeVisual,
} from './GraphCanvas.helpers'

const props = defineProps<{
  node: GraphNode
  selected: boolean
  anchor: boolean
  visual: NodeVisual
  expandable: boolean
}>()

const labelBox = () => nodeLabelBox(props.node.label, props.node.type, props.anchor)
</script>

<template>
  <!-- eslint-disable vue/multiline-html-element-content-newline -- Everything below is SVG, but
       `vue-eslint-parser` can only tell that from an enclosing `<svg>`, which is in the parent, so
       it reads these as HTML. Inside `<text>` whitespace is rendered content: the line break this
       rule asks for would put a leading space in every label. Free in HTML, not here. -->
  <!-- Anchor halo: outer ring + the white main-shape stroke = double ring -->
  <polygon
    v-if="anchor"
    :points="nodeShapePoints(visual.shape, 32)"
    fill="none"
    stroke="#1e293b"
    stroke-width="2"
  />
  <polygon
    :points="nodeShapePoints(visual.shape, anchor ? 27 : 24)"
    :fill="visual.color"
    :opacity="selected ? 1 : 0.8"
    :stroke="selected ? '#1e293b' : 'white'"
    :stroke-width="selected ? 3 : 2"
  />
  <!-- Glyph inside the node shape; falls back to the type abbreviation when the
       consumer supplies no glyph (e.g. non-ArchiMate graphs). -->
  <svg
    v-if="visual.glyph"
    x="-9"
    y="-9"
    width="18"
    height="18"
    viewBox="0 0 16 16"
    fill="none"
    :stroke="contrastTextColor(visual.color)"
    stroke-width="1.3"
    stroke-linecap="round"
    stroke-linejoin="round"
    pointer-events="none"
  ><g v-html="visual.glyph" /></svg>
  <text
    v-else
    dy="4"
    text-anchor="middle"
    :fill="contrastTextColor(visual.color)"
    font-size="9"
    font-weight="600"
  >
    {{ node.type }}
  </text>
  <!-- Translucent backing so the label stays legible where it crosses edges. -->
  <rect
    v-bind="labelBox()"
    rx="3"
    fill="#ffffff"
    opacity="0.6"
    pointer-events="none"
  />
  <!-- Label below the node: bolded type abbreviation, a colon, then the name (wrapped).
       Absolute y (not dy) — dy on <text> does not shift the baseline reliably once a
       child tspan sets its own x, which left the label sitting over the node. -->
  <text
    :y="anchor ? 46 : 40"
    text-anchor="middle"
    :fill="anchor ? '#1e293b' : '#374151'"
    font-size="10"
  >
    <title>{{ node.type }}: {{ node.label }}</title>
    <tspan
      v-for="(line, li) in wrapLabel(node.label)"
      :key="li"
      x="0"
      :dy="li === 0 ? 0 : 12"
    ><tspan
      v-if="li === 0"
      font-weight="700"
    >{{ node.type }}: </tspan>{{ line }}</tspan>
  </text>
  <text
    v-if="visual.iconLetter"
    x="-17"
    y="-14"
    text-anchor="middle"
    :fill="contrastTextColor(visual.color)"
    font-size="9"
    font-weight="bold"
    pointer-events="none"
  >{{ visual.iconLetter }}</text>
  <circle
    v-if="expandable"
    class="expand-badge"
    cx="17"
    cy="-17"
    r="7"
    fill="#2563eb"
    stroke="white"
    stroke-width="1.5"
    cursor="pointer"
  />
  <text
    v-if="expandable"
    x="17"
    y="-14"
    text-anchor="middle"
    fill="#252327"
    font-size="9"
    font-weight="bold"
    pointer-events="none"
  >+</text>
</template>
