<script setup lang="ts">
/**
 * One note on the canvas.
 *
 * Its own component because a note is the thing this feature is about, and because the canvas was
 * past the source-length limit — the seam being what a note *is* against the surface it sits on.
 * It knows nothing about gestures: every interaction is an event the canvas interprets, so the
 * pan/zoom/drag state stays in one place and this stays a card.
 */
import type { Note } from '../../domain/schemas/scratchpads'

defineProps<{
  note: Note
  /** Canvas coordinates. The transform lives here so a move is one style write on one element. */
  at: { x: number; y: number }
  selected: boolean
  /** The domain's colour, or nothing when the note has decided nothing — which is a real state. */
  tint: string | undefined
  /** The entity type's glyph markup, from the table the entity list and picker already use. */
  glyph: string | null
  /** Outside the focused frame: faded back, still there, still linkable. */
  dimmed: boolean
}>()

const emit = defineEmits<{
  (event: 'note-pointerdown', payload: PointerEvent): void
  (event: 'note-keydown', payload: KeyboardEvent): void
  (event: 'title-blur', payload: FocusEvent): void
  (event: 'title-keydown', payload: KeyboardEvent): void
  (event: 'handle-pointerdown', payload: PointerEvent): void
  (event: 'unbind'): void
  (event: 'delete'): void
}>()
</script>

<!-- eslint-disable vue/no-v-html -- one directive, on the glyph below: generated markup from a
     checked-in table keyed by entity type, with no path from user content to it. -->
<template>
  <article
    class="sp-note"
    role="option"
    tabindex="0"
    :aria-selected="selected"
    :class="{
      selected: selected,
      typed: !!note['element-type'],
      bound: !!note['model-ref'],
    }"
    :data-note-id="note.id"
    :data-area="note.area"
    :data-domain="note.domain ?? ''"
    :style="{ transform: `translate(${at.x}px, ${at.y}px)`, borderLeftColor: tint }"
    @pointerdown="emit('note-pointerdown', $event)"
    @keydown="emit('note-keydown', $event)"
  >
    <!-- `contenteditable` rather than a positioned <input>: real text editing, IME and
         spellcheck come free, which is the whole argument for HTML notes. -->
    <div
      class="sp-title"
      contenteditable="plaintext-only"
      spellcheck="true"
      tabindex="-1"
      :aria-label="`Title of ${note.title}`"
      :data-note-title="note.id"
      @pointerdown.stop
      @blur="emit('title-blur', $event)"
      @keydown="emit('title-keydown', $event)"
    >
      {{ note.title }}
    </div>
    <footer class="sp-meta">
      <!-- The glyph is generated markup from a checked-in table keyed by entity type; no user
           content reaches it, which is why `v-html` is safe here and nowhere near a title. -->
      <svg
        v-if="glyph"
        class="sp-glyph"
        viewBox="0 0 16 16"
        aria-hidden="true"
        v-html="glyph"
      />
      <button
        v-if="note['model-ref']?.kind === 'bound'"
        type="button"
        class="sp-type sp-bound"
        :data-unbind-note="note.id"
        :title="`Bound to ${note['model-ref']['artifact-id']} — click to release`"
        @pointerdown.stop
        @click.stop="emit('unbind')"
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
        @click.stop="emit('delete')"
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
      @pointerdown="emit('handle-pointerdown', $event)"
    />
  </article>
</template>

<style scoped>
.sp-note {
  position: absolute; top: 0; left: 0; width: 132px; height: 120px; box-sizing: border-box;
  display: flex; flex-direction: column;
  padding: 8px 10px 6px; background: #fff; border: 1px solid #dcdce1; border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0,0,0,.06); cursor: default;
  transition: box-shadow .12s ease, border-color .12s ease;
}
.sp-note:hover { box-shadow: 0 2px 6px rgba(0,0,0,.10); }
.sp-note.dimmed { opacity: .3; }
.sp-note.dimmed:hover, .sp-note.dimmed:focus-within { opacity: .75; }
.sp-note.selected { border-color: #2563eb; box-shadow: 0 0 0 2px rgba(37,99,235,.18); }
/* The domain is the tint; the border simply becomes visible once anything has been decided. A
   note that has decided nothing wears nothing, which is the state the feature exists to allow. */
.sp-note.typed, .sp-note[data-domain]:not([data-domain='']) { border-left: 3px solid #7c3aed; }
.sp-note.bound { border-left: 3px solid #059669; }
.sp-glyph { width: 13px; height: 13px; flex: 0 0 auto; color: #6b7280; }
.sp-bound {
  border: none; background: none; padding: 0; cursor: pointer;
  color: #059669; font-size: 10.5px; font-weight: 600;
}
.sp-bound:hover { text-decoration: line-through; }
/* The title *is* the note: it takes the whole card and the metadata sits under it, rather than the
   other way round. A thought is what this holds. */
.sp-title {
  flex: 1 1 auto; font-size: 13px; line-height: 1.3; color: #1f2328; outline: none;
  word-break: break-word; overflow: hidden; cursor: text;
}
.sp-title:focus { box-shadow: inset 0 -1px 0 #2563eb; }
.sp-meta {
  display: flex; align-items: center; gap: 4px; justify-content: space-between;
  margin-top: 4px; flex: 0 0 auto;
}
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
