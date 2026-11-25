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
import { GRID } from '../../domain/layout/lab/labSnapping'
import { type BendRef, withBendsMoved } from '../../domain/layout/lab/labSelection'
import type { DrawnMembership } from '../../domain/layout/diagramMembership'
import type { Extent } from '../../domain/layout/geometry'
import type { ReadingLens } from '../../domain/readingLens'
import type { DiagramContext } from '../../domain'
import { extentOfMarks, type OverviewMark } from '../lib/diagramOverview'
import type { CanvasFocus } from '../components/layoutLab/useCanvasFocus'
import { useEditPanel } from './useEditPanel'
import { useDiagramEditing } from './useDiagramEditing'
import { type EditKey, editKeyOf } from './editModeKeys'
import { useEditingPreferences } from './useEditingPreferences'
import { useSurroundPlacement } from './useSurroundPlacement'
import type { ShowToast } from '../keys'

/** How far the arrows nudge a picked label: two pixels, or one with Shift (02·5). */
const LABEL_STEP = 2

/** What the page's canvas and edit bar let the keys ask of them. */
export interface CanvasHandle {
  readonly selected: string | null
  readonly selection: readonly string[]
  readonly selectedLine: number | null
  readonly hasSelection: boolean
  readonly removePickedBend: () => boolean
  readonly selectedBends: readonly BendRef[]
  readonly removeSelectedBends: () => boolean
  readonly clearSelection: () => void
  readonly select: (alias: string) => void
  readonly sweepFrom: (event: PointerEvent) => void
  readonly focus: Pick<CanvasFocus, 'step' | 'enter' | 'towards' | 'selectAll'>
  readonly focusedExtent: Extent | null
  readonly announced: string
  readonly nudgeLabel: (dx: number, dy: number) => boolean
}
export interface EditBarHandle {
  readonly closeList: () => boolean
}

/** The window onto the picture, as the keys move it: show a part, follow a shape, pan by a fraction. */
export interface EditWindow {
  readonly frame: (extent: Extent) => void
  readonly reveal: (extent: Extent) => void
  readonly panBy: (across: number, down: number) => void
}

const isTyping = (target: EventTarget | null): boolean =>
  target instanceof HTMLElement
  && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))

/** Whether *target* is the canvas itself, or a shape on it, rather than a control in its corner. */
const onTheCanvas = (host: HTMLElement | null, target: EventTarget | null): boolean =>
  target instanceof Element && Boolean(host?.contains(target)) && !target.closest('button, a, input, select, textarea')

