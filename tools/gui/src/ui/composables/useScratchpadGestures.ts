import { computed, ref, type Ref } from 'vue'
import { isAdditive } from './useScratchpadKeyboard'

/**
 * Pan, zoom, drag, and the link-drawing gesture.
 *
 * Extracted from `ScratchpadCanvas.vue` because the component had grown past the file-size limit,
 * and this is the seam that makes sense: what the canvas *does* when a pointer moves, apart from
 * what it draws. It reports intents through callbacks rather than mutating a document — the
 * document, its undo history and when to save all belong to the view, which is what keeps "one
 * write a second" a property with a test rather than an accident of a mouse handler.
 */

export interface CanvasGestureIntents {
  /** `additive` is a shift-click (or ctrl / cmd — see `isAdditive`): it adds to the selection
   * rather than replacing it, which is what makes a lift's selection expressible without a marquee
   * competing with the pan gesture the background drag already owns. */
  readonly onSelect: (id: string | null, additive: boolean) => void
  readonly onMoveNote: (id: string, x: number, y: number) => void
  readonly onCreateNote: (x: number, y: number) => void
  readonly onLinkNotes: (source: string, target: string) => void
  /** Where to put something, in canvas coordinates, and where to draw the menu asking what —
   * in viewport pixels, because the menu is rendered outside the transformed layer so it does
   * not shrink with the zoom. */
  readonly onOpenMenu: (at: { x: number; y: number }, screen: { x: number; y: number }) => void
}

