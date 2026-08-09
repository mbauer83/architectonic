import { computed, ref, type Ref } from 'vue'

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
  readonly onSelect: (id: string | null) => void
  readonly onMoveNote: (id: string, x: number, y: number) => void
  readonly onCreateNote: (x: number, y: number) => void
  readonly onLinkNotes: (source: string, target: string) => void
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

  const toCanvas = (clientX: number, clientY: number): { x: number; y: number } => {
    const bounds = viewport.value?.getBoundingClientRect()
    return {
      x: ((clientX - (bounds?.left ?? 0)) - pan.value.x) / zoom.value,
      y: ((clientY - (bounds?.top ?? 0)) - pan.value.y) / zoom.value,
    }
  }

  const onNotePointerDown = (event: PointerEvent, noteId: string): void => {
    event.stopPropagation()
    intents.onSelect(noteId)
    const at = toCanvas(event.clientX, event.clientY)
    const position = positionOf(noteId)
    dragging.value = { id: noteId, offsetX: at.x - position.x, offsetY: at.y - position.y }
  }

  const onHandlePointerDown = (event: PointerEvent, noteId: string): void => {
    event.stopPropagation()
    event.preventDefault()
    linkingFrom.value = noteId
    pointer.value = toCanvas(event.clientX, event.clientY)
  }

  const onBackgroundPointerDown = (event: PointerEvent): void => {
    intents.onSelect(null)
    panning.value = { x: event.clientX - pan.value.x, y: event.clientY - pan.value.y }
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
      const target = (event.target as HTMLElement | null)?.closest<HTMLElement>('[data-note-id]')
      const targetId = target?.dataset.noteId
      if (targetId && targetId !== linkingFrom.value) {
        intents.onLinkNotes(linkingFrom.value, targetId)
      }
      linkingFrom.value = null
    }
    dragging.value = null
    panning.value = null
  }

  /** Double-click rather than long-press: long-press is the touch equivalent, and making it the
   * desktop primary would compete with drag-select. */
  const onBackgroundDoubleClick = (event: MouseEvent): void => {
    const at = toCanvas(event.clientX, event.clientY)
    intents.onCreateNote(at.x - noteSize.width / 2, at.y - noteSize.height / 2)
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

  return {
    layerTransform, linkingFrom, pointer, resetView,
    onNotePointerDown, onHandlePointerDown, onBackgroundPointerDown,
    onPointerMove, onPointerUp, onBackgroundDoubleClick, onWheel,
  }
}
