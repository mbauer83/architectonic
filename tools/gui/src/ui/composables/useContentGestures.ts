/**
 * What a press on the canvas means for its content (sketch 01·3, 01·10, 03·8–9), read once for the
 * press, the cursor and the highlight alike (`pressed`): on a line, or where one ends on an element's
 * edge, it is the line's (Q33), and a long press opens its relation — on its label, the label's own
 * text, typed in place (02·5); on an element's edge band, or the relation dot of a selected element, it
 * draws a relation; on the rest of an element it moves it, and a long press renames it.
 *
 * While nothing is pressed the side of the edge band under the pointer is said (`side`), which the
 * editor lights and turns the cursor to a crosshair for; while an element is dragged, the shape it is
 * over is handed on (`over`), which the editor says whether it would take it.
 */
import { onBeforeUnmount, ref, type Ref } from 'vue'
import { type Side, sideInBand } from '../../domain/layout/edgeBand'
import type { Extent } from '../../domain/layout/geometry'
import { lineEndNear } from '../../domain/layout/canvasRouteEdits'
import { pointOnPicture } from '../components/canvas/pointerOnPicture'
import type { DiagramEditing } from './useDiagramEditing'

/** How near a line's end, on screen, a press picks the line rather than the element's edge (Q33). */
const NEAR_AN_END = 6

export const elementAt = (event: Event) =>
  event.target instanceof Element ? event.target.closest<SVGGElement>('[data-alias]') : null

/** What a press at a point would do. */
type Pressed =
  | { readonly kind: 'line'; readonly index: number }
  | { readonly kind: 'edge'; readonly alias: string; readonly side: Side | null; readonly at: Extent }
  | { readonly kind: 'body'; readonly alias: string; readonly at: Extent }

/** The side of an element's edge band under the pointer, on screen. */
export interface HoveredSide {
  readonly alias: string
  readonly side: Side
  readonly at: Extent
}

const onScreen = (element: Element): Extent => {
  const rect = element.getBoundingClientRect()
  return { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom }
}

export function useContentGestures(
  host: Ref<HTMLElement | null>, editing: DiagramEditing, source: Ref<string>,
  position: (x: number, y: number) => void, rename: (alias: string) => void,
  editLine: (index: number) => void, pair: (alias: string) => void,
  /** An element moved and dropped over another shape: what it was dropped on, by alias. */
  droppedOn: (alias: string, target: string, x: number, y: number) => void = () => {},
  /** An element being moved is over another shape, or over none (*target* undefined), or let go (null). */
  over: (alias: string | null, target?: string) => void = () => {},
  /** A long press on the label of the line at *index*: its text, typed in place. */
  relabel: (index: number) => void = editLine,
) {
  let hold: ReturnType<typeof setTimeout> | undefined
  let down: { alias: string; x: number; y: number; edge: boolean; travelled?: boolean } | null = null
  /** The side of an edge band the pointer is on while nothing is pressed; null elsewhere. */
  const side = ref<HoveredSide | null>(null)
  function release() {
    clearTimeout(hold)
    if (down?.travelled && !down.edge) over(null)
    down = null
  }
  onBeforeUnmount(release)

  /** What a press at *e* would do, or null on open paper. */
  function pressed(e: PointerEvent): Pressed | null {
    const target = e.target instanceof Element ? e.target : null
    const dot = target?.closest<SVGElement>('[data-relation-from]')
    const from = dot?.dataset.relationFrom
    const fromShape = from ? host.value?.querySelector(`[data-alias="${CSS.escape(from)}"]`) : null
    if (from && fromShape) return { kind: 'edge', alias: from, side: null, at: onScreen(fromShape) }
    const line = target?.closest<SVGElement>('[data-relation]')
    const svg = host.value?.querySelector('svg') ?? null
    const pixel = svg ? 1 / (svg.getScreenCTM()?.a || 1) : 1
    const endpoint = lineEndNear(editing.session.courses.value, pointOnPicture(svg, e), NEAR_AN_END * pixel)
    if (line || endpoint) return { kind: 'line', index: endpoint?.line ?? Number(line?.dataset.relation) }
    const el = elementAt(e)
    if (!el) return null
    const alias = el.dataset.alias ?? ''
    const at = onScreen(el)
    const edge = sideInBand(at, { x: e.clientX, y: e.clientY })
    return edge ? { kind: 'edge', alias, side: edge, at } : { kind: 'body', alias, at }
  }

  function press(e: PointerEvent) {
    if (e.button !== 0) return
    side.value = null
    const what = pressed(e)
    if (!what) return
    if (what.kind === 'line') {
      position(e.clientX, e.clientY)
      down = { alias: '', x: e.clientX, y: e.clientY, edge: false }
      const onLabel = e.target instanceof Element && e.target.closest('.lab-line-label') !== null
      hold = setTimeout(() => (onLabel ? relabel : editLine)(what.index), 550)
      return
    }
    const edge = what.kind === 'edge'
    if (edge) e.stopPropagation()
    down = { alias: what.alias, x: e.clientX, y: e.clientY, edge }
    hold = setTimeout(() => {
      position(what.at.left, what.at.top)
      void rename(what.alias)
      release()
    }, 550)
  }
  function moving(e: PointerEvent) {
    if (!down) {
      const what = e.buttons === 0 ? pressed(e) : null
      side.value = what?.kind === 'edge' && what.side ? { alias: what.alias, side: what.side, at: what.at } : null
      return
    }
    if (Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5) {
      clearTimeout(hold)
      down.travelled = true
    }
    if (down.travelled && down.alias && !down.edge) over(down.alias, shapeUnder(e, down.alias))
  }
  /** The boxes *alias* is drawn in, innermost first: each grows round it as it is dragged. */
  const holdersOf = (alias: string): ReadonlySet<string> => {
    const shapes = [...editing.session.geometry.value?.elements ?? [], ...editing.session.geometry.value?.boxes ?? []]
    const insideOf = new Map(shapes.map((shape) => [shape.alias, shape.inside]))
    const chain = new Set<string>()
    for (let at = insideOf.get(alias); at !== undefined && !chain.has(at); at = insideOf.get(at)) chain.add(at)
    return chain
  }
  /**
   * The shape under the pointer at a drop, other than the one dropped, what it holds, and the boxes it is
   * in — which grow round it while it moves, so are never what it is dropped on.
   */
  const shapeUnder = (e: PointerEvent, dropped: string): string | undefined => {
    const own = host.value?.querySelector(`[data-alias="${CSS.escape(dropped)}"]`)
    const holders = holdersOf(dropped)
    return document.elementsFromPoint(e.clientX, e.clientY)
      .map((hit) => hit.closest<SVGElement>('[data-alias]'))
      .find((shape) => shape && shape !== own && host.value?.contains(shape) && !holders.has(shape.dataset.alias ?? ''))
      ?.dataset.alias
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
  const leave = () => { side.value = null }
  return { focusCanvas, up, release, moving, leave, side }
}