export function useScratchpadGestures(
  viewport: Ref<HTMLElement | null>,
  positionOf: (id: string) => { x: number; y: number },
  noteSize: { width: number; height: number },
  intents: CanvasGestureIntents,
) {
  const pan = ref({ x: 0, y: 0 })
  const zoom = ref(1)
  const dragging = ref<{ id: string; offsetX: number; offsetY: number } | null>(null)
  const panning = ref<{ x: number; y: number } | null>(null)
  /** The note a link is being drawn from. Held here rather than in the document, because an
   * abandoned gesture must leave nothing behind to undo. */
  const linkingFrom = ref<string | null>(null)
  const pointer = ref({ x: 0, y: 0 })

  /** One string, set on both layers, so notes and links cannot drift apart. */
  const layerTransform = computed(
    () => `translate(${pan.value.x}px, ${pan.value.y}px) scale(${zoom.value})`,
  )

  /** A gesture owns the pointer until it ends.
   *
   * Without this a drag died the moment the cursor crossed the note panel — an absolutely
   * positioned *sibling* of the viewport, not a child of it. The pointer left `.sp-viewport`,
   * `pointerleave` ended the gesture, and a note being dragged toward the top-left of its own
   * canvas simply stopped following the cursor. The browser suite recorded it as a drag that wrote
   * nothing at all, which is what it was.
   *
   * Capturing routes every later pointer event to the viewport whatever is drawn on top of it, so
   * a gesture now ends when the button comes up and at no other time — including when it comes up
   * outside the window, which `pointerleave` also could not see.
   */
  const capture = (event: PointerEvent): void => {
    // A synthetic PointerEvent names no live pointer and capture throws for it. Capture is what
    // keeps a gesture alive across an overlay, not what starts it, so failing to take it must
    // leave the gesture working rather than refuse it.
    try { viewport.value?.setPointerCapture(event.pointerId) } catch { /* no such active pointer */ }
  }

  const release = (event: PointerEvent): void => {
    try { viewport.value?.releasePointerCapture(event.pointerId) } catch { /* never captured */ }
  }

  const toCanvas = (clientX: number, clientY: number): { x: number; y: number } => {
    const bounds = viewport.value?.getBoundingClientRect()
    return {
      x: ((clientX - (bounds?.left ?? 0)) - pan.value.x) / zoom.value,
      y: ((clientY - (bounds?.top ?? 0)) - pan.value.y) / zoom.value,
    }
  }

  const onNotePointerDown = (event: PointerEvent, noteId: string): void => {
    event.stopPropagation()
    intents.onSelect(noteId, isAdditive(event))
    const at = toCanvas(event.clientX, event.clientY)
    const position = positionOf(noteId)
    dragging.value = { id: noteId, offsetX: at.x - position.x, offsetY: at.y - position.y }
    capture(event)
  }

  const onHandlePointerDown = (event: PointerEvent, noteId: string): void => {
    event.stopPropagation()
    event.preventDefault()
    linkingFrom.value = noteId
    pointer.value = toCanvas(event.clientX, event.clientY)
    capture(event)
  }

  const onBackgroundPointerDown = (event: PointerEvent): void => {
    intents.onSelect(null, false)
    panning.value = { x: event.clientX - pan.value.x, y: event.clientY - pan.value.y }
    capture(event)
  }

  const onPointerMove = (event: PointerEvent): void => {
    if (dragging.value) {
      const at = toCanvas(event.clientX, event.clientY)
      intents.onMoveNote(
        dragging.value.id, at.x - dragging.value.offsetX, at.y - dragging.value.offsetY,
      )
      return
    }
    if (linkingFrom.value) {
      pointer.value = toCanvas(event.clientX, event.clientY)
      return
    }
    if (panning.value) {
      pan.value = { x: event.clientX - panning.value.x, y: event.clientY - panning.value.y }
    }
  }

  const onPointerUp = (event: PointerEvent): void => {
    if (linkingFrom.value) {
      // What is under the cursor, not what the event was dispatched to: while the pointer is
      // captured every event targets the viewport, so reading `event.target` would find the canvas
      // and never the note the link was dropped on. Hit-testing the point is also the more honest
      // question — a drop lands where the cursor is.
      const under = window.document.elementFromPoint(event.clientX, event.clientY)
      const targetId = under?.closest<HTMLElement>('[data-note-id]')?.dataset.noteId
      if (targetId && targetId !== linkingFrom.value) {
        intents.onLinkNotes(linkingFrom.value, targetId)
      }
      linkingFrom.value = null
    }
    dragging.value = null
    panning.value = null
    release(event)
  }

  /** Double-click rather than long-press: long-press is the touch equivalent, and making it the
   * desktop primary would compete with drag-select. */
  const onBackgroundDoubleClick = (event: MouseEvent): void => {
    const at = toCanvas(event.clientX, event.clientY)
    intents.onCreateNote(at.x - noteSize.width / 2, at.y - noteSize.height / 2)
  }

  /** Right-click is "act here". The point is the gesture: area membership on a scratchpad is
   * spatial, so whatever the menu adds belongs where the menu was opened — which is also why the
   * per-frame button this replaces had to invent a placement rule and this does not. */
  const onContextMenu = (event: MouseEvent): void => {
    event.preventDefault()
    const bounds = viewport.value?.getBoundingClientRect()
    // Kept inside the viewport, which clips its overflow: a menu opened near the right or bottom
    // edge would otherwise be half a menu. The box is the widest state — the search — because a
    // menu that fits when it opens and is clipped when it widens is worse than one that never moves.
    const menuBox = { width: 400, height: 220 }
    const width = bounds?.width ?? menuBox.width
    const height = bounds?.height ?? menuBox.height
    intents.onOpenMenu(toCanvas(event.clientX, event.clientY), {
      x: Math.max(0, Math.min(event.clientX - (bounds?.left ?? 0), width - menuBox.width)),
      y: Math.max(0, Math.min(event.clientY - (bounds?.top ?? 0), height - menuBox.height)),
    })
  }

  const onWheel = (event: WheelEvent): void => {
    event.preventDefault()
    const factor = event.deltaY < 0 ? 1.1 : 1 / 1.1
    const next = Math.min(3, Math.max(0.2, zoom.value * factor))
    // Zoom about the pointer, so the thing under the cursor stays under it.
    const bounds = viewport.value?.getBoundingClientRect()
    const px = event.clientX - (bounds?.left ?? 0)
    const py = event.clientY - (bounds?.top ?? 0)
    pan.value = {
      x: px - ((px - pan.value.x) / zoom.value) * next,
      y: py - ((py - pan.value.y) / zoom.value) * next,
    }
    zoom.value = next
  }

  const resetView = (): void => { pan.value = { x: 0, y: 0 }; zoom.value = 1 }

  /** Bring one rectangle into view, centred, with a little room around it.
   *
   * Focus mode's whole gesture: a frame is a region of the workspace, so focusing one is a matter
   * of where the viewport is rather than of hiding anything from the document. Nothing is removed —
   * the cross-area links are the content worth having, and a mode that hid them would defeat the
   * reason the canvas is one surface rather than four tabs.
   */
  const fitTo = (rect: { x: number; y: number; w: number; h: number }): void => {
    const bounds = viewport.value?.getBoundingClientRect()
    if (!bounds || !rect.w || !rect.h) return
    const margin = 40
    const next = Math.min(
      3,
      Math.max(0.2, Math.min(
        (bounds.width - margin * 2) / rect.w,
        (bounds.height - margin * 2) / rect.h,
      )),
    )
    zoom.value = next
    pan.value = {
      x: bounds.width / 2 - (rect.x + rect.w / 2) * next,
      y: bounds.height / 2 - (rect.y + rect.h / 2) * next,
    }
  }

  return {
    layerTransform, linkingFrom, pointer, resetView, fitTo,
    onNotePointerDown, onHandlePointerDown, onBackgroundPointerDown,
    onPointerMove, onPointerUp, onBackgroundDoubleClick, onContextMenu, onWheel,
  }
}
