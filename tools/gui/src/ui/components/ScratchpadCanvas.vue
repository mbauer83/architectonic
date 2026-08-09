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
import { computed, ref, watch } from 'vue'
import { useScratchpadGestures } from '../composables/useScratchpadGestures'
import { linkMidpoint, linkPath } from '../composables/scratchpadLinkGeometry'
import { getDomainColor } from '../lib/domains'
import ScratchpadLinkMarkers from './ScratchpadLinkMarkers.vue'
import ScratchpadNote from './ScratchpadNote.vue'
import { edgeMarkerId } from './edgeMarkers'
import { notationDash, type RelationNotation } from '../lib/relationNotations'
import { archimateGlyphMarkup } from '../lib/glyphKey'
import {
  menuAnchorFor,
  noteKeydown,
  selectionAnnouncement,
} from '../composables/useScratchpadKeyboard'
import type { Area, Link, Note, Scratchpad } from '../../domain/schemas/scratchpads'

const props = defineProps<{
  scratchpad: Scratchpad
  selectedIds: readonly string[]
  selectedLinkId: string | null
  /** The frame being worked in, or null. Everything outside it is dimmed, never hidden. */
  focusedAreaId: string | null
  /** Connection type → how the ontology says it is drawn. Empty until it has been fetched, which
   * is one request per canvas rather than one per link. */
  notations: ReadonlyMap<string, RelationNotation>
}>()
const emit = defineEmits<{
  (event: 'create-note', payload: { x: number; y: number }): void
  (event: 'move-note', payload: { id: string; x: number; y: number }): void
  (event: 'rename-note', payload: { id: string; title: string }): void
  (event: 'delete-note', payload: { id: string }): void
  (event: 'link-notes', payload: { source: string; target: string }): void
  (event: 'select', payload: { id: string | null; additive: boolean }): void
  (event: 'select-link', payload: { id: string | null }): void
  (event: 'menu-request', payload: {
    at: { x: number; y: number }
    screen: { x: number; y: number }
  }): void
  (event: 'edit-title', payload: { id: string }): void
  (event: 'unbind-note', payload: { id: string }): void
}>()

// Roughly square, so the title has room to be the note rather than a caption on one: a thought is
// what a scratchpad holds, and a wide strip makes it look like a row in a list.
const NOTE_WIDTH = 132
const NOTE_HEIGHT = 120

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

const NOTE_BOX = { width: NOTE_WIDTH, height: NOTE_HEIGHT }
const pathOf = (link: Link): string => linkPath(positionOf(link.source), positionOf(link.target), NOTE_BOX)
const midpointOf = (link: Link) => linkMidpoint(positionOf(link.source), positionOf(link.target), NOTE_BOX)

const refusedLinks = computed(() => links.value.filter((link) => link.verdict?.kind === 'refused'))

