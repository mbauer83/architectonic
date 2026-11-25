/**
 * The canvas editor's keys and double press (02·9, Q35, 01·10): Escape closes the open popover; the menu
 * key or Shift+F10 opens the menu of what is selected — a line's at its middle, a box's, a selection's or
 * an element's at its corner; F2 renames the selected element; a double press on a relation's label opens
 * the relation, on an element renames it. What each opens is the editor's: this only says which.
 */
import { ref, type Ref } from 'vue'
import type { CanvasPopoverLevel } from './useCanvasPopover'
import { asksForTheMenu, selectedLineMiddle } from '../components/lineMenuPlace'
import { elementAt } from './useContentGestures'

/** Which popover the editor opens for the selection's menu. */
export type MenuFor = Extract<CanvasPopoverLevel, 'line' | 'box' | 'selection' | 'element'>

export function useCanvasEditorKeys(parts: {
  host: Ref<HTMLElement | null>
  /** The popover open, if any; closing it is *close*. *source* is the shape a menu is opened on. */
  mode: Ref<CanvasPopoverLevel | null>
  source: Ref<string>
  close: (refocus: boolean) => void
  position: (x: number, y: number) => void
  /** What is selected: a line by its place, the one shape, and every shape. */
  selected: () => { line: number | null; shape: string | null; shapes: readonly string[] }
  /** The diagram's box *alias*, which has a menu of its own; undefined for any other shape. */
  boxNamed: (alias: string) => { readonly alias: string; readonly label: string } | undefined
  rename: (alias: string) => void
  editLine: (index: number) => void
}) {
  /** The box whose menu is open; null while none is. */
  const boxAt = ref<{ alias: string; label: string } | null>(null)
  const isBox = (alias: string) => parts.boxNamed(alias) !== undefined
  /** The menu *on* opened for *alias*; answers whether it opened, which a box's does only on a box. */
  const openMenu = (on: MenuFor, alias: string): boolean => {
    const box = on === 'box' ? parts.boxNamed(alias) : undefined
    if (on === 'box' && !box) return false
    parts.source.value = alias
    boxAt.value = box ? { alias: box.alias, label: box.label } : null
    parts.mode.value = on
    return true
  }

  const cornerOf = (alias: string) =>
    parts.host.value?.querySelector(`[data-alias="${CSS.escape(alias)}"]`)?.getBoundingClientRect()

  const key = (e: KeyboardEvent) => {
    const { line, shape, shapes } = parts.selected()
    if (e.key === 'Escape' && parts.mode.value) {
      e.stopPropagation()
      parts.close(true)
    }
    if (asksForTheMenu(e) && line !== null) {
      e.preventDefault()
      const middle = selectedLineMiddle(parts.host.value) ?? { x: 40, y: 40 }
      parts.position(middle.x, middle.y)
      openMenu('line', '')
    } else if (asksForTheMenu(e) && shape) {
      e.preventDefault()
      const corner = cornerOf(shape)
      parts.position(corner?.right ?? 40, corner?.top ?? 40)
      openMenu(shapes.length > 1 ? 'selection' : isBox(shape) ? 'box' : 'element', shape)
    }
    if (e.key === 'F2' && shape && !isBox(shape)) {
      e.preventDefault()
      const corner = cornerOf(shape)
      if (corner) parts.position(corner.left, corner.top)
      parts.rename(shape)
    }
  }

  const double = (e: MouseEvent) => {
    parts.position(e.clientX, e.clientY)
    const target = e.target instanceof Element ? e.target : null
    // A double press on a label opens its relation; on a line it adds a bend, which the canvas does.
    const label = target?.closest<SVGElement>('.lab-line-label[data-relation]')
    if (label) parts.editLine(Number(label.dataset.relation))
    else if (!target?.closest('[data-relation], .lab-line-handles')) {
      const alias = elementAt(e)?.dataset.alias
      if (alias) parts.rename(alias)
    }
  }

  return { key, double, openMenu, boxAt }
}