export function useDiagramEditMode(
  svc: ModelService,
  diagramId: Ref<string>,
  parts: {
    canvas: Ref<CanvasHandle | null>; bar: Ref<EditBarHandle | null>; membership: () => DrawnMembership | null
    /** The window the keys move, the element it is drawn in, and whether the diagram is too large to see whole. */
    view: EditWindow; host: Ref<HTMLElement | null>; large: () => boolean
    /** The reader's lens, which the picture being arranged keeps showing (owner, 2026-11-25). */
    lens?: () => ReadingLens
    /** The diagram's context read: what names the elements in the list of changes. */
    context?: () => DiagramContext | null
  },
  onLeft: () => void,
  toast: ShowToast,
) {
  const editing = useDiagramEditing(svc, () => diagramId.value, parts.membership, {
    onMembershipSaved: onLeft, lens: () => parts.lens?.(), context: parts.context,
  })
  const active = ref(false)
  const leaving = ref(false)
  const spaceHeld = ref(false)
  /** Whether the layout's rule breaches are marked on the canvas: off until asked for, never opened for one. */
  const checking = ref(false)
  const toggleCheck = () => { checking.value = !checking.value }
  const told = new Set<string>()
  const session = editing.session
  const panel = useEditPanel(parts.large)
  const prefs = useEditingPreferences()
  /** The title and the legend where the saved picture will draw them, placed by the composer's rule. */
  const surround = useSurroundPlacement(session, (placement) => svc.placeSurround(diagramId.value, placement))

  /** The shapes selected, where they are now: what the overview marks and `F` frames. */
  const marks = computed((): OverviewMark[] => {
    const where = session.placement.value
    return where ? (parts.canvas.value?.selection ?? []).flatMap((alias) => {
      const extent = where.elements.get(alias) ?? where.boxes.get(alias)
      return extent ? [{ id: alias, extent, selected: true }] : []
    }) : []
  })
  const selectionExtent = computed(() => extentOfMarks(marks.value))
  /** The shapes the panel points at — the two ends of a relation its row would draw (01·8), by alias. */
  const outlined = ref<readonly string[]>([])
  const outline = (aliases: readonly string[]) => { outlined.value = aliases }
  /** Select the shape *alias*, as the panel does for an element already drawn, and bring it into view. */
  const select = (alias: string) => {
    parts.canvas.value?.select(alias)
    const extent = session.placement.value?.elements.get(alias) ?? session.placement.value?.boxes.get(alias)
    if (extent) parts.view.reveal(extent)
  }

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
  const nudge = (
    selection: readonly string[], bends: readonly BendRef[], [x, y]: readonly [number, number], by: number,
    resize: boolean,
  ) => {
    const [alias] = selection
    if (resize && selection.length !== 1) return
    session.change((geometry, from, placement) => {
      if (!resize) {
        return movedTogether(geometry, withBendsMoved(geometry, from, bends, selection, x * by, y * by), selection,
          x * by, y * by)
      }
      const extent = placement.elements.get(alias) ?? placement.boxes.get(alias)
      const least = placement.boxes.has(alias) ? 1 : SMALLEST_ELEMENT
      return extent ? resized(geometry, from, alias, resizedExtent(extent, 'se', x * by, y * by, least)) : from
    })
  }

  /** The window follows the shape the keyboard is on, by the least move that shows it (02·9). */
  const followFocus = () => {
    const extent = parts.canvas.value?.focusedExtent
    if (extent) parts.view.reveal(extent)
  }

  /** An arrow: a picked label nudged, else the selection nudged, else the focus moved — or the window panned. */
  const arrow = (key: Extract<EditKey, { kind: 'arrow' }>, inCanvas: boolean): boolean => {
    const canvas = parts.canvas.value
    const [x, y] = key.direction
    const label = key.fine ? 1 : LABEL_STEP
    if (!canvas || (!key.resize && canvas.nudgeLabel(x * label, y * label))) return Boolean(canvas)
    if (canvas.selection.length || canvas.selectedBends.length) {
      nudge(canvas.selection, canvas.selectedBends, key.direction, key.fine ? 1 : GRID, key.resize)
    }
    else if (!inCanvas) return false
    else if (canvas.focus.towards({ x, y })) followFocus()
    else parts.view.panBy(x / 5, y / 5)
    return true
  }

  /** What *key* does, given whether it was pressed on the canvas; answers whether it was taken. */
  const perform = (key: EditKey, inCanvas: boolean): boolean => {
    const canvas = parts.canvas.value
    switch (key.kind) {
      case 'escape': escape(); return true
      case 'undo': session.undo(); return true
      case 'redo': session.redo(); return true
      case 'delete':
        // A picked bend goes; otherwise the selection is removed from the diagram only (owner's standing
        // rule) — deleting from the model is a menu command, and a line is not removed here.
        if (!canvas?.hasSelection) return false
        if (!canvas.removePickedBend() && canvas.selectedLine === null) {
          canvas.removeSelectedBends()
          if (canvas.selection.length) editing.remove(canvas.selection)
          canvas.clearSelection()
        }
        return true
      case 'arrow': return arrow(key, inCanvas)
      case 'restack':
        if (canvas?.selection.length) editing.restack(canvas.selection, key.how)
        return Boolean(canvas?.selection.length)
      case 'frame':
        if (selectionExtent.value) parts.view.frame(selectionExtent.value)
        return Boolean(selectionExtent.value)
      case 'pan': spaceHeld.value = true; return true
      case 'rectangle': {
        const rule = prefs.switchRectangle()
        toast(`A selection rectangle now selects ${rule === 'touches' ? 'every element it touches'
          : 'only the elements it encloses'}.`, 'info', 3000)
        return true
      }
      case 'tab': {
        const moved = inCanvas && Boolean(canvas?.focus.step(key.forward))
        if (moved) followFocus()
        return moved
      }
      case 'enter':
        if (!inCanvas) return false
        canvas?.focus.enter(key.toggle)
        followFocus()
        return true
      case 'select-all':
        if (inCanvas) canvas?.focus.selectAll()
        return inCanvas
    }
  }

  const onKey = (event: KeyboardEvent) => {
    if (!active.value || isTyping(event.target)) return
    const key = editKeyOf(event)
    if (key && perform(key, onTheCanvas(parts.host.value, event.target))) event.preventDefault()
  }
  const onKeyUp = (event: KeyboardEvent) => { if (event.key === ' ') spaceHeld.value = false }

  /** A press on the canvas pans only while Space is held: otherwise it is the canvas's to select and move. */
  const panPress = (event: MouseEvent, pan: (event: MouseEvent) => void) => {
    if (spaceHeld.value) pan(event)
  }

  // Said once per diagram, at the moment it happens: the picture is now arranged by hand. The toast's
  // Undo goes back to the automatic picture the step took over, taking back what followed it too.
  watch(() => session.state.value?.byHand, (byHand, was) => {
    if (!active.value || !byHand || was !== false || told.has(diagramId.value)) return
    const automatic = session.history.value.at(-1)
    if (!automatic) return
    told.add(diagramId.value)
    const undoTakeover = () => {
      for (let steps = session.history.value.length; steps > 0 && session.history.value.includes(automatic); steps--) {
        session.undo()
      }
    }
    toast(
      'Arranged by hand from here on. Undo, or “Return to automatic”, gives the automatic layout back.',
      'info', 8000, { label: 'Undo', run: undoTakeover },
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
    editing, session, active, leaving, spaceHeld, panel, marks, checking, toggleCheck, surround,
    outlined, outline, select, escape,
    canUndo: computed(() => session.history.value.length > 0),
    canRedo: computed(() => session.future.value.length > 0),
    enter, done, saveAndExit, discardAndExit, keepEditing, panPress,
  }
}

export type DiagramEditMode = ReturnType<typeof useDiagramEditMode>
