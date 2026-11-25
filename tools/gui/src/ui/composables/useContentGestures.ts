import { onBeforeUnmount, type Ref } from 'vue'
import { lineEndNear } from '../../domain/layout/lab/labRouteEdits'
import { pointOnPicture } from '../components/layoutLab/pointerOnPicture'
import type { DiagramEditing } from './useDiagramEditing'

/** How near a line's end, on screen, a press picks the line rather than the element's edge (Q33). */
const NEAR_AN_END = 6

export const elementAt = (event: Event) =>
  event.target instanceof Element ? event.target.closest<SVGGElement>('[data-alias]') : null

export function useContentGestures(
  host: Ref<HTMLElement | null>, editing: DiagramEditing, source: Ref<string>,
  position: (x: number, y: number) => void, rename: (alias: string) => void,
  editLine: (index: number) => void, pair: (alias: string) => void,
  /** An element moved and dropped over another shape: what it was dropped on, by alias. */
  droppedOn: (alias: string, target: string, x: number, y: number) => void = () => {},
) {
  let hold: ReturnType<typeof setTimeout> | undefined
  let down: { alias: string; x: number; y: number; edge: boolean; travelled?: boolean } | null = null
  function release() {
    clearTimeout(hold)
    down = null
  }
  onBeforeUnmount(release)
  function press(e: PointerEvent) {
    if (e.button !== 0) return
    // A press on a line, or where one ends on an element's edge, is the canvas's: it selects the line
    // (`useLineGesture`); held without travel it opens the relation, and the edge draws nothing.
    const line = (e.target as Element).closest<SVGElement>('[data-relation]')
    const svg = host.value?.querySelector('svg') ?? null
    const pixel = svg ? 1 / (svg.getScreenCTM()?.a || 1) : 1
    const endpoint = lineEndNear(editing.session.courses.value, pointOnPicture(svg, e), NEAR_AN_END * pixel)
    if (line || endpoint) {
      const index = endpoint?.line ?? Number(line?.dataset.relation)
      position(e.clientX, e.clientY)
      down = { alias: '', x: e.clientX, y: e.clientY, edge: false }
      hold = setTimeout(() => editLine(index), 550)
      return
    }
    const el = elementAt(e)
    if (!el) return
    const alias = el.dataset.alias ?? ''
    const rect = el.getBoundingClientRect()
    const edge =
      Math.min(
        Math.abs(e.clientX - rect.left),
        Math.abs(e.clientX - rect.right),
        Math.abs(e.clientY - rect.top),
        Math.abs(e.clientY - rect.bottom),
      ) < 5
    if (edge) e.stopPropagation()
    down = { alias, x: e.clientX, y: e.clientY, edge }
    hold = setTimeout(() => {
      position(rect.left, rect.top)
      void rename(alias)
      release()
    }, 550)
  }
  function moving(e: PointerEvent) {
    if (down && Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5) {
      clearTimeout(hold)
      down.travelled = true
    }
  }
  /** The shape under the pointer at a drop, other than the one dropped and what it holds. */
  const shapeUnder = (e: PointerEvent, dropped: string): string | undefined => {
    const own = host.value?.querySelector(`[data-alias="${CSS.escape(dropped)}"]`)
    return document.elementsFromPoint(e.clientX, e.clientY)
      .map((hit) => hit.closest<SVGElement>('[data-alias]'))
      .find((shape) => shape && shape !== own && host.value?.contains(shape))?.dataset.alias
  }
  function up(e: PointerEvent) {
    if (down?.edge) {
      const dest = document.elementFromPoint(e.clientX, e.clientY)?.closest<SVGElement>('[data-alias]')
        ?.dataset.alias
      if (dest && dest !== down.alias) {
        source.value = down.alias
        position(e.clientX, e.clientY)
        void pair(dest)
      }
    } else if (down?.alias && down.travelled) {
      const [alias, target] = [down.alias, shapeUnder(e, down.alias)]
      // After the canvas has kept the drop itself: what the drop asks for starts from where it was dropped.
      if (target) setTimeout(() => droppedOn(alias, target, e.clientX, e.clientY))
    }
    release()
  }
  function focusCanvas(e: PointerEvent) {
    if (e.button === 0) host.value?.focus({ preventScroll: true })
    press(e)
  }
  return { focusCanvas, up, release, moving }
}
