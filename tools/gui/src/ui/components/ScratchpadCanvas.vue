<script setup lang="ts">
/**
 * The scratchpad canvas: HTML notes in a transformed layer, SVG beneath for frames and links.
 *
 * The 500-note spike settled the approach. Applying the pan/zoom transform and forcing style and
 * layout to completion costs **0.1 ms at 1000 notes and 1600 links**, because a transform on a
 * composited layer invalidates no layout at all — the DOM is not the bottleneck at this scale, and
 * everything left is rasterisation any renderer would pay. What HTML buys in exchange is the whole
 * reason to prefer it: `contenteditable` titles with real text editing, IME and spellcheck; CSS for
 * the visuals; native hit-testing; and interactions the Playwright suite can actually see, on the
 * most interaction-heavy surface in the product.
 *
 * The spike also ruled culling *out* for now: hiding offscreen notes measured **worse**, since
 * `visibility:hidden` keeps an element in layout while adding a style write per note per frame.
 *
 * This component owns gestures and rendering only. The document, its undo history and when to save
 * belong to the view — so the canvas can be driven by a test with a plain object, and the save
 * policy is not buried in a mouse handler.
 */
import { computed, ref } from 'vue'
import { useScratchpadGestures } from '../composables/useScratchpadGestures'
import type { Area, Link, Note, Scratchpad } from '../../domain/schemas/scratchpads'

const props = defineProps<{ scratchpad: Scratchpad; selectedId: string | null }>()
const emit = defineEmits<{
  (event: 'create-note', payload: { x: number; y: number }): void
  (event: 'move-note', payload: { id: string; x: number; y: number }): void
  (event: 'rename-note', payload: { id: string; title: string }): void
  (event: 'delete-note', payload: { id: string }): void
  (event: 'link-notes', payload: { source: string; target: string }): void
  (event: 'select', payload: { id: string | null }): void
  (event: 'bind-request', payload: { areaId: string }): void
  (event: 'unbind-note', payload: { id: string }): void
}>()

const NOTE_WIDTH = 180
const NOTE_HEIGHT = 64

const viewport = ref<HTMLElement | null>(null)

const notes = computed<readonly Note[]>(() => props.scratchpad.notes ?? [])
const links = computed<readonly Link[]>(() => props.scratchpad.links ?? [])
const areas = computed<readonly Area[]>(() => props.scratchpad.areas ?? [])

const positionOf = (id: string): { x: number; y: number } => {
  const point = props.scratchpad.layout?.notes?.[id]
  return { x: point?.[0] ?? 0, y: point?.[1] ?? 0 }
}
const rectOf = (id: string): { x: number; y: number; w: number; h: number } => {
  const rect = props.scratchpad.layout?.areas?.[id]
  return { x: rect?.[0] ?? 0, y: rect?.[1] ?? 0, w: rect?.[2] ?? 0, h: rect?.[3] ?? 0 }
}

/** A cubic Bézier between two notes' centres.
 *
 * Curved rather than straight, deliberately: a straight line reads as a decided relation, and every
 * link here is provisional until it is typed. The control points run horizontally so the curve
 * leaves and enters along the axis a reader scans. */
const linkPath = (link: Link): string => {
  const from = positionOf(link.source)
  const to = positionOf(link.target)
  const x1 = from.x + NOTE_WIDTH / 2
  const y1 = from.y + NOTE_HEIGHT / 2
  const x2 = to.x + NOTE_WIDTH / 2
  const y2 = to.y + NOTE_HEIGHT / 2
  const bend = Math.max(40, Math.abs(x2 - x1) * 0.4)
  return `M${x1},${y1} C${x1 + bend},${y1} ${x2 - bend},${y2} ${x2},${y2}`
}

const refusedLinks = computed(() => links.value.filter((link) => link.verdict?.kind === 'refused'))

/** The midpoint of a link's curve, near enough for a marker: the Bézier's control points are
 * horizontal, so the curve passes close to the straight-line midpoint. */
const linkMidpoint = (link: Link): { x: number; y: number } => {
  const from = positionOf(link.source)
  const to = positionOf(link.target)
  return {
    x: (from.x + to.x) / 2 + NOTE_WIDTH / 2,
    y: (from.y + to.y) / 2 + NOTE_HEIGHT / 2 - 6,
  }
}

const {
  layerTransform, linkingFrom, pointer, resetView,
  onNotePointerDown, onHandlePointerDown, onBackgroundPointerDown,
  onPointerMove, onPointerUp, onBackgroundDoubleClick, onWheel,
} = useScratchpadGestures(
  viewport,
  positionOf,
  { width: NOTE_WIDTH, height: NOTE_HEIGHT },
  {
    onSelect: (id) => emit('select', { id }),
    onMoveNote: (id, x, y) => emit('move-note', { id, x, y }),
    onCreateNote: (x, y) => emit('create-note', { x, y }),
    onLinkNotes: (source, target) => emit('link-notes', { source, target }),
  },
)