const {
  layerTransform, linkingFrom, pointer, resetView, fitTo,
  onNotePointerDown, onHandlePointerDown, onBackgroundPointerDown,
  onPointerMove, onPointerUp, onBackgroundDoubleClick, onContextMenu, onWheel,
} = useScratchpadGestures(
  viewport,
  positionOf,
  NOTE_BOX,
  {
    onSelect: (id, additive) => emit('select', { id, additive }),
    onMoveNote: (id, x, y) => emit('move-note', { id, x, y }),
    onCreateNote: (x, y) => emit('create-note', { x, y }),
    onLinkNotes: (source, target) => emit('link-notes', { source, target }),
    onOpenMenu: (at, screen) => emit('menu-request', { at, screen }),
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

/** Every pointer gesture, spelled as a key. The note is a `listbox` option, so `Space` toggling and
 * `Enter` entering it is the convention a screen-reader user already has. */
const onNoteKeydown = (event: KeyboardEvent, noteId: string): void => noteKeydown(event, noteId, {
  onToggle: (id, additive) => emit('select', { id, additive }),
  onEditTitle: (id) => emit('edit-title', { id }),
  onDelete: (id) => emit('delete-note', { id }),
  onMenu: (id) => emit('menu-request', {
    at: positionOf(id),
    screen: menuAnchorFor(viewport.value, id),
  }),
  onClearSelection: () => emit('select', { id: null, additive: false }),
})

const announcement = computed(() => selectionAnnouncement(props.selectedIds.length))

/** A note wears its domain, and its type's glyph.
 *
 * Both are read from the meta-ontology rather than invented here: the colours are keyed by the
 * generated `DOMAIN_NAMES`, and the glyph by the entity type the ontology declares — the same two
 * mechanisms the entity list and the picker already use, so a note and the element it becomes look
 * like the same thing before and after a lift.
 */
const domainTint = (note: Note): string | undefined =>
  note.domain ? getDomainColor(note.domain) : undefined
const glyphOf = (note: Note): string | null => archimateGlyphMarkup(note['element-type'])

/** How the ontology says this link is drawn. A link with no type has no notation and stays dashed
 * and headless, which is the honest picture of a relation nobody has named yet. */
const notationOf = (link: Link): RelationNotation | undefined => {
  const type = link['connection-type']
  return type ? props.notations.get(type) : undefined
}
const dashOf = (link: Link): string | undefined => notationDash(notationOf(link)?.line)
const markerUrl = (link: Link, end: 'source' | 'target'): string | undefined => {
  const marker = notationOf(link)?.[end]
  return marker && marker !== 'none' ? `url(#${edgeMarkerId(marker, end)})` : undefined
}

/** Focus is a viewport move, not a filter: the frame is fitted and the rest fades back. Nothing
 * leaves the document, because the cross-area links are the content worth having — which is why
 * this is one canvas rather than four tabs. */
watch(() => props.focusedAreaId, (areaId) => {
  if (!areaId) { resetView(); return }
  const rect = rectOf(areaId)
  if (rect.w && rect.h) fitTo(rect)
})

/** Whether a note or frame is outside the focus. Nothing is outside when nothing is focused. */
const outside = (areaId: string): boolean =>
  !!props.focusedAreaId && areaId !== props.focusedAreaId

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
    @contextmenu="onContextMenu"
    @wheel="onWheel"
  >
    <p
      class="sp-live"
      aria-live="polite"
      data-testid="selection-announcement"
    >
      {{ announcement }}
    </p>
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
          :class="{ dimmed: outside(area.id) }"
          :data-area-id="area.id"
          :x="rectOf(area.id).x"
          :y="rectOf(area.id).y"
          :width="rectOf(area.id).w"
          :height="rectOf(area.id).h"
          rx="12"
        />
        <text
          class="sp-area-label"
          :class="{ dimmed: outside(area.id) }"
          :x="rectOf(area.id).x + 16"
          :y="rectOf(area.id).y + 26"
        >
          {{ area.label }}
        </text>
      </g>
      <!-- The ontology's own `notation:` declaration, served by /api/relation-notations and drawn
           from the same shapes the graph explorer uses. -->
      <ScratchpadLinkMarkers />
      <g
        v-for="link in links"
        :key="link.id"
      >
        <!-- A fat invisible stroke under the visible one: a 1.5-px curve is not something anyone
             can reliably click, and a link has to be selectable to be refinable. -->
        <path
          class="sp-link-hit"
          :data-link-hit="link.id"
          :d="pathOf(link)"
          @pointerdown.stop="emit('select-link', { id: link.id })"
        />
        <path
          class="sp-link"
          :class="[link.verdict?.kind ?? 'unverified', {
            typed: !!link['connection-type'],
            selected: link.id === selectedLinkId,
          }]"
          :data-link-id="link.id"
          :data-verdict="link.verdict?.kind ?? 'unverified'"
          :d="pathOf(link)"
          :stroke-dasharray="dashOf(link)"
          :marker-start="markerUrl(link, 'source')"
          :marker-end="markerUrl(link, 'target')"
        />
      </g>
      <!-- A refusal is the one verdict that must be visible without hovering: it is the only one
           that stops a lift. -->
      <text
        v-for="link in refusedLinks"
        :key="`x-${link.id}`"
        class="sp-link-flag"
        :x="midpointOf(link).x"
        :y="midpointOf(link).y"
        text-anchor="middle"
      >✕</text>
      <path
        v-if="linkingFrom"
        class="sp-link drawing"
        :d="`M${positionOf(linkingFrom).x + NOTE_WIDTH / 2},${positionOf(linkingFrom).y + NOTE_HEIGHT / 2}
             L${pointer.x},${pointer.y}`"
      />
    </svg>

    <!-- A real multi-select listbox rather than a div with a blue border: selection is the state a
         lift acts on, so it has to be announced rather than only drawn. -->
    <div
      class="sp-layer"
      role="listbox"
      aria-multiselectable="true"
      aria-label="Notes on this scratchpad"
      :style="{ transform: layerTransform }"
    >
      <ScratchpadNote
        v-for="note in notes"
        :key="note.id"
        :note="note"
        :at="positionOf(note.id)"
        :selected="selectedIds.includes(note.id)"
        :tint="domainTint(note)"
        :dimmed="outside(note.area)"
        :glyph="glyphOf(note)"
        @note-pointerdown="onNotePointerDown($event, note.id)"
        @note-keydown="onNoteKeydown($event, note.id)"
        @title-blur="onTitleBlur($event, note)"
        @title-keydown="onTitleKeydown($event, note)"
        @handle-pointerdown="onHandlePointerDown($event, note.id)"
        @unbind="emit('unbind-note', { id: note.id })"
        @delete="emit('delete-note', { id: note.id })"
      />
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
/* Announced, never drawn: the visible state is the border, and repeating it in the corner would be
   noise for everyone who can see it. */
.sp-live {
  position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0;
  overflow: hidden; clip-path: inset(50%); white-space: nowrap;
}
.sp-note:focus-visible { outline: 2px solid #2563eb; outline-offset: 2px; }
.sp-area { fill: #ffffff; stroke: #e2e2e6; stroke-width: 1.5; }
/* Faded, not hidden: a link leaving the focused frame still has a visible other end, which is the
   whole reason focus is a viewport move rather than a filter. */
.sp-area.dimmed, .sp-area-label.dimmed { opacity: .35; }
.sp-area-label { font: 600 13px system-ui, sans-serif; fill: #8b8b93; letter-spacing: .02em; }
.sp-link { fill: none; stroke: #c3c6cc; stroke-width: 1.5; stroke-dasharray: 5 4; }
.sp-link-hit { fill: none; stroke: transparent; stroke-width: 14px; pointer-events: stroke; cursor: pointer; }
.sp-link.selected { stroke: #2563eb; stroke-width: 2.5; }
/* Solid once typed — unless the ontology says otherwise, in which case its own `notation:` line
   style wins through `stroke-dasharray` on the element. */
.sp-link.typed { stroke: #6b7280; stroke-dasharray: none; }
/* The verdict, at a glance. Permitted is settled and quiet; narrowed warns without blocking;
   refused is the only one that stops a lift, so it is the only one that shouts. */
.sp-link.permitted { stroke: #059669; stroke-dasharray: none; }
.sp-link.narrowed { stroke: #d97706; stroke-dasharray: none; }
.sp-link.refused { stroke: #dc2626; stroke-width: 2; stroke-dasharray: none; }
.sp-link.reference { stroke: #7c3aed; stroke-dasharray: 2 3; }
.sp-link-flag { font: 700 13px system-ui, sans-serif; fill: #dc2626; }
.sp-link.drawing { stroke: #2563eb; stroke-dasharray: 4 3; }


</style>
