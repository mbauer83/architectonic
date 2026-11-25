/**
 * View mode and edit mode on a diagram's own page (D15): entering, the keys, and the ways out.
 *
 * - **Escape steps outward** (owner, F1), wherever focus is on the page: an open list of changes, then
 *   the leave choice, then the selection, then edit mode itself — which leaves at once when nothing
 *   is unsaved, and otherwise asks, in the edit bar, *Save and exit*, *Discard and exit* or *Keep
 *   editing* (Q2). A text field keeps its own Escape.
 * - **Done** is the same last step.
 * - **Save** is one press and stays in edit mode (Q4); **Discard** returns to the last save.
 * - **Space held** turns a press on the canvas into a pan; the wheel zooms as in view mode.
 * - The first move of an automatically laid-out picture takes it over (D16): said once, in a toast.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Ref } from 'vue'
import type { ModelService } from '../../application/ModelService'
import { SMALLEST_ELEMENT, movedTogether, resized, resizedExtent } from '../../domain/layout/lab/labArrangement'
import type { DrawnMembership } from '../../domain/layout/diagramMembership'
import type { Extent } from '../../domain/layout/geometry'
import { extentOfMarks, type OverviewMark } from '../lib/diagramOverview'
import { useEditPanel } from './useEditPanel'
import { useDiagramEditing } from './useDiagramEditing'
import { restackKey } from '../components/canvasElementMenu'

/** How far an arrow moves or resizes a shape: the grid, or one pixel with Shift. */
const GRID = 8

/** Each arrow key as the direction it moves in, read by the character it produces, not its position. */
const ARROWS: Readonly<Record<string, readonly [number, number]>> = {
  ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1],
}

/** What the page's canvas and edit bar let the keys ask of them. */
export interface CanvasHandle {
  readonly selected: string | null
  readonly selection: readonly string[]
  readonly selectedLine: number | null
  readonly hasSelection: boolean
  readonly removePickedBend: () => boolean
  readonly clearSelection: () => void
  readonly sweepFrom: (event: PointerEvent) => void
}
export interface EditBarHandle {
  readonly closeList: () => boolean
}

type Toast = (message: string, type?: 'info' | 'warn' | 'error', durationMs?: number) => void

const isTyping = (target: EventTarget | null): boolean =>
  target instanceof HTMLElement
  && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))