const onTitleBlur = (event: FocusEvent, note: Note): void => {
  const text = (event.target as HTMLElement).innerText.trim()
  if (text && text !== note.title) emit('rename-note', { id: note.id, title: text })
  else if (!text) (event.target as HTMLElement).innerText = note.title
}

/** Enter commits a title; Escape abandons it. Without this, Enter inserts a newline into a field
 * that renders on one line, and the change looks lost. */
const onTitleKeydown = (event: KeyboardEvent, note: Note): void => {
  if (event.key === 'Enter') {
    event.preventDefault()
    ;(event.target as HTMLElement).blur()
  } else if (event.key === 'Escape') {
    ;(event.target as HTMLElement).innerText = note.title
    ;(event.target as HTMLElement).blur()
  }
}

defineExpose({ resetView })
</script>

<template>
  <div
    ref="viewport"
    class="sp-viewport"
    data-testid="scratchpad-canvas"
    @pointerdown="onBackgroundPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointerleave="onPointerUp"
    @dblclick="onBackgroundDoubleClick"
    @wheel="onWheel"
  >
    <!-- Frames and links share the note layer's transform, so nothing drifts on pan or zoom. -->
    <svg
      class="sp-underlay"
      :style="{ transform: layerTransform }"
      aria-hidden="true"
    >
      <g
        v-for="area in areas"
        :key="area.id"
      >
        <rect
          class="sp-area"
          :data-area-id="area.id"
          :x="rectOf(area.id).x"
          :y="rectOf(area.id).y"
          :width="rectOf(area.id).w"
          :height="rectOf(area.id).h"
          rx="12"
        />
        <text
          class="sp-area-label"
          :x="rectOf(area.id).x + 16"
          :y="rectOf(area.id).y + 26"
        >
          {{ area.label }}
        </text>
      </g>
      <path
        v-for="link in links"
        :key="link.id"
        class="sp-link"
        :class="[link.verdict?.kind ?? 'unverified', { typed: !!link['connection-type'] }]"
        :data-link-id="link.id"
        :data-verdict="link.verdict?.kind ?? 'unverified'"
        :d="linkPath(link)"
      />
      <!-- A refusal is the one verdict that must be visible without hovering: it is the only one
           that stops a lift. -->
      <text
        v-for="link in refusedLinks"
        :key="`x-${link.id}`"
        class="sp-link-flag"
        :x="linkMidpoint(link).x"
        :y="linkMidpoint(link).y"
        text-anchor="middle"
      >✕</text>
      <path
        v-if="linkingFrom"
        class="sp-link drawing"
        :d="`M${positionOf(linkingFrom).x + NOTE_WIDTH / 2},${positionOf(linkingFrom).y + NOTE_HEIGHT / 2}
             L${pointer.x},${pointer.y}`"
      />
    </svg>

    <!-- One per frame, in the HTML layer because the SVG underlay takes no pointer events.
         Reaching for what already exists is the more common move than inventing something, so
         the affordance sits on the frame rather than behind a menu. -->
    <div
      class="sp-layer sp-frame-actions"
      :style="{ transform: layerTransform }"
    >
      <button
        v-for="area in areas"
        :key="`add-${area.id}`"
        type="button"
        class="sp-add-existing"
        :data-add-existing="area.id"
        :title="`Add an element that already exists to ${area.label}`"
        :style="{
          transform: `translate(${rectOf(area.id).x + rectOf(area.id).w - 150}px, ${rectOf(area.id).y + 12}px)`,
        }"
        @pointerdown.stop
        @click.stop="emit('bind-request', { areaId: area.id })"
      >
        + Add existing
      </button>
    </div>

    <div
      class="sp-layer"
      :style="{ transform: layerTransform }"
    >
      <article
        v-for="note in notes"
        :key="note.id"
        class="sp-note"
        :class="{ selected: note.id === selectedId, typed: !!note['element-type'], bound: !!note['model-ref'] }"
        :data-note-id="note.id"
        :data-area="note.area"
        :style="{ transform: `translate(${positionOf(note.id).x}px, ${positionOf(note.id).y}px)` }"
        @pointerdown="onNotePointerDown($event, note.id)"
      >
        <!-- `contenteditable` rather than a positioned <input>: real text editing, IME and
             spellcheck come free, which is the whole argument for HTML notes. -->
        <div
          class="sp-title"
          contenteditable="plaintext-only"
          spellcheck="true"
          :data-note-title="note.id"
          @pointerdown.stop
          @blur="onTitleBlur($event, note)"
          @keydown="onTitleKeydown($event, note)"
        >
          {{ note.title }}
        </div>
        <footer class="sp-meta">
          <button
            v-if="note['model-ref']?.kind === 'bound'"
            type="button"
            class="sp-type sp-bound"
            :data-unbind-note="note.id"
            :title="`Bound to ${note['model-ref']['artifact-id']} — click to release`"
            @pointerdown.stop
            @click.stop="emit('unbind-note', { id: note.id })"
          >
            ⛓ {{ note['element-type'] }}
          </button>
          <span
            v-else-if="note['element-type']"
            class="sp-type"
          >{{ note['element-type'] }}</span>
          <span
            v-else
            class="sp-untyped"
          >untyped</span>
          <button
            class="sp-delete"
            type="button"
            title="Delete note"
            :data-delete-note="note.id"
            @pointerdown.stop
            @click.stop="emit('delete-note', { id: note.id })"
          >
            ×
          </button>
        </footer>
        <!-- Drag from here to draw a link. A dedicated handle keeps note-drag and link-draw
             unambiguous, which a modifier key does not. -->
        <button
          class="sp-handle"
          type="button"
          title="Draw a link"
          :data-link-handle="note.id"
          @pointerdown="onHandlePointerDown($event, note.id)"
        />
      </article>
    </div>
  </div>
</template>

<style scoped>
.sp-viewport {
  position: relative; overflow: hidden; height: 100%; width: 100%;
  background: #fafafa; touch-action: none; cursor: grab; user-select: none;
}
.sp-viewport:active { cursor: grabbing; }
.sp-underlay, .sp-layer {
  position: absolute; top: 0; left: 0; transform-origin: 0 0; will-change: transform;
}
.sp-underlay { overflow: visible; width: 100%; height: 100%; pointer-events: none; }
.sp-area { fill: #ffffff; stroke: #e2e2e6; stroke-width: 1.5; }
.sp-area-label { font: 600 13px system-ui, sans-serif; fill: #8b8b93; letter-spacing: .02em; }
.sp-link { fill: none; stroke: #c3c6cc; stroke-width: 1.5; stroke-dasharray: 5 4; }
/* Solid once typed: the canvas should show at a glance how much of the picture is committed to. */
.sp-link.typed { stroke: #6b7280; stroke-dasharray: none; }
/* The verdict, at a glance. Permitted is settled and quiet; narrowed warns without blocking;
   refused is the only one that stops a lift, so it is the only one that shouts. */
.sp-link.permitted { stroke: #059669; stroke-dasharray: none; }
.sp-link.narrowed { stroke: #d97706; stroke-dasharray: none; }
.sp-link.refused { stroke: #dc2626; stroke-width: 2; stroke-dasharray: none; }
.sp-link.reference { stroke: #7c3aed; stroke-dasharray: 2 3; }
.sp-link-flag { font: 700 13px system-ui, sans-serif; fill: #dc2626; }
.sp-link.drawing { stroke: #2563eb; stroke-dasharray: 4 3; }

.sp-note {
  position: absolute; top: 0; left: 0; width: 180px; box-sizing: border-box;
  padding: 8px 10px 6px; background: #fff; border: 1px solid #dcdce1; border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0,0,0,.06); cursor: default;
  transition: box-shadow .12s ease, border-color .12s ease;
}
.sp-note:hover { box-shadow: 0 2px 6px rgba(0,0,0,.10); }
.sp-note.selected { border-color: #2563eb; box-shadow: 0 0 0 2px rgba(37,99,235,.18); }
.sp-note.typed { border-left: 3px solid #7c3aed; }
.sp-note.bound { border-left: 3px solid #059669; }
.sp-frame-actions { pointer-events: none; }
.sp-add-existing {
  position: absolute; top: 0; left: 0; pointer-events: auto; width: 130px;
  padding: 4px 8px; border: 1px dashed #c7c7cf; border-radius: 6px; background: #fff;
  font-size: 11.5px; color: #6b7280; cursor: pointer;
}
.sp-add-existing:hover { border-color: #2563eb; color: #2563eb; border-style: solid; }
.sp-bound {
  border: none; background: none; padding: 0; cursor: pointer;
  color: #059669; font-size: 10.5px; font-weight: 600;
}
.sp-bound:hover { text-decoration: line-through; }
.sp-title {
  font-size: 12.5px; line-height: 1.35; color: #1f2328; outline: none;
  min-height: 1.35em; word-break: break-word; cursor: text;
}
.sp-title:focus { box-shadow: inset 0 -1px 0 #2563eb; }
.sp-meta { display: flex; align-items: center; justify-content: space-between; margin-top: 6px; }
.sp-type { font-size: 10.5px; color: #7c3aed; font-weight: 600; }
.sp-untyped { font-size: 10.5px; color: #9ca3af; }
.sp-delete {
  border: none; background: none; color: #b0b0b8; font-size: 15px; line-height: 1;
  cursor: pointer; padding: 0 2px; border-radius: 3px;
}
.sp-delete:hover { color: #dc2626; background: #fee2e2; }
.sp-handle {
  position: absolute; right: -6px; top: 50%; transform: translateY(-50%);
  width: 12px; height: 12px; border-radius: 50%; border: 2px solid #fff;
  background: #9ca3af; cursor: crosshair; padding: 0; opacity: 0;
  transition: opacity .12s ease;
}
.sp-note:hover .sp-handle, .sp-note.selected .sp-handle { opacity: 1; }
.sp-handle:hover { background: #2563eb; }
</style>