export function useDiagramEditMode(
  svc: ModelService,
  diagramId: Ref<string>,
  parts: {
    canvas: Ref<CanvasHandle | null>; bar: Ref<EditBarHandle | null>; membership: () => DrawnMembership | null
    /** Show a part of the picture in the window (`F`); and whether the diagram is too large to see whole. */
    frame: (extent: Extent) => void; large: () => boolean
  },
  onLeft: () => void,
  toast: Toast,
) {
  const editing = useDiagramEditing(svc, () => diagramId.value, parts.membership, onLeft)
  const active = ref(false)
  const leaving = ref(false)
  const spaceHeld = ref(false)
  /** Whether the layout's rule breaches are marked on the canvas: off until asked for, never opened for one. */
  const checking = ref(false)
  const toggleCheck = () => { checking.value = !checking.value }
  const told = new Set<string>()
  const session = editing.session
  const panel = useEditPanel(parts.large)

  /** The shapes selected, where they are now: what the overview marks and `F` frames. */
  const marks = computed((): OverviewMark[] => {
    const where = session.placement.value
    return where ? (parts.canvas.value?.selection ?? []).flatMap((alias) => {
      const extent = where.elements.get(alias) ?? where.boxes.get(alias)
      return extent ? [{ id: alias, extent, selected: true }] : []
    }) : []
  })
  const selectionExtent = computed(() => extentOfMarks(marks.value))

  const enter = async () => {
    leaving.value = false
    if (await editing.open()) { active.value = true; panel.opened() }
    else {
      const why = editing.error.value ?? 'its picture could not be read'
      toast(`This diagram cannot be arranged here: ${why}`, 'error')
    }
  }

  const exit = () => {
    active.value = false
    leaving.value = false
    onLeft()
  }

  /** Done, or Escape with nothing else to close: leave, or ask how when something is unsaved. */
  const done = () => {
    if (editing.changes.value.length === 0) exit()
    else leaving.value = true
  }

  const saveAndExit = async () => { if (await editing.save()) exit() }
  const discardAndExit = () => { editing.discard(); exit() }
  const keepEditing = () => { leaving.value = false }

  const escape = () => {
    if (parts.bar.value?.closeList()) return
    if (leaving.value) return keepEditing()
    if (parts.canvas.value?.hasSelection) return parts.canvas.value.clearSelection()
    done()
  }

  /**
   * The selection moved by the arrows, or one selected shape resized by Alt and the arrows from its
   * right and bottom edges (Q35): one undoable step each, *by* pixels at a time.
   */
  const nudge = (selection: readonly string[], [x, y]: readonly [number, number], by: number, resize: boolean) => {
    const [alias] = selection
    if (resize && selection.length !== 1) return
    session.change((geometry, from, placement) => {
      if (!resize) return movedTogether(geometry, from, selection, x * by, y * by)
      const extent = placement.elements.get(alias) ?? placement.boxes.get(alias)
      const least = placement.boxes.has(alias) ? 1 : SMALLEST_ELEMENT
      return extent ? resized(geometry, from, alias, resizedExtent(extent, 'se', x * by, y * by, least)) : from
    })
  }

  const onKey = (event: KeyboardEvent) => {
    if (!active.value || isTyping(event.target)) return
    const command = event.ctrlKey || event.metaKey
    const key = event.key.toLowerCase()
    if (event.key === 'Escape') {
      event.preventDefault()
      escape()
    } else if (command && key === 'z') {
      event.preventDefault()
      if (event.shiftKey) session.redo()
      else session.undo()
    } else if (command && key === 'y') {
      event.preventDefault()
      session.redo()
    } else if ((event.key === 'Delete' || event.key === 'Backspace') && parts.canvas.value?.hasSelection) {
      // A picked bend goes; otherwise the selection is removed from the diagram only (owner's standing
      // rule) — deleting from the model is a menu command, and a line is not removed here.
      event.preventDefault()
      if (parts.canvas.value.removePickedBend() || parts.canvas.value.selectedLine !== null) return
      editing.remove(parts.canvas.value.selection)
      parts.canvas.value.clearSelection()
    } else if (event.key in ARROWS && parts.canvas.value?.selection.length) {
      event.preventDefault()
      nudge(parts.canvas.value.selection, ARROWS[event.key], event.shiftKey ? 1 : GRID, event.altKey)
    } else if (restackKey(event) !== null && parts.canvas.value?.selection.length) {
      event.preventDefault()
      editing.restack(parts.canvas.value.selection, restackKey(event) ?? 'front')
    } else if (key === 'f' && !command && selectionExtent.value) {
      event.preventDefault()
      parts.frame(selectionExtent.value)
    } else if (event.key === ' ') {
      event.preventDefault()
      spaceHeld.value = true
    }
  }
  const onKeyUp = (event: KeyboardEvent) => { if (event.key === ' ') spaceHeld.value = false }

  /** A press on the canvas pans only while Space is held: otherwise it is the canvas's to select and move. */
  const panPress = (event: MouseEvent, pan: (event: MouseEvent) => void) => {
    if (spaceHeld.value) pan(event)
  }

  // Said once per diagram, at the moment it happens: the picture is now arranged by hand.
  watch(() => session.state.value?.byHand, (byHand, was) => {
    if (!active.value || !byHand || was !== false || told.has(diagramId.value)) return
    if (session.history.value.length === 0) return
    told.add(diagramId.value)
    toast(
      'Arranged by hand from here on. Undo, or “Return to automatic”, gives the automatic layout back.',
      'info', 6000,
    )
  })

  // Leaving the page with the session open leaves nothing behind.
  watch(diagramId, () => { active.value = false; leaving.value = false })

  onMounted(() => {
    window.addEventListener('keydown', onKey)
    window.addEventListener('keyup', onKeyUp)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('keydown', onKey)
    window.removeEventListener('keyup', onKeyUp)
  })

  return {
    editing, session, active, leaving, spaceHeld, panel, marks, checking, toggleCheck,
    canUndo: computed(() => session.history.value.length > 0),
    canRedo: computed(() => session.future.value.length > 0),
    enter, done, saveAndExit, discardAndExit, keepEditing, panPress,
  }
}

export type DiagramEditMode = ReturnType<typeof useDiagramEditMode>
